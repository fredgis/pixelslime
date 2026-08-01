# RUNBOOK — deploying and operating PIXELSLIME

> This is the operational source of truth: how to release the application, run the two jobs, verify
> Azure and Polygon Amoy, and recover from failures already seen in production.
>
> **Live-state checkpoint:** Azure, the public API and Polygon Amoy were queried on **2026-07-29**.
> Commands below are PowerShell unless stated otherwise.

## Contents

- [1. Current state and safety rules](#1-current-state-and-safety-rules)
- [2. Sign in and set variables](#2-sign-in-and-set-variables)
- [3. Secrets and environment](#3-secrets-and-environment)
- [4. Build, deploy and roll back](#4-build-deploy-and-roll-back)
- [5. Operate the Container Apps Jobs](#5-operate-the-container-apps-jobs)
- [6. Chain operations](#6-chain-operations)
- [7. Mochibo integrity: fixture versus deployed card](#7-mochibo-integrity-fixture-versus-deployed-card)
- [8. Post-deployment verification checklist](#8-post-deployment-verification-checklist)
- [9. Troubleshooting](#9-troubleshooting)
- [10. Cost](#10-cost)

---

## 1. Current state and safety rules

> **Placeholders.** This repository is public, so tenant-specific values are written as
> `<SUBSCRIPTION_ID>`, `<TENANT_ID>` and `<ASMDB_INSTANCE>`. Recover the real ones from the
> live environment rather than guessing:
>
> ```powershell
> az account show --query "{sub:id, tenant:tenantId}" -o json
> az containerapp show -n ca-pixelslime-api -g FGI-ASMDBPIXELSMILES `
>   --query "properties.template.containers[0].env[?name=='ASMDB_INSTANCE'].value" -o tsv
> ```
>
> `deploy.ps1` takes `-SubscriptionId` and `-AsmdbInstance` as **mandatory** parameters. That is
> deliberate: a default placeholder would deploy successfully and leave the app talking to a
> database that does not exist.

| | Live value |
|---|---|
| Subscription | `<SUBSCRIPTION_ID>` |
| Resource group / region | `FGI-ASMDBPIXELSMILES` / `swedencentral` |
| Public site | `https://www.pixelslime.cloud` |
| Platform FQDN | `ca-pixelslime-api.blackbay-470e05c9.swedencentral.azurecontainerapps.io` |
| Container Apps environment | `cae-pixelslime` |
| API | `ca-pixelslime-api` |
| Daily job | `caj-pixelslime-daily` — `0 8,9 * * *` UTC |
| Anchor job | `caj-pixelslime-anchor` — `30 8,9 * * *` UTC |
| Registry | `crpixelslimededh2k35j5.azurecr.io` |
| Managed identity | `id-pixelslime` |
| Active image | API, daily and anchor all use `pixelslime:v20` |
| asmDB | `https://www.asmdb.cloud` · instance `<ASMDB_INSTANCE>` |
| Chain | Polygon Amoy · chain id `80002` |
| Live health | `{"status":"ok","cards":1,"engine":"1.7.0"}` |

The API runs the real FastAPI application and built React SPA. There is no placeholder image in the
live environment.

### Non-negotiable operational rules

1. **Deploy one immutable image tag to all three workloads.** Never leave the API and jobs on
   different tags after a rollout.
2. **Never pass `--command`, `--args` or `--env-vars` to `az containerapp job start`.**
   A start-time container override replaces the execution template and can silently drop every
   configured environment variable and secret reference.
3. **The job definition must contain `command: ["python"]` and `args: ["-m", "app.jobs"]`.**
   The subcommand comes from `PIXELSLIME_JOB`.
4. **Never run `.\infra\deploy.ps1` without
   `-DeployPlaceholderImage:$false` against the live resource group.** Its default is still
   `$true`.
5. **Never put a private key, bearer token or admin token in this repository, a log, or a chat.**
6. **Do not redeploy the current chain contracts during an application release.** Mochibo's
   provenance is tied to the existing `PixelSlimeCard` address.

### 🚨 Active blocker: unrestricted anchor sweeps can re-bloom Mochibo

The intended state is that Mochibo's 760 SMILE remains in retired `ClaimPool` v1 and is **not**
recorded again in v2, because another `recordBloom(1, ...)` would burn another 100 SMILE.

The live state still satisfies that intent: v1 holds 760, v2 holds zero and
`v2.bloomRecorded(1) == false`. However, the current anchor source deliberately retries bloom
recording when an anchor row already exists. The live scheduled job points at v2 and normally walks
all serials. Therefore an unrestricted run can attempt to record serial 1 in v2.

> **Do not manually start the unrestricted anchor job until the application explicitly excludes the
> legacy PS-0001 bloom. Treat the scheduled job as unsafe until that guard is deployed.**

If a guarded image cannot be deployed before the next schedule, the conservative temporary
mitigation is to disable the schedule while preserving the definition:

```powershell
az containerapp job update `
  --name caj-pixelslime-anchor `
  --resource-group FGI-ASMDBPIXELSMILES `
  --cron-expression "0 0 31 2 *" `
  --only-show-errors --output none
```

This impossible date creates an anchor/bloom backlog for new cards. Restore the real schedule only
after PS-0001 is excluded:

```powershell
az containerapp job update `
  --name caj-pixelslime-anchor `
  --resource-group FGI-ASMDBPIXELSMILES `
  --cron-expression "30 8,9 * * *" `
  --only-show-errors --output none
```

---

## 2. Sign in and set variables

```powershell
Set-Location <repo>

az login --tenant <TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
az account show --query "{subscription:id,name:name,tenant:tenantId}" -o json
```

Expected subscription id:

```text
<SUBSCRIPTION_ID>
```

Set reusable values:

```powershell
$ResourceGroup = 'FGI-ASMDBPIXELSMILES'
$Registry = 'crpixelslimededh2k35j5'
$Repository = 'pixelslime'
$Api = 'ca-pixelslime-api'
$DailyJob = 'caj-pixelslime-daily'
$AnchorJob = 'caj-pixelslime-anchor'
$Tag = 'v12' # choose the next unused immutable tag
$Image = "$Registry.azurecr.io/$Repository`:$Tag"
```

---

## 3. Secrets and environment

### 3.1 Why signing does not use Key Vault

The management-group assignment `MCAPSGovDeployPolicies` applies two separate modify definitions:

| Resource | Enforcing definition | Live result |
|---|---|---|
| Key Vault | `KeyVault_PublicNetwork_Modify` | `publicNetworkAccess: Disabled` |
| Storage | `StorageAccount_PublicNetwork_Modify` | `publicNetworkAccess: Disabled` |

The policies revert public access changes within seconds. Storage is reachable through the deployed
VNet and private endpoint. Key Vault has no private endpoint, so its data plane is not on the workload
path.

The Amoy signer is therefore a raw secp256k1 key held in the anchor job's Container Apps secret
`chain-signer-key` and exposed as `CHAIN_LOCAL_PRIVATE_KEY`. This is weaker custody than an HSM, but
`backend/app/chain/signer.py` fails closed unless:

- `CHAIN_ALLOW_LOCAL_SIGNER=true`; and
- `CHAIN_ID` is in `TESTNET_CHAIN_IDS` (`80002`, `31337`, `1337`, `11155111`).

A value-bearing chain id is rejected in code.

### 3.2 Store or rotate the asmDB bearer

Container App secrets and Container Apps Job secrets are separate stores. Update all three:

```powershell
$secure = Read-Host 'asmDB bearer token' -AsSecureString
$plain = [System.Net.NetworkCredential]::new('', $secure).Password

az containerapp secret set `
  --name ca-pixelslime-api --resource-group FGI-ASMDBPIXELSMILES `
  --secrets "asmdb-bearer-token=$plain" --only-show-errors --output none

az containerapp job secret set `
  --name caj-pixelslime-daily --resource-group FGI-ASMDBPIXELSMILES `
  --secrets "asmdb-bearer-token=$plain" --only-show-errors --output none

az containerapp job secret set `
  --name caj-pixelslime-anchor --resource-group FGI-ASMDBPIXELSMILES `
  --secrets "asmdb-bearer-token=$plain" --only-show-errors --output none

Remove-Variable secure, plain
```

Ensure each workload references its local secret:

```powershell
az containerapp update `
  --name ca-pixelslime-api --resource-group FGI-ASMDBPIXELSMILES `
  --set-env-vars "ASMDB_BEARER_TOKEN=secretref:asmdb-bearer-token" `
  --only-show-errors --output none

az containerapp job update `
  --name caj-pixelslime-daily --resource-group FGI-ASMDBPIXELSMILES `
  --set-env-vars "ASMDB_BEARER_TOKEN=secretref:asmdb-bearer-token" `
  --only-show-errors --output none

az containerapp job update `
  --name caj-pixelslime-anchor --resource-group FGI-ASMDBPIXELSMILES `
  --set-env-vars "ASMDB_BEARER_TOKEN=secretref:asmdb-bearer-token" `
  --only-show-errors --output none
```

List names without revealing values:

```powershell
az containerapp secret list -n ca-pixelslime-api -g FGI-ASMDBPIXELSMILES `
  --query "[].name" -o tsv
az containerapp job secret list -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --query "[].name" -o tsv
az containerapp job secret list -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --query "[].name" -o tsv
```

### 3.3 Store or rotate the Amoy signer

Only the anchor job needs this key:

```powershell
$secure = Read-Host 'Amoy secp256k1 private key' -AsSecureString
$plain = [System.Net.NetworkCredential]::new('', $secure).Password

az containerapp job secret set `
  --name caj-pixelslime-anchor --resource-group FGI-ASMDBPIXELSMILES `
  --secrets "chain-signer-key=$plain" --only-show-errors --output none

Remove-Variable secure, plain

az containerapp job update `
  --name caj-pixelslime-anchor --resource-group FGI-ASMDBPIXELSMILES `
  --set-env-vars `
    "CHAIN_ALLOW_LOCAL_SIGNER=true" `
    "CHAIN_LOCAL_PRIVATE_KEY=secretref:chain-signer-key" `
  --only-show-errors --output none
```

Never put this key on the API or daily job.

### 3.4 Required environment

| Variable | API | Daily | Anchor | Live value / source |
|---|:---:|:---:|:---:|---|
| `ASMDB_BASE_URL` | ✓ | ✓ | ✓ | `https://www.asmdb.cloud` |
| `ASMDB_INSTANCE` | ✓ | ✓ | ✓ | `<ASMDB_INSTANCE>` |
| `ASMDB_BEARER_TOKEN` | ✓ | ✓ | ✓ | `secretref:asmdb-bearer-token` |
| `PIXELSLIME_JOB` | — | ✓ | ✓ | `daily` / `anchor` |
| `PIXELSLIME_FORCE` | — | optional | — | `1` bypasses only the Paris-hour guard |
| `CHAIN_RPC_URL` | read path | — | ✓ | `https://polygon-amoy.drpc.org` |
| `CHAIN_ID` | read path | — | ✓ | `80002` |
| `CARD_CONTRACT_ADDRESS` | read path | — | ✓ | `0xD889…Baf7f` |
| `CLAIM_POOL_ADDRESS` | read path | — | ✓ | v2 `0xbce1…160d` |
| `CHAIN_ALLOW_LOCAL_SIGNER` | — | — | ✓ | `true` on Amoy only |
| `CHAIN_LOCAL_PRIVATE_KEY` | — | — | ✓ | `secretref:chain-signer-key` |
| `SMILE_TOKEN_ADDRESS` | ✓ | — | — | `0x0BBa…b798` |
| `ADOPTION_ADDRESS` | ✓ | — | — | `0x20d6…CcA` |

Repair the anchor job's non-secret chain settings:

> Run this only after the PS-0001 blocker in §1 is resolved. Until then, setting
> `CLAIM_POOL_ADDRESS` arms the unsafe v2 replay path.

```powershell
az containerapp job update `
  --name caj-pixelslime-anchor --resource-group FGI-ASMDBPIXELSMILES `
  --set-env-vars `
    "PIXELSLIME_JOB=anchor" `
    "CHAIN_RPC_URL=https://polygon-amoy.drpc.org" `
    "CHAIN_ID=80002" `
    "CARD_CONTRACT_ADDRESS=0xD88928B55CefcAe756e55824a48342cA432Baf7f" `
    "CLAIM_POOL_ADDRESS=0xbce1362c1155777df19F9cea6c8ECa68B155160d" `
    "CHAIN_ALLOW_LOCAL_SIGNER=true" `
    "CHAIN_LOCAL_PRIVATE_KEY=secretref:chain-signer-key" `
  --only-show-errors --output none
```

---

## 4. Build, deploy and roll back

### 4.1 Build an immutable image in ACR

Docker is not required locally:

```powershell
Set-Location <repo>

az acr build `
  --registry crpixelslimededh2k35j5 `
  --image "pixelslime:$Tag" `
  --file Dockerfile .
```

Do not deploy `latest`; deploy the immutable version tag.

#### If the local CLI reports `UnicodeEncodeError`

On Windows, `az acr build` can crash while printing a `✓` with:

```text
UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'
```

That is a local console-encoding failure. The remote ACR build may already have succeeded. Check
before rebuilding or reusing a tag:

```powershell
az acr repository show-tags `
  --name crpixelslimededh2k35j5 `
  --repository pixelslime `
  --top 10 --orderby time_desc -o table

az acr task list-runs `
  --registry crpixelslimededh2k35j5 `
  --top 10 `
  --query "[].{runId:runId,status:status,lastUpdated:lastUpdatedTime}" -o table
```

### 4.2 Routine application rollout

Use targeted image updates so the existing environment, secret references, commands, domains and
chain settings remain intact:

```powershell
$Image = "crpixelslimededh2k35j5.azurecr.io/pixelslime:$Tag"

az containerapp update `
  --name ca-pixelslime-api --resource-group FGI-ASMDBPIXELSMILES `
  --image $Image --only-show-errors --output none

az containerapp job update `
  --name caj-pixelslime-daily --resource-group FGI-ASMDBPIXELSMILES `
  --image $Image --only-show-errors --output none

az containerapp job update `
  --name caj-pixelslime-anchor --resource-group FGI-ASMDBPIXELSMILES `
  --image $Image --only-show-errors --output none
```

Immediately run [the full checklist](#8-post-deployment-verification-checklist). In particular, verify
that `PIXELSLIME_JOB` on the daily job is still `daily`; it was found set to `seed` after debugging.

### 4.3 Infrastructure deployment caveats

`infra/deploy.ps1` compiles Bicep, validates, prints a what-if and requires explicit confirmation. Its
live-safe invocation shape is:

```powershell
Set-Location <repo>
.\infra\deploy.ps1 -ContainerImageTag $Tag -DeployPlaceholderImage:$false `
  -SubscriptionId <SUBSCRIPTION_ID> -AsmdbInstance <ASMDB_INSTANCE>
```

> ⚠️ **This is not currently a complete reconstruction of the live estate.**
>
> - Bicep models the API and daily job, but not the anchor job.
> - The custom domains are not represented.
> - The API's live chain-read environment is not represented.
> - `deploy.ps1` preserves API secrets, but does not manage the anchor signer.
> - Its final printed instruction still says to write the asmDB token to Key Vault; ignore it. The
>   correct Container Apps commands are in §3.

Use the script only for an intentional infrastructure change, review the what-if for domain,
environment and secret removal, and run the complete verification checklist afterwards. Use §4.2 for
a normal image release.

### 4.4 Roll back

Choose the last known-good immutable tag and update all three workloads:

```powershell
$Tag = 'v11'
$Image = "crpixelslimededh2k35j5.azurecr.io/pixelslime:$Tag"

az containerapp update -n ca-pixelslime-api -g FGI-ASMDBPIXELSMILES `
  --image $Image --only-show-errors --output none
az containerapp job update -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --image $Image --only-show-errors --output none
az containerapp job update -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --image $Image --only-show-errors --output none
```

Then run §8. A rollback is incomplete until the three image values are identical and the API checks
pass.

---

## 5. Operate the Container Apps Jobs

### 5.1 Definitions and schedules

| Job | UTC cron | Required dispatch | Definition command / args | Behaviour |
|---|---|---|---|---|
| `caj-pixelslime-daily` | `0 8,9 * * *` | `PIXELSLIME_JOB=daily` | `python` / `-m`, `app.jobs` | Both schedules run; only the one at 10:00 Europe/Paris proceeds |
| `caj-pixelslime-anchor` | `30 8,9 * * *` | `PIXELSLIME_JOB=anchor` | `python` / `-m`, `app.jobs` | Catch-up sweep; with no serials it visits every serial |

Paris is UTC+1 in winter and UTC+2 in summer. The double UTC schedule avoids editing Azure at every
DST transition. `backend/app/jobs/daily.py` makes the wrong firing a no-op.

`PIXELSLIME_FORCE=1` bypasses the Paris-hour guard, but **does not** bypass the date idempotency check.

### 5.2 Verify command, args and dispatch

```powershell
az containerapp job show -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --query "properties.template.containers[0].{command:command,args:args}" -o json

az containerapp job show -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --query "properties.template.containers[0].{command:command,args:args}" -o json

az containerapp job show -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --query "properties.template.containers[0].env[?name=='PIXELSLIME_JOB'].value" -o tsv

az containerapp job show -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --query "properties.template.containers[0].env[?name=='PIXELSLIME_JOB'].value" -o tsv
```

Both command queries must show:

```json
{
  "args": ["-m", "app.jobs"],
  "command": ["python"]
}
```

The dispatch queries must print `daily` and `anchor`.

### 5.3 Two Container Apps CLI traps

#### Trap 1 — start-time command overrides drop the environment

This is wrong:

```powershell
# DO NOT RUN
az containerapp job start -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --command "python" "-m" "app.jobs" "daily"
```

The start override replaces the entire container execution template. Historical failed executions
showed no environment at all, so the process had no asmDB URL, instance or bearer reference. Start a
configured job with no container overrides:

```powershell
az containerapp job start -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES
```

#### Trap 2 — `--args "-m app.jobs"` creates one argument

This is also wrong:

```powershell
# DO NOT RUN
az containerapp job update -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --command python --args "-m app.jobs"
```

It stores:

```json
["-m app.jobs"]
```

Python then fails with:

```text
Error while finding module specification for ' app.jobs'
(ModuleNotFoundError: No module named ' app')
```

The reliable repair is to export YAML, make the two elements explicit, and update from YAML:

```powershell
az containerapp job show `
  -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES -o yaml |
  Set-Content -Encoding utf8 .\caj-pixelslime-anchor.yaml
```

Edit the container in `properties.template.containers` to:

```yaml
command:
  - python
args:
  - -m
  - app.jobs
```

Apply and remove the local export:

```powershell
az containerapp job update `
  -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --yaml .\caj-pixelslime-anchor.yaml

Remove-Item .\caj-pixelslime-anchor.yaml
```

Repeat for the daily job if its arrays are wrong. Never place a secret value in the exported YAML.

### 5.4 Start the normal daily job

At 10:00 Europe/Paris:

```powershell
az containerapp job update -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --set-env-vars "PIXELSLIME_JOB=daily" "PIXELSLIME_FORCE=0" `
  --only-show-errors --output none

az containerapp job start -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES
```

Outside that hour it should stand down.

### 5.5 Force today's daily run

Use this only to recover today's missed bloom:

```powershell
try {
  az containerapp job update -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
    --set-env-vars "PIXELSLIME_JOB=daily" "PIXELSLIME_FORCE=1" `
    --only-show-errors --output none

  az containerapp job start -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES
}
finally {
  az containerapp job update -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
    --set-env-vars "PIXELSLIME_JOB=daily" "PIXELSLIME_FORCE=0" `
    --only-show-errors --output none
}
```

`job start` snapshots the definition for that execution; restoring the scheduled values after it
returns does not alter the execution already created.

### 5.6 Backfill an inclusive date range

The current CLI uses **positional** dates:

```text
python -m app.jobs backfill START END
```

It does not accept the old `--from` / `--to` options.

```powershell
try {
  az containerapp job update -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
    --set-env-vars "PIXELSLIME_JOB=backfill 2026-08-01 2026-08-03" `
    --only-show-errors --output none

  az containerapp job start -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES
}
finally {
  az containerapp job update -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
    --set-env-vars "PIXELSLIME_JOB=daily" "PIXELSLIME_FORCE=0" `
    --only-show-errors --output none
}
```

Existing dates are skipped. A missed date matters economically: every unrecorded bloom leaves the
finite 365,000-SMILE schedule short by 100.

### 5.7 Run the seed plan

`seed` installs PS-0001 through PS-0004 and validates any existing seed serial before skipping it.
It can make paid AI calls for missing seed cards. Use it only for fresh-environment recovery:

```powershell
try {
  az containerapp job update -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
    --set-env-vars "PIXELSLIME_JOB=seed" `
    --only-show-errors --output none

  az containerapp job start -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES
}
finally {
  az containerapp job update -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
    --set-env-vars "PIXELSLIME_JOB=daily" "PIXELSLIME_FORCE=0" `
    --only-show-errors --output none
}
```

The `finally` block is essential. The daily job was previously left at `PIXELSLIME_JOB=seed`.

### 5.8 Run anchoring

The local subcommand is:

```text
python -m app.jobs anchor [SERIAL ...]
```

With no serials it walks every asmDB serial. Explicit serials limit the run.

> The unrestricted command below remains blocked by the PS-0001 warning in §1.

```powershell
# Do not run until PS-0001 is explicitly excluded from v2 bloom recording.
az containerapp job start -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES
```

After a guarded image is deployed, target selected serials without changing the command:

```powershell
try {
  az containerapp job update -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
    --set-env-vars "PIXELSLIME_JOB=anchor" "ANCHOR_SERIALS=2,3" `
    --only-show-errors --output none

  az containerapp job start -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES
}
finally {
  az containerapp job update -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
    --remove-env-vars ANCHOR_SERIALS `
    --set-env-vars "PIXELSLIME_JOB=anchor" `
    --only-show-errors --output none
}
```

### 5.9 Inspect executions and logs

```powershell
az containerapp job execution list `
  -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES -o table

az containerapp job execution list `
  -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES -o table
```

For a live or recently completed execution:

```powershell
$Execution = '<execution-name>'
$Container = az containerapp job show `
  -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --query "properties.template.containers[0].name" -o tsv

az containerapp job replica list `
  -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --execution $Execution -o table

az containerapp job logs show `
  -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --execution $Execution --container $Container `
  --tail 100 --follow true --format text
```

Replicas are cleaned up, so old execution logs may no longer be available. Stop a hung execution by
its exact name. Do not use the stop command without `--job-execution-name`, because that stops every
currently running execution of the job:

```powershell
az containerapp job stop `
  -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
  --job-execution-name $Execution
```

---

## 6. Chain operations

### 6.1 RPC choice

| Endpoint | Suitable for | Operational result |
|---|---|---|
| `https://polygon-amoy.drpc.org` | normal reads, writes and 900-block log scans | Required endpoint. A verified 900-block `eth_getLogs` scan returned Mochibo's mint logs. The free plan can rate-limit or return `Request timeout`; retry later. |
| `https://polygon-amoy-bor-rpc.publicnode.com` | simple non-archive reads | Do not use for the anchor job. `eth_getLogs` returned `Archive requests require a personal token` / HTTP 403, so mint recovery cannot work. |

The recovery code scans backward in 900-block windows. dRPC also rejects ranges over 10,000 blocks
on the free plan, so widening the window is not a fix.

### 6.2 Live contracts

| Contract | Polygon Amoy address | Status |
|---|---|---|
| `SmileToken` | `0x0BBaC39Bf418ab63BF71802808A4C63D4B39b798` | active |
| `PixelSlimeCard` | `0xD88928B55CefcAe756e55824a48342cA432Baf7f` | active; Mochibo is token 1 |
| `ClaimPool` v2 | `0xbce1362c1155777df19F9cea6c8ECa68B155160d` | active for future blooms |
| `SlimeAdoption` | `0x20d6A4F365d00b4d27726f13093Dc2C497473CcA` | deployed, not enabled |
| `ClaimPool` v1 | `0x02a6887730894E39B437eB0A4AB457d98167Fc0f` | retired |

All five addresses returned non-empty bytecode.

> ⚠️ `chain/deployments/amoy.json` still names retired ClaimPool v1. Do not use that field to
> configure the anchor job; use the v2 address above.

### 6.3 Retired ClaimPool v1

V1 had no on-chain idempotency flag for `recordBloom`. A retry could burn another 100 SMILE, and a
zero-happiness card could never be detected through `yieldByCard > 0`.

Its `SmileToken.MINTER_ROLE` is revoked. Mochibo's 760 SMILE remains in v1 and was deliberately not
migrated: recording serial 1 in v2 would burn a second 100 for the same card. Do not “repair” the zero
v2 balance by replaying Mochibo.

Verified state at the checkpoint:

| Check | Value |
|---|---:|
| Treasury balance | 364,900 SMILE |
| V1 balance / `yieldByCard(1)` | 760 SMILE |
| V2 balance / `yieldByCard(1)` | 0 SMILE |
| V2 `bloomRecorded(1)` | `false` |
| Total supply | 365,660 SMILE |

### 6.4 Treasury-only rollout steps

These calls spend authority belonging to the Treasury/Vault, not the admin:

| Call | Required signer | Live status |
|---|---|---|
| `SmileToken.approve(ClaimPoolV2, type(uint256).max)` | Treasury | **done**; allowance is `2^256 - 1` |
| `PixelSlimeCard.setApprovalForAll(SlimeAdoption, true)` | Treasury | **not done**; adoption is not enabled |

The admin key cannot substitute for the Treasury key because it does not own the Genesis Rain or the
cards. Do not enable adoption until its product and operational flow are ready.

### 6.5 Read-only chain verification

The backend requirements include web3.py. This command verifies chain id, deployed code, the three
required SMILE minter-role checks, Mochibo's hash, the Treasury allowance and the disabled adoption
approval:

```powershell
Set-Location <repo>\backend

@'
from web3 import HTTPProvider, Web3
from web3.middleware import ExtraDataToPOAMiddleware

RPC = "https://polygon-amoy.drpc.org"
SMILE = Web3.to_checksum_address("0x0BBaC39Bf418ab63BF71802808A4C63D4B39b798")
CARD = Web3.to_checksum_address("0xD88928B55CefcAe756e55824a48342cA432Baf7f")
POOL = Web3.to_checksum_address("0xbce1362c1155777df19F9cea6c8ECa68B155160d")
ADOPTION = Web3.to_checksum_address("0x20d6A4F365d00b4d27726f13093Dc2C497473CcA")
ADMIN = Web3.to_checksum_address("0x56d1A1146a533dF4952Eb9f2FE6Fa0E7c51fc937")
TREASURY = Web3.to_checksum_address("0xb71C9B63ba13d2a34DD895A4De577661A963FaAc")

w3 = Web3(HTTPProvider(RPC, request_kwargs={"timeout": 60}))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
assert w3.eth.chain_id == 80002
for address in (SMILE, CARD, POOL, ADOPTION):
    assert len(w3.eth.get_code(address)) > 0

smile = w3.eth.contract(address=SMILE, abi=[
    {"type":"function","name":"MINTER_ROLE","stateMutability":"view","inputs":[],"outputs":[{"type":"bytes32"}]},
    {"type":"function","name":"hasRole","stateMutability":"view","inputs":[{"type":"bytes32"},{"type":"address"}],"outputs":[{"type":"bool"}]},
    {"type":"function","name":"allowance","stateMutability":"view","inputs":[{"type":"address"},{"type":"address"}],"outputs":[{"type":"uint256"}]},
])
card = w3.eth.contract(address=CARD, abi=[
    {"type":"function","name":"cardHash","stateMutability":"view","inputs":[{"type":"uint256"}],"outputs":[{"type":"bytes32"}]},
    {"type":"function","name":"isApprovedForAll","stateMutability":"view","inputs":[{"type":"address"},{"type":"address"}],"outputs":[{"type":"bool"}]},
])

role = smile.functions.MINTER_ROLE().call()
checks = {
    "admin_is_minter": smile.functions.hasRole(role, ADMIN).call(),
    "treasury_is_minter": smile.functions.hasRole(role, TREASURY).call(),
    "claim_pool_is_minter": smile.functions.hasRole(role, POOL).call(),
    "treasury_allowance_is_max": smile.functions.allowance(TREASURY, POOL).call() == 2**256 - 1,
    "adoption_is_enabled": card.functions.isApprovedForAll(TREASURY, ADOPTION).call(),
    "mochibo_hash": "0x" + card.functions.cardHash(1).call().hex(),
}
assert checks["admin_is_minter"] is False
assert checks["treasury_is_minter"] is False
assert checks["claim_pool_is_minter"] is True
assert checks["treasury_allowance_is_max"] is True
assert checks["adoption_is_enabled"] is False
assert checks["mochibo_hash"] == "0xe99e4c83067fa3c296802287e0779eaf5c10813cbc9e0c11d1dd75a162e7af0a"
print(checks)
'@ | python -
```

`ExtraDataToPOAMiddleware` is required because Polygon is proof-of-authority.

---

## 7. Mochibo integrity: fixture versus deployed card

Two different Mochibo hashes are correct because they hash two different canonical cards:

| Input | `art_sha` | `cardHash` |
|---|---|---|
| Repository fixture `contracts/cards/mochibo.json` | `00000000` | `0x718e809df90bbce66bf7bac60feff91edc4b97653771834555a037d58e680a1c` |
| Deployed card, using the real PNG SHA-256 prefix | `47f94199` | `0xe99e4c83067fa3c296802287e0779eaf5c10813cbc9e0c11d1dd75a162e7af0a` |

`backend/app/jobs/seed.py` replaces the fixture placeholder with the first eight hex characters of
the artwork SHA-256 before encoding. `art_sha` is part of the PSC-1 header, so the stream and hash
must change.

Verify the fixture vector:

```powershell
Set-Location <repo>
python scripts\verify_rows.py
```

Verify the deployed card:

```powershell
curl.exe -fsS https://www.pixelslime.cloud/api/cards/1/raw
```

The deployed API must return:

```text
0xe99e4c83067fa3c296802287e0779eaf5c10813cbc9e0c11d1dd75a162e7af0a
```

The chain verification in §6.5 must return the same value. Comparing the deployed value to the
`00000000` fixture vector is not an integrity test; it compares different inputs.

---

## 8. Post-deployment verification checklist

Run every item after an image release, infrastructure deployment, secret rotation or job repair.

### 8.1 API and card

```powershell
$Health = Invoke-RestMethod https://www.pixelslime.cloud/api/health
$Stats = Invoke-RestMethod https://www.pixelslime.cloud/api/stats
$Card = Invoke-RestMethod https://www.pixelslime.cloud/api/cards/1
$Raw = Invoke-RestMethod https://www.pixelslime.cloud/api/cards/1/raw

if ($Health.status -ne 'ok') { throw "Health is $($Health.status)" }
if ($Health.engine -ne '1.7.0') { throw "Unexpected asmDB engine $($Health.engine)" }
if (-not $Card.onChain) { throw 'PS-0001 is not reported on-chain' }
if ($Raw.cardHash -ne '0xe99e4c83067fa3c296802287e0779eaf5c10813cbc9e0c11d1dd75a162e7af0a') {
  throw "Unexpected PS-0001 hash $($Raw.cardHash)"
}

$Health
$Stats
$Card | Select-Object serial, name, onChain
$Raw | Select-Object rowCount, streamBytes, cardHash
```

### 8.2 All three resources use the expected image

```powershell
$ExpectedImage = "crpixelslimededh2k35j5.azurecr.io/pixelslime:$Tag"
$Images = @(
  az containerapp show -n ca-pixelslime-api -g FGI-ASMDBPIXELSMILES `
    --query "properties.template.containers[0].image" -o tsv
  az containerapp job show -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
    --query "properties.template.containers[0].image" -o tsv
  az containerapp job show -n caj-pixelslime-anchor -g FGI-ASMDBPIXELSMILES `
    --query "properties.template.containers[0].image" -o tsv
)

$Images
if ($Images.Count -ne 3 -or ($Images | Where-Object { $_ -ne $ExpectedImage })) {
  throw "Image mismatch; expected $ExpectedImage on API, daily and anchor"
}
```

### 8.3 Daily dispatch is `daily`

```powershell
$Dispatch = az containerapp job show `
  -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --query "properties.template.containers[0].env[?name=='PIXELSLIME_JOB'].value" -o tsv

if ($Dispatch -ne 'daily') {
  throw "Daily job would run '$Dispatch', not 'daily'"
}
```

### 8.4 Both jobs have the two-element args array

```powershell
foreach ($Job in @('caj-pixelslime-daily', 'caj-pixelslime-anchor')) {
  $Definition = az containerapp job show -n $Job -g FGI-ASMDBPIXELSMILES -o json |
    ConvertFrom-Json
  $Container = $Definition.properties.template.containers[0]

  if (@($Container.command).Count -ne 1 -or $Container.command[0] -ne 'python') {
    throw "$Job command is wrong: $($Container.command -join ', ')"
  }
  if (
    @($Container.args).Count -ne 2 -or
    $Container.args[0] -ne '-m' -or
    $Container.args[1] -ne 'app.jobs'
  ) {
    throw "$Job args are wrong: $($Container.args -join ', ')"
  }
}
```

### 8.5 Chain roles and approvals

Run the tested read-only command in §6.5. The required role results are:

| `SmileToken.hasRole(MINTER_ROLE, …)` | Expected |
|---|---|
| admin | `false` |
| Treasury | `false` |
| ClaimPool v2 | `true` |

Until adoption is intentionally launched, `isApprovedForAll(Treasury, SlimeAdoption)` must remain
`false`.

### 8.6 Domain and certificate

```powershell
az containerapp show -n ca-pixelslime-api -g FGI-ASMDBPIXELSMILES `
  --query "properties.configuration.ingress.customDomains" -o table

az containerapp env certificate list `
  -n cae-pixelslime -g FGI-ASMDBPIXELSMILES `
  --managed-certificates-only `
  --query "[].{name:name,subject:properties.subjectName,provisioning:properties.provisioningState}" `
  -o table
```

`www.pixelslime.cloud` must be `SniEnabled` with a succeeded managed certificate. DNS is managed at
OVH. The apex `pixelslime.cloud` binding is currently disabled and its certificate is not healthy.

---

## 9. Troubleshooting

| Symptom | Cause and action |
|---|---|
| `az acr build` ends with `UnicodeEncodeError: ... '\u2713'` | Local Windows console encoding failed. Check ACR tags and task runs before assuming the remote build failed. |
| A job runs uvicorn/the web server | Its definition is missing `command` / `args`, so the Dockerfile default `uvicorn app.main:app ...` runs. Repair the job definition through YAML (§5.3). |
| A job hangs with no useful output after a manual start | A start-time override replaced the template and dropped environment variables. Stop that execution and start the configured job with no overrides. |
| Python reports `No module named ' app'` | The job has one arg, `"-m app.jobs"`, instead of `"-m"` and `"app.jobs"`. Repair through YAML. |
| The named daily job seeds instead of blooming | `PIXELSLIME_JOB=seed` was left behind. Reset it to `daily` and add the §8.3 check to every rollout. |
| Daily starts but publishes nothing | Expected for one of the two UTC firings. Check Paris time and logs for `not 10:00 in Paris yet`; use `PIXELSLIME_FORCE=1` only for deliberate recovery. |
| `ExtraDataLengthError` from web3.py | Polygon is proof-of-authority. Inject `ExtraDataToPOAMiddleware` at layer 0 before block reads. The production anchor code already does this. |
| Anchor recovery fails with `Archive requests require a personal token` or HTTP 403 | The job is using PublicNode. Set `CHAIN_RPC_URL=https://polygon-amoy.drpc.org`. |
| dRPC returns `Request timeout` or a free-plan range error | Retry later. Keep log windows at the coded 900 blocks; do not replace them with one wide query. |
| Key Vault or Storage `publicNetworkAccess` changes back to `Disabled` within seconds | Governance policy is modifying the resource. Key Vault and Storage use separate definitions under `MCAPSGovDeployPolicies`; this is not application drift. |
| `/api/health` reports `degraded` | asmDB may be waking from scale-to-zero. Retry and inspect API logs. |
| `/api/cards/1/raw` shows `0xe99e…` instead of fixture `0x718e…` | Correct. The deployed card contains artwork SHA prefix `47f94199`; the fixture contains `00000000`. See §7. |
| An unrestricted anchor sweep is about to run against v2 | Stop. Until PS-0001 is explicitly excluded, the job can attempt a second Mochibo bloom. See the active blocker in §1. |
| Old execution logs cannot be fetched | Container Apps has already cleaned up the replica. Use execution metadata, Log Analytics/Application Insights, and capture logs while the replica still exists. |

To inspect the policy definitions affecting each resource:

```powershell
$KeyVaultId = az keyvault show -n kv-pixelslime-dedh2k35j5 `
  -g FGI-ASMDBPIXELSMILES --query id -o tsv
az policy state list --resource $KeyVaultId `
  --query "[].{assignment:policyAssignmentName,definition:policyDefinitionName,state:complianceState}" `
  -o table

$StorageId = az storage account show -n stpixelslimededh2k35j5 `
  -g FGI-ASMDBPIXELSMILES --query id -o tsv
az policy state list --resource $StorageId `
  --query "[].{assignment:policyAssignmentName,definition:policyDefinitionName,state:complianceState}" `
  -o table
```

---

## 10. Cost

The planning estimate remains roughly **€15–25/month** excluding AI image generation. Both Container
Apps Jobs scale to zero between executions. asmDB is currently on its free tier and Amoy gas has no
real monetary value.

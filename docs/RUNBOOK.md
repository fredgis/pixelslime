# RUNBOOK — deploying and operating PIXELSLIME

Everything is built, tested and pushed. The infrastructure is deployed. What remains is the
application rollout, which needs one thing only this repository cannot provide: **your asmDB bearer
token**, which is readable exactly once and must never travel through a chat, a log or a commit.

---

## Current state

| | |
|---|---|
| Resource group | `FGI-ASMDBPIXELSMILES` · `swedencentral` · **deployed** |
| Container App | `ca-pixelslime-api` — running the **placeholder** image, responds `200` |
| Daily job | `caj-pixelslime-daily` — armed, cron `0 8,9 * * *` UTC |
| Key Vault | `kv-pixelslime-dedh2k35j5` — **empty, awaiting the bearer** |
| Registry | `crpixelslimededh2k35j5.azurecr.io` — **empty** |
| Storage | `stpixelslimededh2k35j5` — `cards` / `thumbs` / `assets`, public access off |
| asmDB | `smilesdb`, engine 1.7.0, **0 rows** |

The API FQDN is:

```
ca-pixelslime-api.bluesmoke-129b4159.swedencentral.azurecontainerapps.io
```

---

## Step 0 — sign in

```powershell
az login --tenant <TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
```

> The CLI was signed out during the build by an `az account clear` that should not have been run.
> Nothing in Azure was affected; only the local credential cache was cleared.

---

## Step 1 — store the asmDB bearer token

**You run this, not the agent.** The token never appears in a prompt, a log or a commit.

```powershell
$token = Read-Host 'asmDB bearer token' -AsSecureString
$plain = [System.Net.NetworkCredential]::new('', $token).Password
az keyvault secret set `
  --vault-name kv-pixelslime-dedh2k35j5 `
  --name asmdb-bearer-token `
  --value $plain --only-show-errors --output none
Remove-Variable token, plain
```

Confirm it landed without printing it:

```powershell
az keyvault secret show --vault-name kv-pixelslime-dedh2k35j5 --name asmdb-bearer-token --query id -o tsv
```

Your account already holds `Key Vault Secrets Officer` on the vault. If it reports `Forbidden`, the
role assignment is still propagating — wait a minute and retry.

---

## Step 2 — build and push the image

ACR builds remotely, so Docker is not needed locally.

```powershell
cd <repo>
az acr build `
  --registry crpixelslimededh2k35j5 `
  --image pixelslime:v1 `
  --image pixelslime:latest `
  --file Dockerfile .
```

The build is three stages: the SPA (`VITE_USE_MOCK=false`, so no mock reaches production), the Python
dependency layer from `backend/requirements.txt`, and a non-root runtime carrying both.

---

## Step 3 — switch the app onto the real image

```powershell
cd infra
.\deploy.ps1 -ContainerImageTag v1 -DeployPlaceholderImage $false
```

This flips ingress from port 80 to 8000 and injects `ASMDB_BEARER_TOKEN` as a Container Apps secret
reference that the platform resolves from Key Vault using the managed identity — so the token is
resolved *before* the process starts and the app makes no Key Vault call of its own.

Verify:

```powershell
curl.exe -s https://ca-pixelslime-api.bluesmoke-129b4159.swedencentral.azurecontainerapps.io/api/health
```

Expect `{"status":"ok","cards":0,...}`.

---

## Step 4 — seed the collection

```powershell
az containerapp job start -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --command "python" "-m" "app.jobs" "seed"
```

This imports **Mochibo as PS-0001** from `contracts/cards/mochibo.json` with the existing artwork, then
generates the seed slimes. It is idempotent per serial.

Then confirm the round trip actually holds against the real database:

```powershell
curl.exe -s https://<fqdn>/api/cards/1/raw
```

The `cardHash` must be `0x718e809df90bbce66bf7bac60feff91edc4b97653771834555a037d58e680a1c` — the same
digest the codec produces locally. If it differs, **stop**: something between encode and storage is
lossy, and that is precisely what the round-trip guardrail exists to catch.

---

## Step 5 — let it run

The job fires at `0 8,9 * * *` UTC and exits immediately unless it is 10:00 in `Europe/Paris`, so
exactly one of the two runs publishes, across both DST transitions. Nothing further is required.

Watch the first real run:

```powershell
az containerapp job execution list -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES -o table
```

---

## Operations

### Generate a card by hand

The admin endpoint is **disabled unless a token is configured**, and says so at startup with an
explicit log line. To arm it:

```powershell
$t = Read-Host 'admin token' -AsSecureString
$p = [System.Net.NetworkCredential]::new('', $t).Password
az keyvault secret set --vault-name kv-pixelslime-dedh2k35j5 --name admin-token --value $p --only-show-errors --output none
Remove-Variable t, p
```

No redeploy is needed — the admin token resolves through Key Vault on its own ladder, independent of
how the bearer was obtained.

### Backfill a missed day

**This matters more than it looks.** The Genesis Rain funds exactly 3,650 blooms; a day that is missed
and never backfilled leaves the puddle short by 100 $SMILE forever, and the tenth-anniversary story is
off by one card. See [`PLAN.md` §8.11](PLAN.md#811-the-arithmetic-closes--and-it-is-a-knife-edge).

```powershell
az containerapp job start -n caj-pixelslime-daily -g FGI-ASMDBPIXELSMILES `
  --command "python" "-m" "app.jobs" "backfill" "--from" "2026-08-01" "--to" "2026-08-03"
```

### Rotate the asmDB token

The token is stored only as a hash by asmDB and cannot be read back. Rotation is two-phase, and is
authenticated with Entra rather than with the token itself — which is the point, since rotation is
what you need when the token is lost:

```
POST https://www.asmdb.cloud/api/v1/databases/{id}/rotate-token
POST https://www.asmdb.cloud/api/v1/databases/{id}/rotate-token/commit
```

Then update the Key Vault secret and restart the app. The commit call stops and starts the instance,
because the engine holds an exclusive lock and a rolling update cannot work.

### Deploy the contracts to Amoy

Not yet done, and deliberately so — it is independent of the site running. Full instructions are in
W9's report; the essentials:

1. Create the signing key. The private key never leaves the HSM:
   ```powershell
   az keyvault key create --vault-name kv-pixelslime-dedh2k35j5 --name pixelslime-signer `
     --kty EC --curve P-256K --ops sign verify
   ```
2. Fund the **deployer** from the Amoy faucet at <https://faucet.polygon.technology/>.
3. ⚠️ **The admin key must be a different key from the Treasury.** If they are the same, the Treasury
   can grant itself `MINTER_ROLE` and refill the Genesis Rain, and the entire economic guarantee
   becomes decorative. The constructor enforces this, but choose the keys deliberately.
4. `forge script script/Deploy.s.sol:Deploy --rpc-url amoy --broadcast --verify`

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `/api/health` reports `degraded` | asmDB is asleep. It scales to zero on the free tier; the first call wakes it. The app degrades rather than failing to start, by design. |
| Job runs but publishes nothing | Expected. It fires twice a day and stands down unless it is 10:00 in Paris. Check the logs for `not 10:00 in Paris yet`. |
| A card shows as anchored in the gallery but not on its page | Should now be impossible — both read the same value captured at index time. If it happens, the anchor row decode is failing; check for `card_read_failed`. |
| `429` from the image model | 2 requests per 60 seconds. Irrelevant at one card a day; only bursts trigger it. |
| A card is missing from the gallery | Look for `card_read_failed`. A card whose continuation row is missing is skipped loudly rather than taking startup down. |

---

## Cost

Roughly **€15–25/month** excluding image generation, on scale-to-zero. The daily job costs pennies.
asmDB is on the free tier. Amoy gas is free.

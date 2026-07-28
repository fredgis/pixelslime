# PIXELSLIME infrastructure

The Bicep entry point is `main.bicep`. It targets the existing
`FGI-ASMDBPIXELSMILES` resource group and uses incremental deployments.

## Modules

| Module | Responsibility |
|---|---|
| `identity.bicep` | Creates the single user-assigned identity used by the API and daily job. |
| `key-vault.bicep` | Creates an empty RBAC-mode Key Vault and grants the identity `Key Vault Secrets User`. |
| `storage.bicep` | Creates private `cards`, `thumbs`, and `assets` containers and grants blob data access. |
| `container-registry.bicep` | Creates Basic ACR with its admin user disabled and grants `AcrPull`. |
| `observability.bicep` | Creates Log Analytics and workspace-based Application Insights, including metrics RBAC. |
| `container-apps.bicep` | Creates the Consumption environment, public unauthenticated API, and scheduled daily job. |
| `cognitive-services-role.bicep` | Runs at explicit `FGI-AI` resource-group scope and grants the identity access to the existing `fgi` AI account. |

No secret value is accepted by any template or script.

Resource names use the first 10 characters of
`uniqueString(resourceGroup().id)`. The full 13-character value would exceed
both the 24-character Key Vault limit and the 24-character Storage account
limit with the required prefixes.

## Deploy

The first deployment uses `mcr.microsoft.com/k8se/quickstart:latest`. The API
temporarily targets port 80 because that image does not listen on the final
application port. Key Vault references and ACR pull configuration are added
only when `DeployPlaceholderImage` is false, so an empty new vault cannot block
the bootstrap deployment.

```powershell
Set-Location <repo>
.\infra\deploy.ps1
```

The script compiles, validates, displays a what-if, and deploys only after
`DEPLOY` is typed.

After the first deployment, the owner must have a Key Vault data-plane role
such as `Key Vault Secrets Officer`. Store the token interactively:

```powershell
$asmdbToken = Read-Host 'asmDB bearer token' -AsSecureString
$asmdbTokenPlain = [System.Net.NetworkCredential]::new('', $asmdbToken).Password
az keyvault secret set --vault-name 'kv-pixelslime-dedh2k35j5' --name 'asmdb-bearer-token' --value $asmdbTokenPlain --only-show-errors --output none
Remove-Variable asmdbToken, asmdbTokenPlain
```

Build and push `pixelslime:<tag>` to the reported ACR login server, then switch
both workloads to it:

```powershell
.\infra\deploy.ps1 -DeployPlaceholderImage:$false -ContainerImageTag '<tag>'
```

The final API command is
`python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`. The job command is
`python -m app.jobs.daily`; W8 must provide that module entry point.

## Rollback

For an application rollback, redeploy a previously known-good immutable image
tag with `DeployPlaceholderImage:$false`. For an infrastructure rollback,
restore the prior `infra/` revision and redeploy it. ARM incremental mode does
not delete resources removed from a template, so remove such resources
explicitly only after checking their data.

For a complete teardown of this dedicated resource group:

```powershell
az group delete --name FGI-ASMDBPIXELSMILES --yes
```

This is destructive. Key Vault purge protection keeps the deleted vault
recoverable and reserves its name for the configured retention period.

## Deployment permissions

The deploying principal needs resource deployment and role-assignment
permissions in `FGI-ASMDBPIXELSMILES`. It also needs
`Microsoft.Resources/deployments/*` in `FGI-AI` and
`Microsoft.Authorization/roleAssignments/write` on the existing `fgi` AI
account for the cross-resource-group assignment.

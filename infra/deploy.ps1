[CmdletBinding()]
param(
    [Parameter()]
    [string] $ResourceGroup = 'FGI-ASMDBPIXELSMILES',

    [Parameter()]
    [string] $SubscriptionId = '<SUBSCRIPTION_ID>',

    [Parameter()]
    [string] $Location,

    [Parameter()]
    [string] $ContainerImageTag = 'latest',

    [Parameter()]
    [bool] $DeployPlaceholderImage = $true,

    # Skip the interactive confirmation. Needed for CI and for any non-interactive
    # shell; the what-if still runs and is still printed, so the change is never
    # applied unseen.
    [Parameter()]
    [switch] $Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$templateFile = Join-Path $PSScriptRoot 'main.bicep'
$deploymentName = "pixelslime-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

az account set --subscription $SubscriptionId
if ($LASTEXITCODE -ne 0) {
    throw "Unable to select Azure subscription '$SubscriptionId'."
}

$parameters = @(
    "containerImageTag=$ContainerImageTag"
    "deployPlaceholderImage=$($DeployPlaceholderImage.ToString().ToLowerInvariant())"
)
if ($Location) {
    $parameters += "location=$Location"
}

# Secrets live as Container Apps secrets, not Key Vault references: a management-group
# policy forces publicNetworkAccess: Disabled on every vault in this tenant, and reaching
# one privately would mean recreating the Container Apps environment, whose VNet config is
# immutable.
#
# Bicep is declarative, so a redeploy that omits a secret REMOVES it. Read the current
# values back and pass them through, otherwise a routine image bump silently unauthenticates
# the app against asmDB and the site starts returning empty galleries.
$appName = 'ca-pixelslime-api'
foreach ($secret in @(
    @{ Name = 'asmdb-bearer-token'; Param = 'asmdbBearerToken'; Label = 'asmDB bearer token' },
    @{ Name = 'admin-token';        Param = 'adminToken';       Label = 'admin token' }
)) {
    $existing = az containerapp secret show `
        --name $appName --resource-group $ResourceGroup `
        --secret-name $secret.Name --query value -o tsv 2>$null
    if ($LASTEXITCODE -eq 0 -and $existing) {
        Write-Host ("  preserving existing {0}" -f $secret.Label)
        $parameters += "$($secret.Param)=$existing"
    }
    $global:LASTEXITCODE = 0
}

Write-Host 'Compiling Bicep...'
az bicep build --file $templateFile --stdout | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Bicep compilation failed.'
}

Write-Host 'Validating deployment...'
az deployment group validate `
    --resource-group $ResourceGroup `
    --template-file $templateFile `
    --parameters $parameters `
    --no-prompt true `
    --only-show-errors `
    --output none
if ($LASTEXITCODE -ne 0) {
    throw 'Azure deployment validation failed.'
}

Write-Host 'Calculating deployment what-if...'
az deployment group what-if `
    --resource-group $ResourceGroup `
    --name $deploymentName `
    --template-file $templateFile `
    --parameters $parameters `
    --no-prompt true `
    --result-format ResourceIdOnly
if ($LASTEXITCODE -ne 0) {
    throw 'Azure deployment what-if failed.'
}

if ($Yes) {
    Write-Host "Applying deployment '$deploymentName' (confirmation skipped by -Yes)."
}
else {
    $confirmation = Read-Host "Type DEPLOY to apply deployment '$deploymentName'"
    if ($confirmation -cne 'DEPLOY') {
        Write-Host 'Deployment cancelled; no resources were changed.'
        exit 0
    }
}

az deployment group create `
    --resource-group $ResourceGroup `
    --name $deploymentName `
    --template-file $templateFile `
    --parameters $parameters `
    --no-prompt true `
    --only-show-errors `
    --output none
if ($LASTEXITCODE -ne 0) {
    throw 'Azure deployment failed.'
}

$outputsJson = az deployment group show `
    --resource-group $ResourceGroup `
    --name $deploymentName `
    --query properties.outputs `
    --output json
if ($LASTEXITCODE -ne 0) {
    throw 'Deployment succeeded, but its outputs could not be read.'
}
$outputs = $outputsJson | ConvertFrom-Json

$apiFqdn = $outputs.apiFqdn.value
$keyVaultName = $outputs.keyVaultName.value
$acrLoginServer = $outputs.acrLoginServer.value

Write-Host ''
Write-Host 'Deployment outputs'
Write-Host "  API FQDN:        $apiFqdn"
Write-Host "  Key Vault:       $keyVaultName"
Write-Host "  ACR login server: $acrLoginServer"
Write-Host ''
Write-Host 'Store the asmDB token without placing its value in this repository or shell history:'
Write-Host ('$asmdbToken = Read-Host ''asmDB bearer token'' -AsSecureString; $asmdbTokenPlain = [System.Net.NetworkCredential]::new('''', $asmdbToken).Password; az keyvault secret set --vault-name "{0}" --name "asmdb-bearer-token" --value $asmdbTokenPlain --only-show-errors --output none; Remove-Variable asmdbToken, asmdbTokenPlain' -f $keyVaultName)

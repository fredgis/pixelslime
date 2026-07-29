targetScope = 'resourceGroup'

@description('Azure region for all regional resources.')
param location string = resourceGroup().location

@description('Tag of the pixelslime image in the provisioned Azure Container Registry.')
param containerImageTag string = 'latest'

@description('Deploy the public Microsoft quickstart image until the pixelslime image is available.')
param deployPlaceholderImage bool = true

@description('''
asmDB bearer token, stored as a Container Apps secret rather than a Key Vault reference.

A management-group policy (KeyVault_PublicNetwork_Modify, assignment MCAPSGovDeployPolicies)
forces publicNetworkAccess: Disabled on every Key Vault in this tenant - it reverted our
Bicep's Enabled within ten seconds. Reaching the vault would need a private endpoint plus a
VNet-injected Container Apps environment, and an environment's VNet configuration is
immutable, so that means recreating it.

@secure() keeps this out of deployment history. Leave empty to preserve whatever is already
set on the app: deploy.ps1 reads the existing value back and passes it through, so a
redeploy never silently wipes the secret.
''')
@secure()
param asmdbBearerToken string = ''

@description('Optional admin token guarding POST /api/admin/generate. Empty leaves it disabled.')
@secure()
param adminToken string = ''

@description('Scheme and host of the asmDB service.')
param asmdbBaseUrl string = 'https://www.asmdb.cloud'

@description('The 24-character asmDB instance suffix — the database this app reads and writes.')
param asmdbInstance string = '<ASMDB_INSTANCE>'

@description('''
Which job the scheduled container runs. Normally 'daily'.

Set to 'seed' (or 'backfill --from ... --to ...') and redeploy to run that instead, then
set it back. This is deliberately an environment variable rather than a start-time command
override: overriding a Container Apps Job's command replaces the whole container template
and silently drops every environment variable it needs, which makes the job hang with no
output at all.
''')
param jobCommand string = 'daily'

@description('''
Set true to let the daily job run outside its 10:00 Europe/Paris window.

For seeding a fresh deployment or recovering a failed run. It does not bypass the
date-idempotency check, so a forced run still cannot produce a second card for a day
that already has one.
''')
param forceJobRun bool = false

@description('''
JSON-RPC endpoint for the chain. Leave empty to deploy without the chain integration —
the anchor job is then not created at all.

Note the endpoint must permit eth_getLogs: the anchor job recovers a mint whose asmDB
row was lost by reading Transfer logs, and polygon-amoy-bor-rpc.publicnode.com answers
any log query with a bare 403.
''')
param chainRpcUrl string = ''

@description('EIP-155 chain id. 80002 is Polygon Amoy.')
param chainId int = 80002

@description('Deployed PixelSlimeCard address — the anchor target.')
param cardContractAddress string = ''

@description('Deployed ClaimPool address — burns the Bloom Fee, mints the yield.')
param claimPoolAddress string = ''

@description('''
secp256k1 key signing anchor and bloom transactions.

A Container Apps secret rather than Key Vault, because the KeyVault_PublicNetwork_Modify
policy at management-group scope forces publicNetworkAccess: Disabled and reverts any
change within seconds. app/chain/signer.py refuses this signer off a testnet, so the
trade-off cannot silently follow the system to a chain carrying real value.
''')
@secure()
param chainSignerKey string = ''

// Key Vault and Storage names cannot fit the full 13-character uniqueString value.
var uniqueSuffix = take(uniqueString(resourceGroup().id), 10)
var identityName = 'id-pixelslime'
var keyVaultName = 'kv-pixelslime-${uniqueSuffix}'
var storageAccountName = 'stpixelslime${uniqueSuffix}'
var containerRegistryName = 'crpixelslime${uniqueSuffix}'
var logAnalyticsName = 'log-pixelslime'
var applicationInsightsName = 'appi-pixelslime'
var containerAppsEnvironmentName = 'cae-pixelslime'
var containerAppName = 'ca-pixelslime-api'
var containerAppsJobName = 'caj-pixelslime-daily'
var imageRepositoryName = 'pixelslime'
var placeholderImage = 'mcr.microsoft.com/k8se/quickstart:latest'
var aiResourceGroupName = 'FGI-AI'
var aiAccountName = 'fgi'

module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    location: location
    name: identityName
  }
}

module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  params: {
    location: location
    name: keyVaultName
    managedIdentityName: identityName
  }
  dependsOn: [
    identity
  ]
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    name: storageAccountName
    managedIdentityName: identityName
  }
  dependsOn: [
    identity
  ]
}

module containerRegistry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  params: {
    location: location
    name: containerRegistryName
    managedIdentityName: identityName
  }
  dependsOn: [
    identity
  ]
}

module observability 'modules/observability.bicep' = {
  name: 'observability'
  params: {
    location: location
    logAnalyticsName: logAnalyticsName
    applicationInsightsName: applicationInsightsName
    managedIdentityName: identityName
  }
  dependsOn: [
    identity
  ]
}

module cognitiveServicesRole 'modules/cognitive-services-role.bicep' = {
  name: 'cognitive-services-role'
  scope: resourceGroup(subscription().subscriptionId, aiResourceGroupName)
  params: {
    accountName: aiAccountName
    managedIdentityName: identityName
    managedIdentityResourceGroupName: resourceGroup().name
  }
  dependsOn: [
    identity
  ]
}

module network 'modules/network.bicep' = {
  name: 'network'
  params: {
    location: location
    vnetName: 'vnet-pixelslime'
    storageAccountName: storageAccountName
  }
  dependsOn: [
    storage
  ]
}

module containerApps 'modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    location: location
    environmentName: containerAppsEnvironmentName
    containerAppName: containerAppName
    jobName: containerAppsJobName
    logAnalyticsName: logAnalyticsName
    applicationInsightsName: applicationInsightsName
    managedIdentityName: identityName
    asmdbBearerToken: asmdbBearerToken
    adminToken: adminToken
    asmdbBaseUrl: asmdbBaseUrl
    asmdbInstance: asmdbInstance
    acaSubnetId: network.outputs.acaSubnetId
    jobCommand: jobCommand
    chainRpcUrl: chainRpcUrl
    chainId: chainId
    cardContractAddress: cardContractAddress
    claimPoolAddress: claimPoolAddress
    chainSignerKey: chainSignerKey
    forceJobRun: forceJobRun
    storageAccountName: storageAccountName
    registryName: containerRegistryName
    imageRepositoryName: imageRepositoryName
    placeholderImage: placeholderImage
    containerImageTag: containerImageTag
    deployPlaceholderImage: deployPlaceholderImage
  }
  dependsOn: [
    keyVault
    storage
    containerRegistry
    observability
    cognitiveServicesRole
  ]
}

output apiFqdn string = containerApps.outputs.apiFqdn
output keyVaultName string = keyVault.outputs.name
output acrLoginServer string = containerRegistry.outputs.loginServer
output storageAccountName string = storage.outputs.name
output managedIdentityClientId string = identity.outputs.clientId
output appInsightsConnectionString string = observability.outputs.applicationInsightsConnectionString

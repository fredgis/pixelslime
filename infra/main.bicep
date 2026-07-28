targetScope = 'resourceGroup'

@description('Azure region for all regional resources.')
param location string = resourceGroup().location

@description('Tag of the pixelslime image in the provisioned Azure Container Registry.')
param containerImageTag string = 'latest'

@description('Deploy the public Microsoft quickstart image until the pixelslime image is available.')
param deployPlaceholderImage bool = true

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
    keyVaultName: keyVaultName
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

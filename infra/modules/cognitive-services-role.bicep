targetScope = 'resourceGroup'

@description('Name of the existing Azure AI Services account.')
param accountName string

@description('Name of the platform managed identity.')
param managedIdentityName string

@description('Resource group containing the platform managed identity.')
param managedIdentityResourceGroupName string

var cognitiveServicesUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'a97b65f3-24c7-4388-baec-2e87135dc908'
)

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: managedIdentityName
  scope: resourceGroup(subscription().subscriptionId, managedIdentityResourceGroupName)
}

resource cognitiveServicesUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiAccount.id, managedIdentity.id, cognitiveServicesUserRoleId)
  scope: aiAccount
  properties: {
    roleDefinitionId: cognitiveServicesUserRoleId
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

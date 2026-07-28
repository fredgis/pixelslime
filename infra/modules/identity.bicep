targetScope = 'resourceGroup'

@description('Name of the user-assigned managed identity.')
param name string

@description('Azure region for the managed identity.')
param location string

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: name
  location: location
}

output resourceId string = managedIdentity.id
output principalId string = managedIdentity.properties.principalId
output clientId string = managedIdentity.properties.clientId

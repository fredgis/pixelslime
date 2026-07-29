@description('Azure region for the network resources.')
param location string

@description('Name of the virtual network.')
param vnetName string

@description('Address space for the virtual network.')
param addressPrefix string = '10.42.0.0/16'

@description('Subnet the Container Apps environment is injected into.')
param acaSubnetPrefix string = '10.42.0.0/23'

@description('Subnet holding private endpoints.')
param privateEndpointSubnetPrefix string = '10.42.2.0/28'

@description('Name of the storage account to reach privately.')
param storageAccountName string

// A management-group policy in this tenant forces publicNetworkAccess: Disabled on both
// Key Vault and Storage - it reverts any attempt to enable them within seconds. The Key
// Vault dependency was removed by moving secrets into Container Apps, but Storage holds
// the card artwork and cannot be substituted, so it has to be reached over a private
// endpoint. That in turn requires the Container Apps environment to be VNet-injected,
// and an environment's VNet configuration is immutable - which is why the environment is
// recreated rather than updated.
//
// ACR (Basic) and Log Analytics are NOT restricted by the policy, so they stay public and
// need no private endpoints. Scoping this to Storage alone keeps the footprint small.

var blobPrivateDnsZoneName = 'privatelink.blob.${environment().suffixes.storage}'

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [addressPrefix]
    }
    subnets: [
      {
        // Container Apps workload-profile environments require a dedicated subnet
        // delegated to Microsoft.App/environments, minimum /27.
        name: 'snet-aca'
        properties: {
          addressPrefix: acaSubnetPrefix
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: privateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: storageAccountName
}

resource blobPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: blobPrivateDnsZoneName
  location: 'global'
}

resource blobDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: blobPrivateDnsZone
  name: '${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource blobPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${storageAccountName}-blob'
  location: location
  properties: {
    subnet: {
      id: vnet.properties.subnets[1].id
    }
    privateLinkServiceConnections: [
      {
        name: 'blob'
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: ['blob']
        }
      }
    ]
  }
}

resource blobDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: blobPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: blobPrivateDnsZone.id
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output acaSubnetId string = vnet.properties.subnets[0].id
output privateEndpointSubnetId string = vnet.properties.subnets[1].id

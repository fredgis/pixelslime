targetScope = 'resourceGroup'

@description('Azure region for Container Apps resources.')
param location string

@description('Name of the Container Apps managed environment.')
param environmentName string

@description('Name of the public API Container App.')
param containerAppName string

@description('Name of the scheduled Container Apps Job.')
param jobName string

@description('Name of the existing Log Analytics workspace.')
param logAnalyticsName string

@description('Name of the existing Application Insights component.')
param applicationInsightsName string

@description('Name of the platform user-assigned managed identity.')
param managedIdentityName string

@description('Name of the platform Key Vault.')
param keyVaultName string

@description('Name of the platform Storage account.')
param storageAccountName string

@description('Name of the platform Azure Container Registry.')
param registryName string

@description('Repository containing the pixelslime image.')
param imageRepositoryName string

@description('Public image used while the pixelslime image is unavailable.')
param placeholderImage string

@description('Tag of the pixelslime image in the platform registry.')
param containerImageTag string

@description('Whether the public Microsoft quickstart image is being deployed.')
param deployPlaceholderImage bool

var asmDbSecretName = 'asmdb-bearer-token'
var asmDbSecretUrl = '${keyVault.properties.vaultUri}secrets/${asmDbSecretName}'
var containerImage = deployPlaceholderImage
  ? placeholderImage
  : '${registry.properties.loginServer}/${imageRepositoryName}:${containerImageTag}'
var commonEnvironmentVariables = [
  {
    name: 'AZURE_CLIENT_ID'
    value: managedIdentity.properties.clientId
  }
  {
    name: 'KEY_VAULT_URI'
    value: keyVault.properties.vaultUri
  }
  {
    name: 'STORAGE_ACCOUNT_NAME'
    value: storageAccountName
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: applicationInsights.properties.ConnectionString
  }
]
var runtimeEnvironmentVariables = concat(commonEnvironmentVariables, [
  {
    name: 'ASMDB_BEARER_TOKEN'
    secretRef: asmDbSecretName
  }
])
var containerEnvironmentVariables = deployPlaceholderImage
  ? commonEnvironmentVariables
  : runtimeEnvironmentVariables
var keyVaultSecrets = deployPlaceholderImage
  ? []
  : [
      {
        name: asmDbSecretName
        identity: managedIdentity.id
        keyVaultUrl: asmDbSecretUrl
      }
    ]
var registries = deployPlaceholderImage
  ? []
  : [
      {
        server: registry.properties.loginServer
        identity: managedIdentity.id
      }
    ]

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-02-01' existing = {
  name: logAnalyticsName
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: managedIdentityName
}

resource keyVault 'Microsoft.KeyVault/vaults@2025-05-01' existing = {
  name: keyVaultName
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource environment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

resource api 'Microsoft.App/containerApps@2025-07-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: deployPlaceholderImage ? 80 : 8000
        transport: 'Auto'
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: registries
      secrets: keyVaultSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: containerImage
          command: deployPlaceholderImage ? [] : [
            'python'
          ]
          args: deployPlaceholderImage
            ? []
            : [
                '-m'
                'uvicorn'
                'app.main:app'
                '--host'
                '0.0.0.0'
                '--port'
                '8000'
              ]
          env: containerEnvironmentVariables
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
      }
    }
  }
}

resource dailyJob 'Microsoft.App/jobs@2025-07-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: '0 8,9 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registries
      secrets: keyVaultSecrets
    }
    template: {
      containers: [
        {
          name: 'daily'
          image: containerImage
          command: deployPlaceholderImage ? [] : [
            'python'
          ]
          args: deployPlaceholderImage
            ? []
            : [
                '-m'
                'app.jobs.daily'
              ]
          env: containerEnvironmentVariables
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
}

output apiFqdn string = api.properties.configuration.ingress.fqdn

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

@description('''
asmDB bearer token, stored as a Container Apps secret rather than a Key Vault reference.

A management-group policy (KeyVault_PublicNetwork_Modify, assignment MCAPSGovDeployPolicies)
forces publicNetworkAccess: Disabled on every Key Vault in this tenant. It reverted our
Bicep's `Enabled` within ten seconds. Reaching the vault would therefore need a private
endpoint plus a VNet-injected Container Apps environment - and an environment's VNet
configuration is immutable, so that means deleting and recreating it.

Container Apps encrypts this value at rest, it is never returned by the control plane in
a template deployment, and @secure() keeps it out of deployment history. The optional
admin token follows the same path for the same reason.

Leave empty to preserve whatever is already set on the app; deploy.ps1 reads the existing
value back and passes it through, so a redeploy never silently wipes the secret.
''')
@secure()
param asmdbBearerToken string = ''

@description('Optional admin token guarding POST /api/admin/generate. Empty leaves it disabled.')
@secure()
param adminToken string = ''

var asmDbSecretName = 'asmdb-bearer-token'
var adminSecretName = 'admin-token'
var containerImage = deployPlaceholderImage
  ? placeholderImage
  : '${registry.properties.loginServer}/${imageRepositoryName}:${containerImageTag}'
var commonEnvironmentVariables = [
  {
    name: 'AZURE_CLIENT_ID'
    value: managedIdentity.properties.clientId
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
var bearerEnvironmentVariable = empty(asmdbBearerToken)
  ? []
  : [
      {
        name: 'ASMDB_BEARER_TOKEN'
        secretRef: asmDbSecretName
      }
    ]
var adminEnvironmentVariable = empty(adminToken)
  ? []
  : [
      {
        name: 'ADMIN_TOKEN'
        secretRef: adminSecretName
      }
    ]
var runtimeEnvironmentVariables = concat(
  commonEnvironmentVariables,
  bearerEnvironmentVariable,
  adminEnvironmentVariable
)
var containerEnvironmentVariables = deployPlaceholderImage
  ? commonEnvironmentVariables
  : runtimeEnvironmentVariables
var bearerSecret = empty(asmdbBearerToken)
  ? []
  : [
      {
        name: asmDbSecretName
        value: asmdbBearerToken
      }
    ]
var adminSecret = empty(adminToken)
  ? []
  : [
      {
        name: adminSecretName
        value: adminToken
      }
    ]
var appSecrets = deployPlaceholderImage ? [] : concat(bearerSecret, adminSecret)
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
      secrets: appSecrets
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
      secrets: appSecrets
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

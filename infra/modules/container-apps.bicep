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

@description('Scheme and host of the asmDB service.')
param asmdbBaseUrl string

@description('The 24-character asmDB instance suffix.')
param asmdbInstance string

@description('Resource id of the subnet the Container Apps environment is injected into.')
param acaSubnetId string

@description('Which job the daily container runs: daily, seed, or backfill with its arguments.')
param jobCommand string = 'daily'

@description('Let the daily job run outside its 10:00 Europe/Paris window.')
param forceJobRun bool = false

@description('JSON-RPC endpoint for the chain. Must permit eth_getLogs for mint recovery.')
param chainRpcUrl string = ''

@description('EIP-155 chain id. 80002 is Polygon Amoy.')
param chainId int = 80002

@description('Deployed PixelSlimeCard address — the anchor target.')
param cardContractAddress string = ''

@description('Deployed ClaimPool address — burns the Bloom Fee and mints the yield.')
param claimPoolAddress string = ''

@description('''
secp256k1 key that signs anchor and bloom transactions.

Held here rather than in Key Vault because the KeyVault_PublicNetwork_Modify policy at
management-group scope forces publicNetworkAccess: Disabled and reverts any change
within seconds, leaving the vault data plane unreachable. app/chain/signer.py refuses
this signer on any chain outside TESTNET_CHAIN_IDS, so the concession cannot follow the
system onto a chain where the money is real.
''')
@secure()
param chainSignerKey string = ''

var asmDbSecretName = 'asmdb-bearer-token'
var adminSecretName = 'admin-token'
var chainKeySecretName = 'chain-signer-key'
var containerImage = deployPlaceholderImage
  ? placeholderImage
  : '${registry.properties.loginServer}/${imageRepositoryName}:${containerImageTag}'
var chainEnvironmentVariables = empty(chainRpcUrl)
  ? []
  : concat(
      [
        {
          name: 'CHAIN_RPC_URL'
          value: chainRpcUrl
        }
        {
          name: 'CHAIN_ID'
          value: string(chainId)
        }
        {
          name: 'CARD_CONTRACT_ADDRESS'
          value: cardContractAddress
        }
        {
          name: 'CLAIM_POOL_ADDRESS'
          value: claimPoolAddress
        }
      ],
      empty(chainSignerKey)
        ? []
        : [
            {
              name: 'CHAIN_ALLOW_LOCAL_SIGNER'
              value: 'true'
            }
            {
              name: 'CHAIN_LOCAL_PRIVATE_KEY'
              secretRef: chainKeySecretName
            }
          ]
    )
var commonEnvironmentVariables = [
  {
    name: 'AZURE_CLIENT_ID'
    value: managedIdentity.properties.clientId
  }
  {
    name: 'PIXELSLIME_JOB'
    value: jobCommand
  }
  {
    name: 'PIXELSLIME_FORCE'
    value: forceJobRun ? '1' : '0'
  }
  {
    name: 'ASMDB_BASE_URL'
    value: asmdbBaseUrl
  }
  {
    name: 'ASMDB_INSTANCE'
    value: asmdbInstance
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
  adminEnvironmentVariable,
  chainEnvironmentVariables
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
var chainSecret = empty(chainSignerKey)
  ? []
  : [
      {
        name: chainKeySecretName
        value: chainSignerKey
      }
    ]
var appSecrets = deployPlaceholderImage ? [] : concat(bearerSecret, adminSecret, chainSecret)
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
    // VNet injection is what lets the app resolve and reach the Storage private
    // endpoint. A management-group policy forces publicNetworkAccess: Disabled on
    // Storage and reverts any attempt to change it, so there is no public route to
    // the card artwork. This property is immutable once set, which is why switching
    // to it required recreating the environment.
    vnetConfiguration: {
      infrastructureSubnetId: acaSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
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
          // Runs the multiplexer, which reads PIXELSLIME_JOB. Selecting the subcommand
          // through an env var rather than a start-time command override matters: an
          // override replaces the whole container template and silently drops every
          // environment variable the job needs, so it hangs with no output at all.
          args: deployPlaceholderImage
            ? []
            : [
                '-m'
                'app.jobs'
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

// Anchoring runs as its own job, half an hour behind the bloom. Keeping it separate
// from generation is deliberate: a card in asmDB is already the real artefact, so an
// RPC hiccup or an empty gas tank must never roll it back or hold up the day's slime.
// It is also self-healing — a serial that already carries its anchor row costs one
// cheap read, so re-running is safe and is the normal way a failure is recovered.
resource anchorJob 'Microsoft.App/jobs@2025-07-01' = if (!deployPlaceholderImage && !empty(chainRpcUrl)) {
  name: '${jobName}-anchor'
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
        cronExpression: '30 8,9 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registries
      secrets: appSecrets
    }
    template: {
      containers: [
        {
          name: 'anchor'
          image: containerImage
          command: [
            'python'
          ]
          args: [
            '-m'
            'app.jobs'
          ]
          // Same template as the daily job apart from this one variable, which is what
          // selects the subcommand. Overriding the command at start time instead would
          // replace the template and drop every variable below.
          env: concat(
            filter(containerEnvironmentVariables, e => e.name != 'PIXELSLIME_JOB'),
            [
              {
                name: 'PIXELSLIME_JOB'
                value: 'anchor'
              }
            ]
          )
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
# 🏗️ ARCHITECTURE — PIXELSLIME as actually deployed

> This describes what is **running**, not what was planned. Where the two differ, the difference is
> explained — usually because reality pushed back. [`PLAN.md`](PLAN.md) holds the reasoning;
> [`RUNBOOK.md`](RUNBOOK.md) holds the operations; [`HOWITWORKS.md`](HOWITWORKS.md) follows the
> byte-for-byte data path.
>
> **Live-state checkpoint:** Azure, the public API and Polygon Amoy were queried on **2026-07-29**.
> Where the checked-in source is newer than the active container image, that deployment drift is
> called out explicitly rather than blurred into the architecture.

| | |
|---|---|
| Subscription | `<SUBSCRIPTION_ID>` |
| Resource group | `FGI-ASMDBPIXELSMILES` · `swedencentral` |
| Public site | [`https://www.pixelslime.cloud`](https://www.pixelslime.cloud) · managed certificate · `SniEnabled` |
| Platform FQDN | `ca-pixelslime-api.blackbay-470e05c9.swedencentral.azurecontainerapps.io` |
| Apex domain | `pixelslime.cloud` is present with a disabled binding; its managed certificate is failed |
| Live health | `{"status":"ok","cards":1,"engine":"1.7.0"}` |
| Active image | `crpixelslimededh2k35j5.azurecr.io/pixelslime:v8` |
| Database | asmDB Cloud · `smilesdb` · instance `<ASMDB_INSTANCE>` |
| Chain | Polygon **Amoy** testnet · chain id `80002` |

## Contents

- [1. The whole picture](#1-the-whole-picture)
- [2. Why there is a VNet at all](#2-why-there-is-a-vnet-at-all)
- [3. Where the secrets live](#3-where-the-secrets-live)
- [4. The jobs architecture](#4-the-jobs-architecture)
- [5. How a card is stored in 175 bytes](#5-how-a-card-is-stored-in-175-bytes)
- [6. The chain, and why the fee is real](#6-the-chain-and-why-the-fee-is-real)
- [7. Reading a card, end to end](#7-reading-a-card-end-to-end)
- [8. Azure resource inventory](#8-azure-resource-inventory)
- [9. How to navigate the codebase](#9-how-to-navigate-the-codebase)
- [10. What it costs](#10-what-it-costs)
- [11. Drift, limitations, and deviations](#11-drift-limitations-and-deviations)

---

## 1. The whole picture

```mermaid
flowchart TB
    NET(["🌍 Anyone on the internet<br/>no sign-in · no account · nothing to log into"])

    subgraph RG["🇸🇪 FGI-ASMDBPIXELSMILES · swedencentral"]
      direction TB

      subgraph VNET["🔒 vnet-pixelslime · 10.42.0.0/16"]
        direction TB
        subgraph SNETACA["snet-aca · 10.42.0.0/23 · delegated to Microsoft.App/environments"]
          API["<b>ca-pixelslime-api</b><br/>Container App · 0 to 3 replicas<br/>FastAPI + the built React SPA<br/><i>one origin, so zero CORS</i>"]
          DAILY["<b>caj-pixelslime-daily</b><br/>Container Apps Job<br/>cron 0 8,9 UTC<br/><i>command selected by PIXELSLIME_JOB</i>"]
          ANCHOR["<b>caj-pixelslime-anchor</b><br/>Container Apps Job<br/>cron 30 8,9 UTC<br/><i>idempotent catch-up sweep</i>"]
        end
        subgraph SNETPE["snet-private-endpoints · 10.42.2.0/28"]
          PE["<b>pe-stpixelslimededh2k35j5-blob</b><br/>private endpoint"]
        end
      end

      MI(["<b>id-pixelslime</b><br/>user-assigned managed identity"])
      ST[("<b>stpixelslimededh2k35j5</b><br/>Blob Storage<br/>cards · thumbs · assets<br/><b>public network DISABLED</b>")]
      ACR["<b>crpixelslimededh2k35j5</b><br/>Container Registry · Basic"]
      OBS["<b>appi-pixelslime</b><br/>App Insights + Log Analytics"]
      KV[("<b>kv-pixelslime-dedh2k35j5</b><br/>Key Vault<br/><i>deployed but its data plane<br/>is unreachable from the workloads</i>")]
    end

    AI["<b>fgi</b> · resource group FGI-AI<br/>gpt-image-2 · gpt-5.6-sol"]
    DB[("<b>asmdb.cloud</b> · smilesdb<br/><b>source of truth</b>")]
    RPC["<b>polygon-amoy.drpc.org</b><br/>JSON-RPC<br/><i>supports the required log scans</i>"]
    CHAIN["<b>Polygon Amoy</b><br/>PixelSlimeCard · SmileToken<br/>ClaimPool · SlimeAdoption"]

    NET -->|HTTPS| API
    API --> MI
    DAILY --> MI
    ANCHOR --> MI
    PE -->|private link| ST
    API -->|blob reads| PE
    DAILY -->|blob writes| PE
    MI -->|Cognitive Services User<br/>cross resource group| AI
    MI -->|AcrPull| ACR
    MI -->|Blob Data Contributor| ST
    API -->|startup and reconcile| DB
    DAILY -->|card rows| DB
    ANCHOR -->|read cards and write part 8| DB
    DAILY -->|metadata and image| AI
    ANCHOR -->|signed transactions| RPC
    RPC --> CHAIN
    API --> OBS
    DAILY --> OBS
    ANCHOR --> OBS

    classDef gold fill:#FFD86B,stroke:#2B1B4A,stroke-width:4px,color:#2B1B4A
    classDef pink fill:#FF8FC5,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef lilac fill:#E7DCFF,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef orange fill:#FF7A59,stroke:#2B1B4A,stroke-width:4px,color:#FFFFFF
    classDef blue fill:#8FD3FF,stroke:#2B1B4A,stroke-width:4px,color:#2B1B4A
    classDef mint fill:#7FE3C0,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A

    class NET,ACR,OBS lilac
    class API,PE,RPC blue
    class DAILY,ANCHOR mint
    class MI,AI,CHAIN gold
    class ST,DB pink
    class KV orange
```

The API and both jobs run the **same immutable image** with different entrypoints. The API owns the
public read path; generation owns AI, blob and card-row writes; anchoring owns chain writes. Keeping
anchoring separate means an RPC outage can never roll back or suppress a valid card already stored in
asmDB.

---

## 2. Why there is a VNet at all

The plan had no network. The site is public by design, Container Apps Consumption was enough, and the
whole thing was meant to cost €15–25/month. Two governance policies changed that during deployment.

```mermaid
flowchart LR
    P["<b>Management-group assignment</b><br/>MCAPSGovDeployPolicies"]
    PK["<b>KeyVault_PublicNetwork_Modify</b>"]
    PS["<b>StorageAccount_PublicNetwork_Modify</b>"]
    KVX["<b>Key Vault</b><br/>publicNetworkAccess forced to Disabled<br/><i>reverted our Bicep in under 10 s</i>"]
    STX["<b>Storage</b><br/>publicNetworkAccess forced to Disabled<br/><i>reverted in 20 s</i>"]

    A["<b>Sidestep</b><br/>secrets move to Container Apps<br/>Key Vault no longer needed"]
    B["<b>Cannot sidestep</b><br/>Storage holds the card artwork<br/>there is no substitute"]
    C["<b>VNet + private endpoint</b><br/>which forces a VNet-injected<br/>Container Apps environment"]
    D["<b>Environment recreated</b><br/>vnetConfiguration is immutable"]

    P --> PK --> KVX --> A
    P --> PS --> STX --> B --> C --> D

    classDef gold fill:#FFD86B,stroke:#2B1B4A,stroke-width:4px,color:#2B1B4A
    classDef orange fill:#FF7A59,stroke:#2B1B4A,stroke-width:4px,color:#FFFFFF
    classDef blue fill:#8FD3FF,stroke:#2B1B4A,stroke-width:4px,color:#2B1B4A
    classDef mint fill:#7FE3C0,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A

    class P orange
    class PK,PS,KVX,STX gold
    class A mint
    class B,C,D blue
```

The two resources are modified by **separate policy definitions under the same assignment**. Azure
Policy reported both resources compliant with the `modify` action, and the live control plane showed
`publicNetworkAccess: Disabled` on each. Only Storage and Key Vault are restricted: ACR Basic,
Application Insights and Log Analytics still accept public traffic, so they need no private
endpoints. Scoping the network to a **single** private endpoint instead of four kept the footprint and
the cost down.

**What was deliberately *not* built.** An API Management gateway was considered and rejected: it fronts
HTTP APIs and does not proxy the Key Vault or Storage data planes, so it would not have unblocked
anything. The Developer SKU also carries no SLA, which would have made a daily-publishing site *less*
reliable, for about €45/month.

---

## 3. Where the secrets live

```mermaid
flowchart TB
    subgraph SEC["Secret resolution, in order"]
      direction TB
      E1["1 · env ASMDB_BEARER_TOKEN<br/><i>Container Apps secret, resolved by the<br/>platform before the process starts</i>"]
      E2["2 · Key Vault via KEY_VAULT_URI<br/><i>fallback for any other host</i>"]
      E3["3 · fail closed<br/><i>clear error, no silent degradation</i>"]
      E1 --> E2 --> E3
    end

    ADM["<b>Admin token — its own ladder</b><br/>env → Key Vault → <b>disabled</b><br/><i>disabled is logged explicitly at startup</i>"]

    NOTE["<b>Why not Key Vault</b><br/>policy forces it unreachable, and reaching it<br/>privately would need a second private endpoint<br/>for a single string"]

    SEC -.-> NOTE
    ADM -.-> NOTE

    classDef step fill:#8FD3FF,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef fail fill:#FF7A59,stroke:#2B1B4A,stroke-width:3px,color:#FFFFFF
    classDef note fill:#FFF6E5,stroke:#8B6FE8,stroke-width:3px,color:#2B1B4A
    classDef adm  fill:#FFD86B,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A

    class E1,E2 step
    class E3 fail
    class ADM adm
    class NOTE note
```

The bearer **fails closed** — without it the app refuses to start, because an API silently serving an
empty gallery is worse than one that will not boot. The admin token **fails safe** — absent means the
endpoint is disabled, and that state is announced in one explicit log line, because a security control
that turns itself off quietly is worse than one that was never there.

> ⚠️ **Bicep is declarative: a redeploy that omits a secret deletes it.** `deploy.ps1` reads the current
> values back and passes them through, otherwise a routine image bump would unauthenticate the app
> against asmDB and the gallery would quietly go empty.

---

## 4. What happens every day at 10:00 Paris

```mermaid
flowchart TB
    CRON(["⏰ cron 0 8,9 UTC<br/>fires twice"])
    GUARD{"Is it 10:00<br/>in Europe/Paris?"}
    STOP(["stand down<br/><i>the other firing publishes</i>"])
    IDEM{"Does a card already<br/>exist for today?"}
    ROLL["<b>1 · ROLL</b><br/>weighted rarity + pity timer<br/><i>in code, never the model</i>"]
    META["<b>2 · METADATA</b> — gpt-5.6-sol<br/>structured output, length-capped"]
    GATE{"Trial PSC-1<br/>encode fits?"}
    IMG["<b>3 · IMAGE</b> — gpt-image-2<br/>/images/edits · image[] = mochibo + rarity ref"]
    ALPHA["<b>4 · ALPHA</b><br/>flood-fill white exterior into real transparency"]
    VER{"Vision check<br/>+ corner alpha<br/>+ not a Mochibo clone"}
    BLOB["<b>5 · BLOB FIRST</b><br/>PNG + WebP through the private endpoint"]
    ROWS["<b>6 · THEN ROWS</b><br/>PSC-1 → Z85 → asmDB"]
    RT{"Read back,<br/>decode, compare"}
    ROLLBACK["🔥 delete the rows<br/><i>a half-written card never becomes<br/>the card of the day</i>"]
    ANCHOR["<b>7 · ANCHOR</b><br/>keccak256 → mintCard on Amoy<br/>tx → row part 8"]
    LIVE(["✨ Today's Bloom is live"])

    CRON --> GUARD
    GUARD -->|no| STOP
    GUARD -->|yes| IDEM
    IDEM -->|yes| STOP
    IDEM -->|no| ROLL --> META --> GATE
    GATE -->|no, reprompt shorter| META
    GATE -->|yes| IMG --> ALPHA --> VER
    VER -->|fail, one retry| IMG
    VER -->|pass| BLOB --> ROWS --> RT
    RT -->|mismatch| ROLLBACK
    RT -->|identical| ANCHOR --> LIVE

    classDef time fill:#FFF6E5,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef gate fill:#FFF6E5,stroke:#8B6FE8,stroke-width:3px,color:#2B1B4A
    classDef code fill:#FFD86B,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef model fill:#C08BFF,stroke:#2B1B4A,stroke-width:3px,color:#FFFFFF
    classDef proc fill:#7FE3C0,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef data fill:#8FD3FF,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef chain fill:#FF8FC5,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef bad  fill:#FF7A59,stroke:#2B1B4A,stroke-width:3px,color:#FFFFFF
    classDef good fill:#FFF6E5,stroke:#FF7A59,stroke-width:4px,color:#2B1B4A

    class CRON time
    class GUARD,IDEM,GATE,VER,RT gate
    class ROLL code
    class META,IMG model
    class ALPHA proc
    class BLOB,ROWS data
    class ANCHOR chain
    class ROLLBACK,STOP bad
    class LIVE good
```

**Blobs are written before rows, deliberately.** If the upload fails, nothing has reached the database.
An orphan blob is harmless and gets overwritten; an orphan **row** would surface as a broken card.

---

## 5. How a card is stored in 175 bytes

```mermaid
flowchart LR
    CARD["<b>Card</b><br/>name · stats · personality<br/>power · quote"]
    HDR["<b>32-byte header</b><br/>serial · level · rarity+type+shiny<br/>height · weight · 4 stats<br/>art_sha · crc16"]
    TXT["<b>Text bundle</b><br/>joined with 0x1F<br/>raw DEFLATE + preset dictionary"]
    STREAM["<b>PSC-1 stream</b><br/>Mochibo: 52 bytes"]
    Z85["<b>Z85 encode</b><br/>4 bytes → 5 chars<br/><i>140 binary bytes per row</i>"]
    ROW0[("<b>row serial×16+0</b><br/>value = YYYYMMDD (positive)<br/>tag = psc.N.0")]
    ROWN[("<b>rows +1…3</b><br/>value = −(serial×16+part)<br/><i>negative, so RANGE never returns them</i>")]
    ROW8[("<b>row serial×16+8</b><br/>anchor: tx hash · block · tokenId · cardHash")]
    HASH["<b>keccak256</b><br/>of the stream"]
    NFT["<b>ERC-721</b><br/>cardHash on Polygon Amoy"]

    CARD --> HDR --> STREAM
    CARD --> TXT --> STREAM
    STREAM --> Z85 --> ROW0
    Z85 --> ROWN
    STREAM --> HASH --> NFT --> ROW8

    classDef src   fill:#FFD86B,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef proc  fill:#7FE3C0,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef enc   fill:#8FD3FF,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef store fill:#FF8FC5,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef chain fill:#C08BFF,stroke:#2B1B4A,stroke-width:3px,color:#FFFFFF

    class CARD src
    class HDR,TXT proc
    class STREAM,Z85 enc
    class ROW0,ROWN,ROW8 store
    class HASH,NFT chain
```

An asmDB row gives **175 bytes of UTF-8 with no NUL, CR or LF** — it is text, not a binary field, which
is why raw bytes cannot simply be written. Z85 was chosen over base64 for density (140 usable bytes
versus 131) and because its alphabet contains no backslash, space or quote, so it cannot collide with
the engine's internal TSV escaping.

| Fixture | Stream | Rows | Widest row |
|---|---:|---:|---:|
| `mochibo` | 52 B | **1** | 65 of 175 |
| a realistic unseen card | 183 B | 2 | 175 |
| every field at its limit, incompressible | 205 B | 2 | 175 |

The largest schema-valid card provably deflates to a 557-byte stream against a 560-byte ceiling, so
**no valid card can overflow**. Chunking is the guarantee; the dictionary is upside.

---

## 6. The chain, and why the fee is real

```mermaid
flowchart TB
    G["<b>🌧️ GENESIS RAIN</b><br/>365,000 SMILE minted once<br/>held by the Treasury<br/><b>minter role then renounced</b>"]
    BLOOM(["🫧 a slime blooms<br/>every day at 10:00 Paris"])
    FEE["<b>BLOOM FEE — 100 SMILE</b>"]
    BURN1["🔥 <b>BURNED</b><br/>3,650 blooms and the puddle is dry<br/><i>exactly ten years</i>"]
    YIELD["<b>YIELD</b> = happiness × rarity multiplier<br/><i>computed on-chain, not supplied by the backend</i>"]
    POOL["<b>💧 CLAIM POOL</b><br/>the Treasury has no role here<br/>and no allowance to itself"]
    KEEP(["🧑‍🌾 Keepers<br/>optional wallet · EIP-712 voucher with a deadline"])
    ADOPT["<b>ADOPT</b><br/>NFT leaves the Vault"]
    BURN2["🔥 <b>BURNED</b>"]

    G -->|every bloom| FEE --> BURN1
    BLOOM --> FEE
    BLOOM --> YIELD -->|NOT into the Treasury| POOL
    POOL --> KEEP --> ADOPT --> BURN2

    classDef gen  fill:#FFD86B,stroke:#2B1B4A,stroke-width:4px,color:#2B1B4A
    classDef blm  fill:#FF8FC5,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef mid  fill:#E7DCFF,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef burn fill:#FF7A59,stroke:#2B1B4A,stroke-width:4px,color:#FFFFFF
    classDef pool fill:#8FD3FF,stroke:#2B1B4A,stroke-width:4px,color:#2B1B4A
    classDef keep fill:#7FE3C0,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A

    class G gen
    class BLOOM,YIELD blm
    class FEE,ADOPT mid
    class BURN1,BURN2 burn
    class POOL pool
    class KEEP keep
```

**The left branch only ever drains a finite purse; the right branch only ever fills a pool that purse
cannot reach.** That separation is what makes the fee real rather than the Treasury paying itself.

Three ways this could have been faked, all closed in code and tested:

| Hole | Why it mattered | Fix |
|---|---|---|
| `admin == treasury` | An admin can `grantRole(MINTER_ROLE, self)` and refill the Rain — the burn becomes theatre | Keys must be distinct; enforced in the constructor **and** re-checked at deploy |
| Voucher had no expiry | A leaked voucher was claimable forever with no way to rotate it out | `deadline` added to the signed tuple |
| Backend supplied the yield amount | A compromised backend key mints unlimited supply | Formula moved on-chain; the job supplies inputs, never payouts |

Simulating all 3,650 blooms in Foundry ends with the Genesis Rain at **exactly zero** and **904,050
SMILE** in existence — all of it earned, none of it decreed. It is a knife-edge: bloom 3,651 reverts,
and a day skipped and never backfilled leaves dust forever. That makes the backfill job structural.

### 6.1 Two tokens, one letter apart

The system deploys **two different tokens**, and confusing them is the easiest mistake to make when
reading a block explorer. They are not variants of each other — they are different standards doing
different jobs.

| | `0xD88928B5…432Baf7f` | `0x0BBaC39B…4B39b798` |
|---|---|---|
| Name | PixelSlime **Card** | PixelSlime **Smile** |
| Symbol | **SLIME** | **SMILE** |
| Standard | **ERC-721** (non-fungible) | **ERC-20** (fungible) |
| Decimals | none — indivisible | 18 |
| What it is | **the cards themselves** | **the money** |
| Supply | one token per slime, ever | 365,660 and growing |
| Mochibo | `SLIME #1`, owned by the Vault | — |

Read it as a card game: **SLIME is the card you hold, SMILE is the coin you spend.** You cannot own
half a Mochibo; you can own half a SMILE.

Both branches of §6 move **SMILE**. The **SLIME** token is what the anchor mints and what adoption
eventually transfers out of the Vault.

> ⚠️ **Known footgun.** `SLIME` and `SMILE` are anagram-adjacent and easy to misread in logs and
> explorer tabs. This is tolerable on a testnet; renaming the NFT symbol to something unmistakable
> (e.g. `PSCARD`) is on the list before any value-bearing deployment.

### 6.2 How the transactions are signed — and why not Key Vault

The design called for an **Azure Key Vault secp256k1 key**, so the private key would never leave the
HSM. `KeyVaultSigner` is written, tested, and still the preferred path — but it **cannot be used in
this subscription**. The `KeyVault_PublicNetwork_Modify` policy at management-group scope forces
`publicNetworkAccess: Disabled` and reverts any change within seconds, and no private endpoint for
Key Vault was provisioned, so its data plane is unreachable from the app.

Amoy therefore signs with a raw key held in a **Container Apps secret**. That is a real reduction in
security, not an equivalent alternative: anyone with RBAC on the container app can read it. It is
acceptable only because these tokens carry no value.

Rather than leave that as a warning comment for a future reader to respect, the limit is enforced:

```python
if settings.chain_id not in TESTNET_CHAIN_IDS:
    raise SignerError("refusing the in-process LocalSigner ...")
```

Pointing this configuration at a value-bearing chain **fails closed**. Restoring the Key Vault path
means adding a private endpoint for the vault — the VNet that §2 already builds makes that a small
change.

### 6.3 Deployed on Polygon Amoy — live addresses

| Contract | Address | Role |
|---|---|---|
| `SmileToken` | [`0x0BBaC39Bf418ab63BF71802808A4C63D4B39b798`](https://amoy.polygonscan.com/token/0x0BBaC39Bf418ab63BF71802808A4C63D4B39b798) | the $SMILE currency |
| `PixelSlimeCard` | [`0xD88928B55CefcAe756e55824a48342cA432Baf7f`](https://amoy.polygonscan.com/token/0xD88928B55CefcAe756e55824a48342cA432Baf7f) | the SLIME cards |
| `ClaimPool` | `0x02a6887730894E39B437eB0A4AB457d98167Fc0f` | burns the fee, mints the yield |
| `SlimeAdoption` | `0x20d6A4F365d00b4d27726f13093Dc2C497473CcA` | spend $SMILE to adopt |

**Invariants read back off the live chain, not asserted from the source:**

| Check | Expected | Actual |
|---|---|---|
| Genesis Rain in Treasury | 365,000 | ✅ 365,000 at deploy |
| Bloom fee | 100 | ✅ 100 |
| Admin can mint $SMILE | **false** | ✅ `false` |
| Treasury can mint $SMILE | **false** | ✅ `false` |
| ClaimPool can mint $SMILE | true | ✅ `true` |

The two `false` rows are the whole point: **the purse that pays the fee cannot print more of it.**

**PS-0001 Mochibo, verified end to end:**

| | Value |
|---|---|
| Mint tx | [`0x6a1c3c6e…bce6260e`](https://amoy.polygonscan.com/tx/0x6a1c3c6e5879851568bcf934b273aa5979f26de6cd9c248043dae133bce6260e) |
| Block | 43,516,915 |
| Owner | the Vault (Treasury) |
| `cardHash` on-chain | `0xe99e4c83…62e7af0a` |
| `cardHash` from the API | `0xe99e4c83…62e7af0a` — **identical** |
| Bloom tx | [`0xa29bcec7…f6276ac7`](https://amoy.polygonscan.com/tx/0xa29bcec720a3d34c5973c07fb3b186345c4343ca25cbe5ce9e202676f6276ac7) |
| Burned | 100 $SMILE (Treasury → `0x0`) |
| Minted | 760 $SMILE (`0x0` → ClaimPool) = happiness 95 × EPIC ×8 |

After that single bloom: Genesis Rain **364,900**, Claim Pool **760**, total supply **365,660**.

---

## 7. Reading a card, end to end

```mermaid
sequenceDiagram
    autonumber
    participant V as 🌍 Visitor
    participant A as ca-pixelslime-api
    participant I as in-memory index
    participant D as asmDB
    participant P as private endpoint
    participant S as Blob Storage

    Note over A,I: index built at startup, refreshed periodically
    V->>A: GET /api/cards
    A->>I: query, filter, sort, paginate
    I-->>A: page of summaries
    A-->>V: 200 — asmDB never touched on a hot request

    V->>A: GET /api/cards/1/raw
    A->>I: cached card
    A-->>V: the literal Z85 rows + cardHash

    V->>A: GET /api/cards/1/image
    A->>P: blob read
    P->>S: private link
    S-->>P: PNG bytes
    P-->>A: PNG bytes
    A-->>V: 200, Cache-Control immutable, ETag

    Note over A,D: a card whose continuation row is missing is<br/>skipped with a loud log, never a failed startup
```

The gallery is served entirely from an in-memory index mirrored to an `index.json` blob. asmDB remains
the **source of truth**; the index is a rebuildable projection. `FIND` and `RANGE` are full scans in the
engine, so keeping them off the hot path is not an optimisation, it is a requirement.

---

## 8. What it costs

| Item | Monthly |
|---|---|
| Container Apps (scale-to-zero) | ~€5–12 |
| Container Apps Job (30 runs) | < €1 |
| **Private endpoint + private DNS zone** | **~€8** |
| Storage (365 PNG/year) | ~€1 |
| ACR Basic | ~€4 |
| Log Analytics + App Insights | ~€3–6 |
| Key Vault (deployed, unused) | < €1 |
| asmDB · Amoy gas | €0 |
| **Total excluding image generation** | **≈ €22–33** |

The VNet itself is free; only the private endpoint carries a charge. Refusing APIM saved roughly
€45/month and avoided putting an SLA-less component in front of a site meant to publish daily.

---

## 9. Deviations from the plan, and why

| Planned | Built | Why |
|---|---|---|
| Key Vault holds the bearer | Container Apps secret | Policy forces the vault unreachable; a private endpoint for one string was not worth it |
| No VNet | VNet + one private endpoint | Storage is also policy-locked, and the card artwork has no substitute |
| `background=transparent` on the model | White exterior + Pillow flood-fill | The parameter is rejected on `/images/edits`, the only endpoint that accepts a reference image |
| Anchor row stores 8-byte hash prefixes | Full 32-byte hashes, version `0x02` | A prefix cannot address a block explorer, which was the row's entire purpose |
| Single-row card | 1–4 chunked rows | The original design needed 143 bytes for 140 bytes of space |
| Companion stored as text | 6-bit `companion_id` in reserved flag bits | The name was unrecoverable from the stream |

---

<div align="center">

*"A slime is a place, a feeling and a friend, squished together."*

</div>

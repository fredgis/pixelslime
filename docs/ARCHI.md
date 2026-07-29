# 🏗️ ARCHITECTURE — PIXELSLIME as actually deployed

> This describes what is **running**, not what was planned. Where the two differ, the difference is
> explained — usually because reality pushed back. [`PLAN.md`](PLAN.md) holds the reasoning;
> [`RUNBOOK.md`](RUNBOOK.md) holds the operations.

| | |
|---|---|
| Subscription | `<SUBSCRIPTION_ID>` |
| Resource group | `FGI-ASMDBPIXELSMILES` · `swedencentral` |
| Public URL | `ca-pixelslime-api.blackbay-470e05c9.swedencentral.azurecontainerapps.io` |
| Database | asmDB Cloud · `smilesdb` · instance `<ASMDB_INSTANCE>` |
| Chain | Polygon **Amoy** testnet |

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
          JOB["<b>caj-pixelslime-daily</b><br/>Container Apps Job<br/>cron 0 8,9 UTC · Paris-hour guard"]
        end
        subgraph SNETPE["snet-private-endpoints · 10.42.2.0/28"]
          PE["<b>pe-blob</b><br/>private endpoint"]
        end
      end

      MI(["<b>id-pixelslime</b><br/>user-assigned managed identity"])
      ST[("<b>stpixelslime…</b><br/>Blob Storage<br/>cards · thumbs · assets<br/><b>public access DISABLED</b>")]
      ACR["<b>crpixelslime…</b><br/>Container Registry · Basic"]
      OBS["<b>appi-pixelslime</b><br/>App Insights + Log Analytics"]
      KV[("<b>kv-pixelslime…</b><br/>Key Vault<br/><i>deployed but unused —<br/>see section 3</i>")]
    end

    AI["<b>fgi</b> · resource group FGI-AI<br/>gpt-image-2 · gpt-5.6-sol"]
    DB[("<b>asmdb.cloud</b> · smilesdb<br/><b>source of truth</b>")]
    CHAIN["<b>Polygon Amoy</b><br/>PixelSlimeCard · SMILE · ClaimPool"]

    NET -->|HTTPS| API
    API --> MI
    JOB --> MI
    PE -->|private link| ST
    API -->|blob reads| PE
    JOB -->|blob writes| PE
    MI -->|Cognitive Services User<br/>cross resource group| AI
    MI -->|AcrPull| ACR
    MI -->|Blob Data Contributor| ST
    API -->|bearer token| DB
    JOB -->|bearer token| DB
    JOB -->|keccak256 anchor| CHAIN
    API --> OBS
    JOB --> OBS

    classDef net    fill:#FFF6E5,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef app    fill:#8FD3FF,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef job    fill:#7FE3C0,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef ident  fill:#FFD86B,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef data   fill:#FF8FC5,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef model  fill:#C08BFF,stroke:#2B1B4A,stroke-width:3px,color:#FFFFFF
    classDef priv   fill:#FF7A59,stroke:#2B1B4A,stroke-width:4px,color:#FFFFFF
    classDef dim    fill:#E7DCFF,stroke:#8B6FE8,stroke-width:2px,color:#5B4A7D

    class NET net
    class API app
    class JOB job
    class MI ident
    class ST,DB data
    class AI,CHAIN model
    class PE priv
    class ACR,OBS dim
    class KV dim
```

---

## 2. Why there is a VNet at all

The plan had no network. The site is public by design, Container Apps Consumption was enough, and the
whole thing was meant to cost €15–25/month. Two governance policies changed that during deployment.

```mermaid
flowchart LR
    P["<b>Management-group policy</b><br/>MCAPSGovDeployPolicies<br/>KeyVault_PublicNetwork_Modify"]
    KVX["<b>Key Vault</b><br/>publicNetworkAccess forced to Disabled<br/><i>reverted our Bicep in under 10 s</i>"]
    STX["<b>Storage</b><br/>publicNetworkAccess forced to Disabled<br/><i>reverted in 20 s</i>"]

    A["<b>Sidestep</b><br/>secrets move to Container Apps<br/>Key Vault no longer needed"]
    B["<b>Cannot sidestep</b><br/>Storage holds the card artwork<br/>there is no substitute"]
    C["<b>VNet + private endpoint</b><br/>which forces a VNet-injected<br/>Container Apps environment"]
    D["<b>Environment recreated</b><br/>vnetConfiguration is immutable"]

    P --> KVX --> A
    P --> STX --> B --> C --> D

    classDef policy fill:#FF7A59,stroke:#2B1B4A,stroke-width:4px,color:#FFFFFF
    classDef block  fill:#FFD86B,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef ok     fill:#7FE3C0,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A
    classDef work   fill:#8FD3FF,stroke:#2B1B4A,stroke-width:3px,color:#2B1B4A

    class P policy
    class KVX,STX block
    class A ok
    class B,C,D work
```

**What was checked rather than assumed.** Only Storage and Key Vault are restricted. The container
registry (Basic) and Log Analytics both still accept public traffic, so they need no private
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

Transactions are signed by an **Azure Key Vault secp256k1 key** — the private key never leaves the HSM,
and `v` recovery plus low-`s` normalisation are done client-side because Key Vault returns only `(r,s)`.

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

# ACE adapter ecosystem catalog v1

- Date: 2026-08-17
- Status: **planning catalog for the adapter ecosystem lane (E2 / post-1.2); not a commitment**
- Related: [local source adapter architecture](personal-intelligence-local-source-adapters-v1.md),
  the ROADMAP adapter-ecosystem and E2 sections, and issue #195 (ACE 1.2 boundary).

## What this is, and is not

This catalogs the common data sources ACE will want adapters for, with a priority order. It is a
**planning artifact**, not a delivery promise. Two hard rules from the roadmap hold:

- **ACE 1.2 stays scoped to four local formats** (Markdown/Obsidian, PDF, CSV, JSON). Nothing in
  this catalog is 1.2 scope. Adding any of it to 1.2 would break the frozen acceptance gate
  (issue #195).
- **ACE does not promise a universal connector catalog.** Adapters ship as independent, separately
  versioned artifacts, prioritized by demonstrated Solution Bundle need. A bundle binds the
  smallest approved set it requires.

## The three adapter contract shapes

"Data source" is not one kind of thing. An adapter's contract, trust model, and cost depend on how
the source is reached. Getting this split right is what keeps the trust boundary small.

| Shape | What it does | Trust / cost | Owns |
|---|---|---|---|
| **A. Local file adapter** | Parse bytes of one format into a structured document + anchors | Lowest — pure translation, no network, no credentials | Format meaning only. This is what PI2 built (Markdown/CSV/JSON/PDF). The governed local-acquisition port owns walking, read-only enforcement, digesting, admission. |
| **B. Remote document connector** | Pull documents/pages from a networked knowledge system, with incremental sync | Medium — OAuth/token, network, pagination, change detection; **host owns credentials** | Source-specific retrieval + mapping to documents. Produces the same document shape as A downstream. |
| **C. Structured / record connector** | Query records, rows, objects, time series, or events from a database, warehouse, SaaS API, object store, or stream | Highest — credentials, schema awareness, pagination/query cost, rate limits, incremental cursors, entitlement | Bounded translation of records into ACE's Observation contract; **never** authoritative storage. Domain Packs declare what the records mean. |

Cloud (AWS/GCP/Azure) is almost entirely shape **C** (object stores, query engines, catalogs,
streams) with some **B** (drive-like storage). It is never a single over-privileged "cloud adapter"
— each service is a narrow, separately authorized adapter.

Only shape A is covered by the thin-adapter design in
[the local source adapter architecture](personal-intelligence-local-source-adapters-v1.md). Shapes
B and C need the connector contract E2 owns: capability declaration, permission scopes, health,
provenance, replay, incremental cursors, rate-limit and retry policy, and upgrade semantics. That
contract is a prerequisite for everything below shape A.

## Priority tiers

- **P0** — highest common value across personal and organizational Solution Bundles; likely first.
- **P1** — broad value; sequenced after P0 and the shape-B/C connector contract exists.
- **P2** — valuable but narrower, heavier, or dependent on a specific bundle.

Priority is a planning signal, not a schedule.

## Catalog

### Local file formats — shape A (thin adapters)

| Source | Anchor grammar | Parser dependency | Priority |
|---|---|---|---|
| Markdown / Obsidian | heading path | stdlib | **Shipped (1.2, PI2)** |
| PDF | page number | pypdf | **Shipped (1.2, PI2)** |
| CSV | row number | stdlib | **Shipped (1.2, PI2)** |
| JSON | JSON Pointer | stdlib | **Shipped (1.2, PI2)** |
| Plain text / RTF | line/offset | stdlib / minimal | P0 |
| DOCX | heading/paragraph path | python-docx | P0 |
| XLSX | sheet + cell reference | openpyxl | P0 |
| PPTX | slide number | python-pptx | P1 |
| HTML | DOM path / heading | selectolax / stdlib | P1 |
| Parquet / Avro | row group + row | pyarrow / fastavro | P1 |
| Email export (mbox / eml) | message id + part | stdlib (`email`, `mailbox`) | P1 |
| Calendar (iCal / ics) | event UID | icalendar | P2 |
| EPUB | chapter + fragment | ebooklib | P2 |
| Images (OCR) | page/region box | an OCR engine | P2 |
| Audio (transcription) | timecode | a transcription engine | P2 |

### Knowledge & collaboration — shape B (remote document connectors)

| Source | Auth | Priority |
|---|---|---|
| Notion | OAuth | **P0** |
| Google Drive / Workspace (Docs, Sheets, Slides) | OAuth | **P0** |
| OneDrive / SharePoint | OAuth (Microsoft) | **P0** |
| Confluence | token / OAuth | P1 |
| Slack | OAuth | P1 |
| Microsoft Teams | OAuth (Microsoft) | P1 |
| Dropbox / Box | OAuth | P1 |
| OneNote | OAuth (Microsoft) | P2 |
| Obsidian sync / remote vault | token | P2 |
| Discord | token | P2 |

### Developer, product & design — mixed shape B/C

| Source | Shape | Priority |
|---|---|---|
| GitHub (issues, PRs, wikis, discussions) | C | **P0** |
| Jira | C | **P0** |
| Linear | C | P1 |
| GitLab / Bitbucket | C | P1 |
| Figma | C (via authorized adapter) | P1 |
| Product analytics (Amplitude, Mixpanel, PostHog) | C | P1 |
| Sentry | C | P2 |
| Asana | C | P2 |

### Operational SaaS — shape C

| Source | Priority |
|---|---|
| Salesforce | **P0** |
| HubSpot | P1 |
| Stripe | P1 |
| Zendesk / Intercom | P1 |
| ServiceNow | P2 |
| Shopify | P2 |
| Workday / SAP | P2 |

### Databases — shape C

| Source | Priority |
|---|---|
| PostgreSQL (incl. pgvector) | **P0** |
| MySQL / MariaDB | **P0** |
| SQLite | **P0** |
| SQL Server | P1 |
| MongoDB | P1 |
| Elasticsearch / OpenSearch | P1 |
| Redis | P2 |
| Oracle | P2 |
| Neo4j | P2 |
| Vector stores (Pinecone, Weaviate, Qdrant, Milvus) | P2 |

### Warehouses, lakehouses & catalogs — shape C

| Source | Priority |
|---|---|
| Snowflake | **P0** |
| BigQuery | **P0** |
| Databricks | P1 |
| Redshift | P1 |
| dbt (models, docs, lineage) | P1 |
| Iceberg / Delta Lake tables | P2 |
| Hive Metastore / Unity Catalog / enterprise catalogs | P2 |

### Cloud services — shape C, **narrow per-service adapters only**

One over-privileged cloud adapter is prohibited. Each service is a separate, separately authorized
adapter.

| Provider | Object storage | Query / warehouse | Catalog | Event / stream | Logs / metrics | Identity / secrets (host-owned) |
|---|---|---|---|---|---|---|
| **AWS** | S3 (**P0**) | Athena, Redshift (P1) | Glue (P1) | Kinesis, SQS/SNS, EventBridge (P1) | CloudWatch (P1) | IAM/Cognito, Secrets Manager (P2) |
| **Google Cloud** | GCS (**P0**) | BigQuery (**P0**) | Data Catalog (P2) | Pub/Sub (P1) | Cloud Logging (P1) | IAM, Secret Manager (P2) |
| **Azure** | Blob Storage (**P0**) | Synapse, Azure SQL (P1) | Purview (P2) | Event Hubs (P1) | Monitor / Log Analytics (P1) | Entra ID, Key Vault (P2) |

### Streams & change data — shape C

| Source | Priority |
|---|---|
| Kafka | P1 |
| Kinesis / Pub/Sub / Event Hubs | P1 |
| Webhooks (governed intake) | P1 |
| Change data capture (Debezium) | P2 |

### BI, observability & security — shape C

| Source | Priority |
|---|---|
| Grafana / Prometheus / OpenTelemetry | P1 |
| Power BI / Tableau / Looker | P2 |
| Datadog / Splunk / ELK | P2 |

### Public web, feeds & licensed data — shape B/C

| Source | Notes | Priority |
|---|---|---|
| HTTP / HTML pages | already the LIVE HTTPS acquisition path | **P0** |
| RSS / Atom feeds | change-friendly | P1 |
| REST / GraphQL APIs (generic) | schema-declared | P1 |
| Sitemaps / crawl (bounded) | robots + rate policy | P2 |
| Research / regulatory / licensed feeds | quotation, retention, redistribution policy per source | P2 |

## Sequencing recommendation

1. **Prove the connector contract (shapes B and C)** on one P0 remote source before breadth — the
   1.2 packet's "one remote knowledge source after the local journey passes" is the natural first
   step (Notion, Google Drive, or OneDrive).
2. **Grow the shape-A local formats** (DOCX, XLSX, plain text) — cheap, they reuse the thin-adapter
   design and the governed acquisition port unchanged.
3. **P0 structured connectors** where object storage and warehouses dominate demonstrated need
   (S3, GCS, Blob, BigQuery, Snowflake, Postgres, GitHub, Salesforce).
4. Everything else by demonstrated Solution Bundle need.

Governance invariants apply to every entry: credentials stay host-owned, each adapter declares its
exact permission scope, provenance and replay are preserved, entitlement and retention policy are
enforced, and no adapter becomes authoritative durable storage.

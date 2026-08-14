# ACE 1.0 Personal Intelligence OS public release closeout

Status: **public, passed**  
Acceptance date: 2026-08-14  
Recommended Core patch: `ace-core==1.0.3`

## Release promise

ACE 1.0 is the stable single-user Intelligence Operating System for one local owner and the
documented single-node deployment. Atrium guides Intelligence selection, exact source review and
binding, permission/readiness checks, activation, ingestion health, and a continuously updating
cited Brief. ACE prepares governed direction packages for downstream engines; it does not recreate
or silently operate those engines.

## Public coordinates

| Component | Public identity | SHA-256 |
|---|---|---|
| Core wheel | `ace_core-1.0.3-py3-none-any.whl` | `ef3184a8c9705cd4767f9fc8f788789b9200826ce6dbcde224d4e79ec7766a72` |
| Core source archive | `ace_core-1.0.3.tar.gz` | `800971e01d67ecb29602a40f2b225bb42141bca662e04dda82ff9f1fe4a45ba3` |
| World wheel | `ace_domain_world_intelligence-0.13.0-py3-none-any.whl` | `5b55c7b4bb35931c389f12684b1d8a7c8960d731bfbccd654608fef7eeaabc6c` |
| Market wheel | `ace_domain_market_intelligence-0.8.0-py3-none-any.whl` | `1ff39169a275c47b6338158f4b41eb3723be4f5447c404aab01773ae6d4a3df3` |
| World trusted Builder wheel | `ace_app_world_ai_builder-0.2.0-py3-none-any.whl` | `b4433483979fa2a519dd47644ab4de81bdeff1657c04c606800744f7a8953c86` |
| Market trusted Builder wheel | `ace_app_market_intelligence_builder-0.1.0-py3-none-any.whl` | `597463409c30ec81b395dcfa0d5422c554da51203cbd656ba958790eb5f1ac19` |
| World source adapter wheel | `ace_ext_world_federal_register_source-0.4.1-py3-none-any.whl` | `d023285dbd6ee5b6c4d9daf41769bf5f5fd465ee314b873f83b2742387834091` |
| Reference action adapter wheel | `ace_reference_workspace_action-0.4.1-py3-none-any.whl` | `077a6ab0f9a21902a2250a1af3482c6c3794be54db6d620de79f91ff576c7263` |

Core release: <https://github.com/augmented-cognition-engine/core/releases/tag/v1.0.3>  
Core merge: `bf515d3aeab1aa7e59316bf61376c86bc154228a`  
World release: <https://github.com/augmented-cognition-engine/domain-world-intelligence/releases/tag/v0.13.0>  
Market release: <https://github.com/augmented-cognition-engine/domain-market-intelligence/releases/tag/v0.8.0>

The installed database schema is v177. The supported thin MCP surface remains exactly eleven
tools. World and Market remain separately versioned Solution Bundles; their inert packs grant no
execution or source authority, and their trusted Builders must be installed explicitly.

## Acceptance receipts

- **Publication and installation.** All Core 1.0.3 publication jobs passed. A fresh isolated Python
  3.12 environment installed the exact public Core wheel plus public World 0.13.0 and Market 0.8.0
  artifacts without a source checkout. The streamed wheel hash matched PyPI metadata exactly.
- **Clean service and owner continuity.** The public 1.0 line launched against a schema-zero-to-v177
  isolated database. Local-owner bootstrap created four fixed, verified build/read grants. After a
  process restart, protected read returned HTTP 200, the same four grants remained verified, and a
  canonical personal-Intelligence export was authorized. Core 1.0.1 and 1.0.2 fixed the two JSON
  round-trip defects found by this clean acceptance; 1.0.3 contains both corrections.
- **Provider route.** `ace doctor --live-provider` passed through the signed-in Codex subscription
  route, alongside database, schema, API, authentication, and eleven-of-eleven MCP checks. ACE also
  supports direct OpenAI/Anthropic API keys, a signed-in Claude CLI route, OpenAI-compatible
  endpoints, and local Ollama. A consumer subscription is never converted into an API key.
- **Recovery and ownership.** Backup manifest verification and restore into a clean namespace and
  database passed. The backup was 410,898 bytes with digest
  `sha256:054012363fad107b2c05873c44aa1d0d5018db2ac3a6c05196d9940c53321308`;
  restore reported schema v177 and `target_was_clean=true`. Export passed. Empty-install deletion
  preview correctly refused with HTTP 409 because no removable records existed; released
  integration coverage proves the required two-step delete path.
- **Quiet sustained runtime.** The sustained public 1.0.2 run revealed a non-fatal heartbeat read
  against the retired `product_map` table. Core 1.0.3 aligns that read to canonical `theme` state.
  All six required CI jobs passed, 41 focused Conductor/release tests passed, the exact public wheel
  contains no retired-table reference in the query, and the exact query returned an empty success
  result against the preserved schema-v177 database.
- **Continuously updating Brief.** Released Core coverage proves first cited Brief, restart/reopen,
  later recorded source revision, append-only Brief revision, retained prior Brief, semantic
  what-changed/why/evidence diff, and grounded Ask/correction through the same resource path used by
  World and Market.
- **Activation, handoff, and outcome return.** Market 0.8.0 proves a content-addressed direction
  package from an exact Brief/Decision, separate approval for exact package and destination,
  acknowledged reference delivery, later Outcome, and proposal-only Feedback. Delivery and
  Feedback never grant themselves authority or become effective automatically.

## Retrieval and verification evidence

The frozen provider-free RAG evaluation passed 5/5 cases with Recall@5 100%, MRR 1.0, and zero
false-association, isolation, correction, or no-answer violations. Exact SurrealDB 3.2.3 plans
verified indexed lexical `FullTextScan` and HNSW `KnnScan`. Focused implementation and contract
regression passed 93 tests before integration; the reconciled release branch passed 95 focused RAG
and contract tests, 92 authority/onboarding/public-contract conflict tests, two fresh database RAG
lifecycle tests, lint, formatting, diff checks, and the full required Core CI matrix.

World release verification recorded 149 passed with one intentional skip plus a focused 107-test
v1 lane. Market release CI passed its pack, Builder, direction-package, handoff, outcome-return,
artifact, and compatibility gates. These are bounded conformance and recorded-source results, not
claims of customer-corpus relevance or general intelligence quality.

## Explicit boundaries

ACE 1.0 does not claim a universal connector or destination catalog, managed hosting,
collaboration or tenant isolation, hostile-extension sandboxing, autonomous source authorization,
autonomous delivery or policy application, arbitrary web access, customer-corpus relevance,
multilingual quality, high-concurrency operation, distributed availability, calibrated real-world
causal accuracy, or general beneficial impact.

Personal sources such as Obsidian, Notion, OneDrive, CSV, Snowflake, AWS, and GCP belong in
Solution Bundles that bind exact source adapters, permissions, swimlanes, applications, outcome
mappings, and conformance fixtures over the same substrate. Personal Intelligence is therefore a
product experience and bundle composition, not a new Core ontology. A universal connector catalog
is explicit post-1.0 work.

Supply chain remains a non-product, non-blocking portability falsifier under the accepted World +
Market release matrix. A full supply-chain product is post-1.0.

## Release disposition

All bounded 1.0 blockers are satisfied. `ace-core==1.0.3` is the recommended stable patch and the
1.0 milestone is **passed**.

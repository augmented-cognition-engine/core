# Productized State public journey receipt v1

Status: **passed — Productized State passed; K1 passed, K2 passed, K3 passed**

Acceptance hash: `023dd9147e2f97227be12a7ad8bc13e3266389ca59cbe3c9c32063b67949f83c`
Frozen config SHA-256: `7916f0f7566e74a9b1981210e3e710ceb5876e9874369ed18f9abc8c1c1cdbd3`
Frozen corpus SHA-256: `85907acc8ad5b9a73d2d7551ced98d1bb26d4b9ea51a189d262675cb5ff9ea28`

## Exact supported journey

| Step | Product-builder action | Result |
|---:|---|---|
| 1 | install and discover ACE plus product extension | passed |
| 2 | ingest bounded public-safe temporal corpus through Product State API | passed |
| 3 | replay ingestion and reconcile identity, lineage, counts, and scope | passed |
| 4 | freeze five-meaning as-of belief projection | passed |
| 5 | challenge and review inspectable transition hypothesis | passed |
| 6 | compare action, no-action, and named alternative rollouts | passed |
| 7 | persist structured decision and I3 use receipt | passed |
| 8 | capture and reconcile incomplete then matched later outcomes | passed |
| 9 | accept correction and append-only supersession lineage | passed |
| 10 | restart database, API, and worker; invoke fresh thin client | passed |
| 11 | exercise honest failure and degraded cases | passed |
| 12 | inspect the integrated receipt chain through the Living Product Graph | passed |
| 13 | reverify unchanged eleven-tool public MCP boundary | passed |

The separately installed `ace-ext-fjord-operations` package was discovered through
the `ace.extensions` entry point. Core retained product scope, identity, validation, persistence,
review authority, task lifecycle, and receipts. The extension supplied the fictional product
mapping and action registration.

## Evidence identities

- ingestion manifest: `grounded_ingestion_manifest:8e456e7907e4eaf6d04b126fc5ca5d90` / `8e456e7907e4eaf6d04b126fc5ca5d90d7ed57bcacb23091d47717d37bb4c3f5`
- belief projection: `grounded_belief_projection:2c10f0093b416ec468c3d550c77e75e8` / `2c10f0093b416ec468c3d550c77e75e8eca6ab928458334ae305a53ada413c00`
- transition revision: `grounded_transition_revision:36d6f891a1c60177207b6891065b1869` / `36d6f891a1c60177207b6891065b18693db0a9f155e8edb3fdbd0a062c0948ca`
- rollout revision: `grounded_rollout_revision:fe6f41832064ec8c03429a0d0170b462` / `fe6f41832064ec8c03429a0d0170b462d5a59b22803afc05e807a9df7780538f`
- decision receipt: `decision:0epxpvc4enseeul7obnn`
- I3 receipt: `grounded_reasoning_use:419e941ae1884dc3a91433a0ea3fc4e5`
- matched reconciliation: `grounded_rollout_reconciliation:f9db0c4fc4c31383ece0a8e30dfd2781` / `f9db0c4fc4c31383ece0a8e30dfd2781f1e90099bd14c45e46931a43703dccf4`
- initial promotion: `grounded_promotion_receipt:c1db4ef5ce20c9a9dfd27bd8006ef846`
- correction promotion: `grounded_promotion_receipt:015c6229a4bf81138439d9111fe44d9d`

Belief states: `contested`, `provisional`, `superseded`, `supported`, `unknown`.
Rollout branches: `action`, `alternative`, `no_action`.

## Productized State surface

- ingestion: `POST /product-state/ingestions` / `ace.product-state.ingestion/v1`
- installed extension: `fjord-operations` /
  `0.1.0`
- integrated snapshot: `product_snapshot:5304a980955d08390cbd2b506ba77b4c2ad927277a3841e4a9f99cf0623b0dea`
- inspection counts: 1 ingestion, 1 belief,
  2 transition, 6 reasoning-evidence,
  2 material-use, 2 rollout, and
  2 promotion receipts
- task attribution: 8 decision,
  9 deliberation, and
  9 intelligence-use receipts

The snapshot is read-only. It does not turn a hypothesis into causal fact, a simulation into an
observation, material influence into beneficial impact, or a model proposal into authority.


## Failure and degraded cases

| Case | Gate | Observed behavior |
|---|---|---|
| `unavailable_evidence` | passed | foreign-scope query returned an explicit empty bounded evidence pack |
| `unsupported_causality` | passed | causal transition acceptance requires human authority |
| `product_isolation` | passed | foreign task read returned 404 and foreign evidence/memory reads returned no rows |
| `stale_state` | passed | stale transition revision remained non-applicable with transition_stale degradation |
| `restart_interruption` | passed | interrupted attempt degraded after restart and resumed as an immutable successor |
| `incomplete_reconciliation` | passed | missing observed assignment remained unresolved and unscored |

## Resource and provider use

- schema-zero migration: 28.715 s;
  v168→v171 upgrade:
  0.944 s
- first full restart: 3.262 s;
  interruption restart: 2.783 s
- task latency p95: 306.577 ms
- store bytes at closeout: 2932418
- provider route/model: `deterministic-provider-free-acceptance` / `provider-free-v1`
- calls/tokens/retries/cost: 0 / 0 /
  0 / $0.00

## Limitations

- bounded single-node database, API, worker, and synchronous adapter clients only
- fictional public-safe product data; no real-world causal-accuracy claim
- provider-free execution; no hosted-model latency or quality claim
- material I3 influence is demonstrated but beneficial impact is not
- trusted installed Python extensions execute in-process; hostile-code sandboxing is not claimed
- no distributed ordering, multi-writer, multi-region, autonomous-learning, or general-world-model claim

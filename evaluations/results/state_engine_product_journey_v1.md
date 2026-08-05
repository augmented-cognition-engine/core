# State Engine K1-K3 product journey receipt v1

Status: **passed — K1 passed, K2 passed, K3 passed**

Acceptance hash: `d81257a0e379c20248cb546b61b57d18c5ed440950d003733140310f83713e85`
Frozen config SHA-256: `7ac1470fd05727b31b794783c40e7afe9aafaa1b628614b8f4f21d72df151a4c`
Frozen corpus SHA-256: `85907acc8ad5b9a73d2d7551ced98d1bb26d4b9ea51a189d262675cb5ff9ea28`

## Exact supported journey

| Step | Product-builder action | Result |
|---:|---|---|
| 1 | install and discover ACE plus product extension | passed |
| 2 | ingest bounded public-safe temporal corpus | passed |
| 3 | replay ingestion and reconcile identity, lineage, counts, and scope | passed |
| 4 | freeze five-meaning as-of belief projection | passed |
| 5 | challenge and review inspectable transition hypothesis | passed |
| 6 | compare action, no-action, and named alternative rollouts | passed |
| 7 | persist structured decision and I3 use receipt | passed |
| 8 | capture and reconcile incomplete then matched later outcomes | passed |
| 9 | accept correction and append-only supersession lineage | passed |
| 10 | restart database, API, and worker; invoke fresh thin client | passed |
| 11 | exercise honest failure and degraded cases | passed |
| 12 | reverify unchanged eleven-tool public MCP boundary | passed |

The separately installed `ace-ext-fjord-operations` package was discovered through
the `ace.extensions` entry point. Core retained product scope, identity, validation, persistence,
review authority, task lifecycle, and receipts. The extension supplied the fictional product
mapping and action registration.

## Evidence identities

- ingestion manifest: `grounded_ingestion_manifest:8e456e7907e4eaf6d04b126fc5ca5d90` / `8e456e7907e4eaf6d04b126fc5ca5d90d7ed57bcacb23091d47717d37bb4c3f5`
- belief projection: `grounded_belief_projection:a9cd08c8f2e927058566ab74c49f239b` / `a9cd08c8f2e927058566ab74c49f239b7c0cc1790e122f737d6ddb206776f599`
- transition revision: `grounded_transition_revision:2c232a03cf15fb4bbfe989f29b732707` / `2c232a03cf15fb4bbfe989f29b7327078470cb3a11c1f85a31bbb91ab9eebbe1`
- rollout revision: `grounded_rollout_revision:0d820541a87dacd09fb003b3997caa90` / `0d820541a87dacd09fb003b3997caa908367cd64a49679f8f241982787d09496`
- decision receipt: `decision:se4rqgl8ekq2qx3qg5t7`
- I3 receipt: `grounded_reasoning_use:6eaadbf8d1e6ca5108ae8ebcd835eeb1`
- matched reconciliation: `grounded_rollout_reconciliation:0c3dd8965ec3d76ac29c670f3eb9e0f1` / `0c3dd8965ec3d76ac29c670f3eb9e0f1c504bff69feb614c431f42d2e4bf1fe4`
- initial promotion: `grounded_promotion_receipt:f1fc69d93efc81bcb104db79bb243866`
- correction promotion: `grounded_promotion_receipt:c139a12f4061703a199d2b927ae01bdc`

Belief states: `contested`, `provisional`, `superseded`, `supported`, `unknown`.
Rollout branches: `action`, `alternative`, `no_action`.

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

- schema-zero migration: 33.902 s;
  v160→v168 upgrade:
  6.277 s
- first full restart: 2.824 s;
  interruption restart: 2.004 s
- task latency p95: 95.303 ms
- store bytes at closeout: 2888756
- provider route/model: `deterministic-provider-free-acceptance` / `provider-free-v1`
- calls/tokens/retries/cost: 0 / 0 /
  0 / $0.00

## Limitations

- bounded single-node database, API, worker, and synchronous adapter clients only
- fictional public-safe product data; no real-world causal-accuracy claim
- provider-free execution; no hosted-model latency or quality claim
- material I3 influence is demonstrated but beneficial impact is not
- no distributed ordering, multi-writer, multi-region, autonomous-learning, or general-world-model claim

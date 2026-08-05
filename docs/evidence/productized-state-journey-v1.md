# Productized State public-journey evidence v1

Status: **engineering acceptance passed on 2026-08-05; public artifact release pending**

This record closes the implementation and reproducible-journey portion of the 0.3.x Productized
State milestone. It does not claim that the branch has been merged or that a new ace-core artifact
has been published. The authoritative machine receipt is
[`evaluations/results/productized_state_journey_v1.json`](../../evaluations/results/productized_state_journey_v1.json),
with a human rendering in the paired Markdown file.

## Frozen identities

| Material | Identity |
|---|---|
| Acceptance | `productized-state-public-journey-v1` |
| Config SHA-256 | `7916f0f7566e74a9b1981210e3e710ceb5876e9874369ed18f9abc8c1c1cdbd3` |
| Corpus SHA-256 | `85907acc8ad5b9a73d2d7551ced98d1bb26d4b9ea51a189d262675cb5ff9ea28` |
| Acceptance hash | `023dd9147e2f97227be12a7ad8bc13e3266389ca59cbe3c9c32063b67949f83c` |
| Extension | `ace-ext-fjord-operations` 0.1.0 / `fjord-operations` entry point |
| Ingestion contract | `ace.product-state.ingestion/v1` |
| Inspection contract | `ace.product-state.inspection/v1` |
| Schema | zero→v171; v168→v171 upgrade |
| Provider | `deterministic-provider-free-acceptance` / `provider-free-v1` |

## What passed

- The example extension wheel clean-installed and published its exact adapter/version manifest plus
  two bounded actions through the ordinary `ace.extensions` boundary.
- Authenticated `POST /product-state/ingestions` supplied the product scope that the extension could
  not override. Five input items produced one immutable batch receipt, 22 stable semantic records,
  exact replay, reconciled counts, one source-version lineage edge, and empty foreign scope.
- The State Engine produced all five required belief meanings, a challenged and reviewed transition
  hypothesis, action/no-action/alternative branches, a structured decision, I2 deliberation, I3
  material use, outcome reconciliation, promotion, and correction supersession.
- Real database/API/worker processes restarted twice. Fresh client processes materially used the
  promoted conclusion and then the corrected authoritative material.
- The Living Product Graph used the authenticated typed product record and exposed 1 ingestion
  receipt, 1 belief projection, 2 transition revisions, 6 reasoning-evidence packs, 2 reasoning-use
  receipts, 2 rollouts, 2 promotion receipts, and task-level I1/I2/I3 attribution.
- Schema zero reached v171 and a frozen v168 predecessor upgraded through the three governed-
  cognition migrations while preserving its sentinel.
- Unavailable evidence, unsupported causal authority, foreign-product reads, stale transition
  state, restart interruption, and incomplete reconciliation failed or degraded honestly.
- The thin MCP surface remained exactly eleven tools. No State Engine MCP tool was added.

## Productization defect found and corrected

The real journey exposed a gap hidden by the prior fake-store G1 tests: the Living Product Graph
passed `product:<id>` to SurrealDB as a plain string and then cast it inside the query. With the real
driver/database pair, valid product-scoped rows were returned as empty collections. The store now
binds a typed driver `RecordID` for every product-scoped query. A real disposable-store check then
returned the complete receipt families above; unit tests also assert the typed authenticated scope.

## Measured run

| Observation | Value |
|---|---:|
| End-to-end duration | 82.061 s |
| Schema zero v171 | 28.715 s |
| v168→v171 upgrade | 0.944 s |
| Maximum restart | 3.262 s |
| Task latency p95 | 306.577 ms |
| Store bytes | 2,932,418 |
| Provider calls / tokens / retries / cost | 0 / 0 / 0 / $0.00 |

## Release boundary

The implementation and frozen public journey pass, but publication remains incomplete until the
candidate is reviewed, merged, included in a versioned artifact, installed from the public index in
a clean environment, and reconciled with issue #2 and the public Project. Until then the published
ace-core 0.3.0 capability page remains authoritative for released users.

The claim is limited to a bounded single-node topology, synchronous adapters, trusted installed
Python extensions running in process, and fictional public-safe data. It does not establish hostile-
code isolation, distributed guarantees, real-world causal accuracy, hosted-model quality,
autonomous learning, general-world-model behavior, or beneficial impact.

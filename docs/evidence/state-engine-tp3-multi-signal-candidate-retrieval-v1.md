# ACE State Engine TP3 multi-signal candidate retrieval v1

Status: **implemented and acceptance-verified; K1–K3 remain not ready**

This record closes TP3 with a provider-neutral, deterministic, bounded candidate finder shared by
grounded evidence retrieval and Cognify. It identifies plausible association candidates and records
why they ranked. It does not accept semantic relationships, project an as-of belief state, learn
dynamics, simulate consequences, promote evidence into memory, or establish beneficial impact.

## Core contract and boundary

[`core/engine/candidates.py`](../../core/engine/candidates.py) defines immutable, extra-forbid v1
contracts for candidate records, explicit filters, requests, index snapshots, signal contributions,
ranked results, and receipts. The provider-free finder combines six versioned signals:

- lexical token overlap;
- local or supplied vector similarity;
- canonical-entity overlap;
- temporal proximity or interval overlap;
- graph-neighborhood overlap; and
- independent-source diversity, applied only when another relationship signal is present.

Inputs are product-scoped and bounded to 200 indexed records, 4,096 vector dimensions, 200 graph
references, and `k <= 50`. Snapshots and requests normalize unordered material before deriving stable
identities. Ranking has deterministic tie-breaks and makes no network, database, or model call. A
canonical-entity conflict with no declared graph bridge is a general negative gate: lexical overlap
or coincident timing alone cannot manufacture an association. Domain record kinds remain filterable
facets and do not receive ranking weight.

Each internal receipt carries the request and snapshot identities, exact filter, requested `k`,
candidate cap, temporal window, index versions, requested/applied/unavailable signals, fallback
reasons, product/explicit/zero-score filtering counts, score-cap and return-cap omissions, every
returned signal contribution, and zero primary-model calls. Validators require all filtering and cap
counts to reconcile. Unknown time may remain eligible through non-temporal signals, but its temporal
contribution is zero, unapplied, and explicitly marked `unknown_time_not_scored`.

[`core/engine/grounded_state/retrieval.py`](../../core/engine/grounded_state/retrieval.py) adapts the
TP2 source, entity, alias, claim, event, participant, relation, and failure records into the shared
contract. It enriches graph neighborhoods bidirectionally from canonical entities, aliases, event
participants, and evidence-relation endpoints, retains product fences, and fails closed rather than
silently truncating an oversized product. This service is internal and read-only.

Cognify now uses the same finder for its bounded existing-insight candidates, requesting lexical and
vector signals over the already product- and discipline-scoped set. Its optional structured model
relationship judgment remains a separate later step. Deterministic generation therefore cannot be
confused with model acceptance. No public endpoint or MCP tool was added; the supported thin MCP
contract remains exactly eleven tools.

TP3 required no migration. It reads the TP2 v163 substrate and creates reproducible in-memory
snapshots and receipts without persisting a new authoritative record class. Schema head remains
v163, with no backfill or write to observation, insight, or operational relationship tables.

## Frozen evaluation

The target configuration
[`state_engine_tp3_candidate_retrieval_v1.json`](../../evaluations/fixtures/state_engine_tp3_candidate_retrieval_v1.json)
was frozen before the first implementation execution. It binds corpus hash
`4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09`, seed `1729`, `k=20`, at
least 95% recall, a top-10 false-association ceiling of 10%, a 200-record/query cap, three declared
ablations, and zero provider calls, tokens, or spend.

The first implementation run honestly failed one predeclared target: it found all 38 directed gold
neighbors but admitted 3 of 6 negative controls, a 50% false-association rate. Its material outcome
hash was `92418e69f2ae90e3acf9eca4a9cc17f050c97b4e4fe15e023610845d6cf706d1`. The general entity-conflict
policy above was then added without editing the corpus, expected neighbors, controls, target, or
budgets.

The unchanged frozen evaluation now records:

| Measure | Result |
|---|---:|
| Indexed evidence occurrences | 62 |
| Directed gold-neighbor queries | 38 |
| Gold neighbors found at `k=20` | 38 |
| Candidate recall | 100% |
| Mean reciprocal rank | 1.000 |
| Directed negative controls | 6 |
| False associations in top 10 | 0 |
| False-association rate | 0% |
| Primary model calls | 0 |

The full material outcome hash is
`79b3007be96e4959349930ad867f23086215fb7840d487dfe0ca18ba45511ccd`.
Removing vector, entity, or temporal scoring individually retains 100% recall and MRR 1.0, while the
recorded mean contribution of the removed signal is respectively 0.602, 1.000, and 0.719. This small
corpus has redundant signals; the ablations demonstrate attribution, not that any signal is
unnecessary at scale. The vector-absent fallback receipt
`candidate_receipt:bafb644655988716adf65e7caaff2f1b` explicitly names the unavailable index and
continues within the same bound with zero provider calls. The complete machine result is
[`state_engine_tp3_candidate_retrieval_v1.json`](../../evaluations/results/state_engine_tp3_candidate_retrieval_v1.json).

## Restart, isolation, and verification

A real disposable SurrealKV acceptance test ingests the complete eight-kind TP2 item, obtains a TP3
candidate receipt, stops and restarts the database, opens a fresh client and service, and obtains the
identical receipt. A request for the same record under another product fails closed. The acceptance
also makes vector-index absence visible and confirms zero primary-model calls.

Verification on 2026-08-03 used source revision
`6b6342f65224ca0c3db2f38c3bc141a58de9e8ea`, CPython 3.12.13, pytest 9.0.3, and SurrealDB 3.2.1.
All TP3 evaluation and acceptance paths were provider-free.

- Ruff lint and format checks over every TP3-touched Python path: passed.
- Focused candidate, Cognify, and grounded-state regression lane: 26 passed and 2 deselected in 1.63
  seconds.
- Disposable SurrealKV TP3 restart and product-isolation acceptance: 1 passed in 3.80 seconds.
- Combined TP0–TP3 contract, frozen-result replay, migration, roadmap, package-identity,
  kernel-boundary, and exact eleven-tool surface lane: 129 passed and 2 deselected in 4.24 seconds.
- Explicit extension-disabled naked-kernel, kernel-boundary, and empty-candidate lane: 6 passed and 1
  expected built-in-discovery skip in 1.24 seconds.
- Complete extension-disabled, non-E2E compatibility suite: 6,753 passed, 47 skipped, and 249
  deselected in 514.45 seconds; zero failures.

The complete suite reported 28 warning instances from existing Starlette/FastAPI/websocket
deprecations, pytest collection of two model classes, short fixture JWT key length, and unawaited
test-mock coroutine paths. No TP3 warning or failure was suppressed. The disposable acceptance
applied v163 twice before ingestion and released its temporary database after the test.

The first implementation collection attempt exposed a packaging cycle because a shared Core module
was re-exported through the grounded-state package that it imported for temporal contracts. The
convenience re-export was removed; direct module imports preserve the dependency direction. No
failure was hidden. The first frozen scoring run's negative-control failure is likewise retained
above and in the generated report.

No live provider, paid model call, customer/private/production data, historical backfill, commit,
push, publication, pull request, hosted-service mutation, or deployment occurred. The frozen TP0
corpus, expected labels, and predeclared TP3 target were not edited. Compose/container execution was
not run for TP3.

## Honest limit after TP3

The 62-occurrence evaluation proves deterministic bounded retrieval behavior on the frozen TP0
reference corpus. It does not establish throughput or retrieval quality for the full 182,315-record
OLC corpus, production index availability, multilingual or learned embedding quality, relationship
truth, belief resolution, causal acceptance, transition learning, calibrated rollout accuracy, or
beneficial decision impact. The single-signal ablations do not reduce recall because the fixture is
small and redundant; larger independent corpora remain necessary before scale claims.

TP4 and later packets remain untouched. T1 remains `not ready`; K1, K2, and K3 remain `not ready`.

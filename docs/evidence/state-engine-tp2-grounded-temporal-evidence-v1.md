# ACE State Engine TP2 grounded temporal evidence v1

Status: **implemented and acceptance-verified; K1–K3 remain not ready**

This record closes the TP2 capability packet: ACE can persist, replay, and inspect bounded,
product-scoped temporal source evidence through a Core-owned grounded-state plane without turning
source claims into cognitive-memory observations or insights. It also supplies the persistence
matrix that TP0 deliberately deferred. The frozen TP0 corpus, its expected labels, and its zero-write
current-runtime baseline are unchanged.

TP2 is an evidence substrate. It is not an as-of belief projection, candidate-retrieval engine,
dynamics model, consequence simulator, promotion path, beneficial-impact result, or K1 completion.

## Architecture and ownership boundary

The provider-neutral v1 contracts live in
[`core/engine/grounded_state/ingestion_contracts.py`](../../core/engine/grounded_state/ingestion_contracts.py).
They are immutable, extra-forbid contracts for source records, canonical entities, retained raw
aliases, source-attributed claims, events, event participants, cheap evidence relations, extraction
failures, supersession lineage, bounded manifests, item receipts, and batch receipts.

Core derives product-scoped record identities, exact idempotency keys, and canonical hashes from
validated material. Product, external source identity, source version, record kind, stable local
identity, content hash, source/provenance material, and temporal semantics participate where
applicable. Delivery-time ingestion metadata does not manufacture a new semantic identity. Unknown
event time remains `unknown` with no substituted occurrence timestamp, while occurrence/valid,
publication, ingestion, and extraction times remain distinct.

[`core/engine/grounded_state/ingestion.py`](../../core/engine/grounded_state/ingestion.py) owns the
bounded, provider-free ingestion lifecycle. It validates each manifest item atomically, resolves
item-local references in two deterministic passes, writes dependency-ordered records in bounded
chunks, and accounts for accepted, duplicate, superseding, rejected, failed, and persisted inputs.
A malformed item is rejected without making a valid sibling unaccountable. If a process dies after
a semantic write but before its receipt, exact replay reconstructs the receipt from the stable
record and creates no second semantic record.

[`core/engine/grounded_state/persistence.py`](../../core/engine/grounded_state/persistence.py) owns
append-only writes and product-fenced reads. Exact replay returns the existing record; semantic
drift under the same authoritative identity fails closed. Changed versions and same-version
extraction corrections create new immutable records plus dedicated supersession-ledger entries.
Late arrival of an older version reconciles the same successor/predecessor lineage without
rewriting either record.

Migration
[`v163_grounded_temporal_evidence.surql`](../../core/schema/v163_grounded_temporal_evidence.surql)
adds eleven append-only, product-scoped tables: eight semantic record tables, one supersession
ledger, and item and batch receipt tables. Updates and deletes are denied. Exact-replay, lineage,
entity-binding, failure, and receipt indexes are additive. The migration does not alter, backfill,
or write `observation`, `insight`, or their relationship tables.

The existing E1 registry now accepts a bounded grounded-state adapter registration. Extensions may
propose extracted material and optional entity resolution, but receive no persistence callback and
cannot choose the manifest product, authoritative Core IDs, hashes, receipt semantics, or lifecycle.
Core does not import a domain extension. The small fixture-backed
[`OLCStyleReferenceAdapter`](../../extensions/reference/grounded_state_adapter.py) lives outside Core,
retains raw aliases and missing-time semantics, represents extraction failures, and performs zero
primary-model calls. It proves the seam against a bounded TP0-derived slice; it does not claim that
the 182,315-record OLC corpus is ready for import. Generic extension scaffolds deliberately omit
this OLC-specific adapter.

No public endpoint or MCP tool was added. The supported thin MCP contract remains exactly eleven
tools, and `ACE_DISABLE_EXTENSIONS=1` leaves the grounded-state adapter registry empty.

## Acceptance matrix

| Requirement | Evidence |
|---|---|
| Exact replay | A fresh service after a real SurrealKV stop/start returns the identical stable batch receipt, IDs, counts, and semantic row counts; persisted records and lineage edges increase by zero |
| Manifest duplicate | A different manifest containing the same eight semantic records reports eight duplicates and zero persisted records |
| Changed source version | v2 creates a distinct record and an explicit supersession edge to retained v1 evidence |
| Extraction correction | Changed content under v2 creates another immutable record and append-only correction lineage; v1 and the first v2 remain inspectable |
| Arrival-order convergence | Manifest record order normalizes to one manifest identity, and v2-before-v1 delivery converges to the same version lineage |
| Count reconciliation | Receipts reconcile every item and all eight semantic kinds: source, entity, alias, claim, event, participant, cheap relation, and extraction failure |
| Partial rejection | An eight-record malformed item persists nothing; in a two-item batch its valid sibling persists and both dispositions reconcile |
| Interruption recovery | A semantic source written without an item receipt is recovered as one duplicate on replay; the next replay returns the same receipt |
| Temporal honesty | Unknown occurrence time reloads as unknown; occurrence, publication, ingestion, and extraction timestamps reload as four distinct values |
| Alias ownership | The raw `Orchid` surface form remains queryable and binds only to its product-scoped canonical entity |
| Degraded evidence | A bounded extraction failure and its degraded reason remain queryable after restart |
| Product isolation | Foreign-product reads fail closed for all eight semantic kinds, item and batch receipts, and supersession entries; identical foreign material receives different IDs |
| Plane separation | Observation and insight row counts are identical before and after the TP2 pilot; ingestion never invokes the TP1 synthesizer or promotion path |
| Causal restraint | The contract accepts only `mentions`, `participates_in`, `precedes`, `reacts_to`, and `co_occurs`; `causes` is rejected |
| Provider independence | Batch and reference-adapter receipts report zero primary-model calls; no provider path is imported or invoked |
| Extension boundary | The reference adapter registers through E1; the naked-kernel lane has no grounded-state adapter; generic scaffolds contain no OLC code |
| Migration safety | Migration lint and safety pass; v163 applies twice in a fresh disposable database; a schema-zero API start applies through v163 |
| Restart continuity | Disposable SurrealKV preserves semantic IDs, timestamps, lineage, failures, receipts, and isolation; a new client replays with zero semantic writes |

## Verification

Verification on 2026-08-03 used source revision
`6b6342f65224ca0c3db2f38c3bc141a58de9e8ea`, CPython 3.12.13, pytest 9.0.3, and SurrealDB 3.2.1.
All TP2 paths were provider-free and made zero model calls, tokens, or estimated provider spend.

- Ruff lint over every TP2-touched Python path: passed; Ruff format check: passed;
  `git diff --check`: passed.
- Focused migration, TP0–TP2 contract, ingestion, TP1 lifecycle, worker, extension, package-identity,
  and roadmap lane with the reference extension enabled: 122 passed and 1 deselected in 8.35
  seconds.
- Explicit extension-disabled naked-kernel lane: 2 passed and 1 expected built-in-discovery skip in
  0.27 seconds.
- Disposable TP2 replay plus TP1A and TP1B restart proofs: 3 passed in 9.02 seconds.
- Fresh schema-zero application through v163, two independent API processes, and thin-client
  I1–I3/F1 persistence: 1 passed in 28.16 seconds.
- Complete extension-disabled, non-E2E compatibility suite: 6,745 passed, 47 skipped, and 248
  deselected in 513.53 seconds; zero failures.
- Final roadmap, thin eleven-tool registration, and kernel-boundary lane: 8 passed in 1.28 seconds.

The v163 migration was applied twice in the disposable TP2 database. The schema-zero API fixture
then applied the full migration chain through v163 and restarted the API against the same store.
All disposable SurrealKV processes were stopped and their temporary directories were released by
their test fixtures.

The complete suite reported 28 warning instances from existing Starlette/FastAPI/websocket
deprecations, pytest collection of two model classes, short fixture JWT key length, and unawaited
test-mock coroutine paths. No TP2 warning or failure was suppressed. One preliminary focused command
incorrectly combined `ACE_DISABLE_EXTENSIONS=1` with the reference-adapter registration test; it
reported 122 passes and one expected environment-mismatch failure before the two environments were
split into the green 122-test reference lane and green naked-kernel lane above. Two preliminary
commands used stale guessed test selectors and collected no tests. The first broad-suite process was
intentionally interrupted after 2,508 passing tests when the roadmap sentinel changed, then the
authoritative final-state suite above was started from the beginning and completed successfully.

Compose/container execution was **not** run for TP2. TP1's prior evidence includes a structural
Compose configuration check, but this packet does not claim a TP2 container run or deployment.

The prior cleanup caveat is now closed. A read-only audit of every TP2 table in the configured local
test database searched only the four exact scopes `product:tp2_a`, `product:tp2_b`,
`product:tp2_acceptance_a`, and `product:tp2_acceptance_b`. It found zero scoped rows and zero matching
product records, with no query errors. There was therefore nothing to remove, and no destructive
query was issued. All subsequent persistence acceptance remained confined to disposable SurrealKV
stores created and released by the test fixtures.

No live provider, customer/private/production data, historical backfill, paid model call, commit,
push, publication, pull request, hosted-service mutation, or deployment occurred. The frozen TP0
corpus and expected labels were not edited.

## Boundary after TP2

TP2 proves durable, inspectable source evidence and an extension-safe ingestion seam at bounded
pilot scale. It does not prove full OLC throughput or readiness for a 182,315-record import. It does
not select candidates, compute an as-of belief state, resolve contested claims, accept causal
assertions, learn transitions, simulate consequences, promote evidence into memory, or demonstrate
beneficial decision impact. Those remain TP3 and later work.

The TP0 persistence matrix is now closed by the combined TP1/TP2 restart, replay, and
foreign-product evidence, without changing TP0's recorded zero public-surface baseline. E1 remains
the existing extension architecture rather than being advanced as a new outcome. T1 remains `not
ready`, and K1, K2, and K3 remain `not ready`.

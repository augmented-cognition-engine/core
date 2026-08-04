# ACE State Engine TP4 belief-state projection v1

Status: **implemented, adversarially repaired, and acceptance-verified; T1 and K1–K3 remain not ready**

This record closes the bounded TP4 packet with immutable, product-scoped records for reviewed
epistemic assertions, as-of belief projection, reproducible external-world insights, and targeted
reopening. Source claims and cheap evidence relations remain evidence; neither prose similarity nor
temporal sequence silently becomes operational causal truth. TP4 does not model dynamics, simulate
consequences, promote these records into cognitive memory, or establish beneficial impact.

## Contract, resolver, and projection boundary

[`belief_contracts.py`](../../core/engine/grounded_state/belief_contracts.py) defines extra-forbid,
immutable v1 contracts for typed evidence endpoints, bounded evidence packs, epistemic proposals,
counterevidence-search receipts, reviews, append-only assertion revisions, projection targets and
entries, as-of projections, inference receipts, external-world insights, and incremental
reprojection receipts. Stable material includes product identity, typed endpoints, validity, source
origins, evidence and review references, and the exact ontology, assertion, resolver, projection, or
inference policy version that governed the record.

Evidence packs freeze the TP3 request/receipt identity and selected evidence before assertion
resolution. They keep publication, ingestion, extraction, and ACE-creation time as separate
meanings. Unknown event time remains unknown; ingestion time is never substituted for it. Packs are
bounded to 200 records and 64,000 compact-content characters and expose candidate, score-cap,
return-cap, record-cap, and character-cap omissions plus fallbacks, failures, degraded reasons, and
provider usage.

[`beliefs.py`](../../core/engine/grounded_state/beliefs.py) implements the provider-free v1 policy:

- model output may propose but cannot accept its own assertion or choose product scope;
- `corroborates` requires independent source origins and is distinct from a restatement;
- `contradicts` applies only to mutually exclusive assertions over the same validity scope, not to a
  later changed state;
- `supersedes` preserves the prior revision and validity semantics;
- projection entries carry the reviewed world-state subject, predicate, and value rather than
  relabeling an evidence-to-evidence relation as a belief;
- historical and planned states remain visible in the frozen knowledge-time projection, while an
  explicit successor assertion marks the prior state superseded;
- `causes` fails closed without human confirmation, two supporting evidence references, two
  independent source origins, a complete non-degraded evidence pack, and a completed exact-material
  counterevidence search over that same pack;
- reciprocal or mutually exclusive accepted assertions project as contested;
- every projection entry retains the assertion revision and review, and accepted operational
  entries additionally retain the accepted assertion plus frozen evidence references;
- arrival and provider-output ordering are normalized before identity and resolution; and
- new dependency evidence reopens only the affected assertion revisions; unrelated entries are
  retained byte-for-byte rather than silently re-evaluated against a different pack.

External-world insights are a separate record class. Each carries the frozen evidence pack,
assertion revisions, hypothesis, supporting and contrary evidence, route, policy/model versions,
confidence, validity, review state, inference receipt, provider usage, and exact replay hash. A
derived insight cannot relabel a source claim as its own conclusion. TP4 deliberately does not
promote the insight into cognitive memory.

The existing relational-assertion path now includes product in proposal, assertion, review, event,
dependency, semantic-identity, persistence, replay, invalidation, and operational-projection
semantics. Grounded endpoint types are accepted without weakening insight and decision endpoint
types. Cheap evidence-edge vocabulary remains non-causal. Existing `causes` assertions now require
confirmed human review, completed counterevidence search, and independent sources before becoming
operational.

## Persistence, restart, and schema

[`belief_persistence.py`](../../core/engine/grounded_state/belief_persistence.py) is an append-only,
type-specific durable store. It atomically persists a record chain, detects a
same-identity/different-payload collision, reloads exact records, lists assertion revision history, and follows dependency references for targeted
reopening. [`BeliefStateProjectionService`](../../core/engine/grounded_state/beliefs.py) freezes TP3
candidates with the TP2 record and ACE-creation times, requires and persists the exact proposal,
review, counterevidence, assertion, pack, and projection chain, and replays a projection through a
fresh service instance. Bounded projections retain their original bound, every evaluated assertion
revision, and every requested target, including material omitted from the emitted entry list.

Migration
[`v164_state_engine_tp4_belief_projection.surql`](../../core/schema/v164_state_engine_tp4_belief_projection.surql)
adds optional product/review/evidence fields and product-fenced indexes to the existing reviewed
assertion tables. It creates nine append-only, schema-full product-scoped tables for proposals,
reviews, assertion revisions, counterevidence searches, evidence packs, projections, inference
receipts, external insights, and reprojection receipts. No legacy assertion row is backfilled or
made operational. Migration replay is idempotent and the schema-zero acceptance reaches v164.

The real disposable SurrealKV acceptance ingests TP2 evidence, freezes a TP3 receipt and TP4 pack,
persists proposal, counterevidence, human review, accepted assertion, projection, inference receipt,
external insight, reopened revision, resulting projection, and targeted reprojection receipt. It
then restarts the database, opens a fresh client and projection service, and reproduces the exact
records and projection. A foreign-product load fails closed. The acceptance also proves TP3 receipt
replay and the existing API/service restart through schema head v164.

## Frozen evaluation

The target configuration
[`state_engine_tp4_belief_projection_v1.json`](../../evaluations/fixtures/state_engine_tp4_belief_projection_v1.json)
was frozen before the first implementation evaluation. It binds corpus hash
`4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09`, the exact v1 ontology,
assertion, resolver, projection, and inference policies, 13 owner-reviewed TP0 cases, deterministic
replay and isolation checks, and zero provider/model-call, token, and cost budgets. Its configuration
hash is `008b9c617c7a0cb86fc0cf94c2e444c8991ff2239f8b92fcb87678330fbe86a7`.

The unchanged target now executes the real proposal compiler, assertion resolver, belief projector,
causal negative controls, product-scoped projections, and reverse-order replay. Every case result
records the actual projection hash. A regression replaces the projector with a failing function and
proves that evaluation fails instead of returning a recorded answer. The repaired execution passed:

| Measure | Result |
|---|---:|
| Cases matched | 13 / 13 |
| Deterministic replay matches | 13 / 13 |
| Product-isolation violations | 0 |
| Causal-negative-control violations | 0 |
| Unlinked operational entries | 0 |
| Primary model calls | 0 |
| Input / output tokens | 0 / 0 |
| Estimated cost | $0.00 |

The result distinguishes temporal update, same-interval contradiction, restatement, corroboration,
supersession, sequence, causal candidacy, and unknown state/time. Its material outcome hash is
`f09127fda74a31246c69eded4e78983f9a6678d770de2134082c21e5bd757bd0`. Runtime checks listed as
deferred inside the pure machine evaluation were completed separately by the acceptance tests in
this record. The complete frozen result is
[`state_engine_tp4_belief_projection_v1.json`](../../evaluations/results/state_engine_tp4_belief_projection_v1.json).

## Verification

Verification on 2026-08-03 used source revision
`6b6342f65224ca0c3db2f38c3bc141a58de9e8ea`, CPython 3.12.13, pytest 9.0.3, and the repository's
disposable SurrealDB acceptance runtime. All TP4 evaluation and acceptance paths were provider-free.

- Post-repair Ruff lint and format checks passed over all nine repaired Python paths.
- Focused TP0–TP4 contract, candidate, assertion, and evaluator lane: 93 passed and 1 skipped in 2.06
  seconds.
- TP4 adversarial and legacy-assertion lane: 41 passed and 1 skipped in 0.55 seconds.
- Disposable TP2–TP4 database and service restart acceptance: 9 passed in 16.66 seconds.
- Migration lint, replay, safety, fail-closed, and idempotency lane: 36 passed and 1 skipped in 0.63
  seconds.
- Fresh isolated schema-zero apply processed 163 migration files through v164 with 110 audited legacy
  compatibility events; the second apply validated v164 with zero pending files.
- API, graph, Cognify, naked-kernel, exact eleven-tool, package-identity, and roadmap regression lane:
  97 passed, 9 skipped, and 1 existing Starlette warning in 2.80 seconds.
- Complete extension-disabled, non-E2E compatibility suite: 6,781 passed, 47 skipped, and 250
  deselected in 529.43 seconds; zero failures and 28 existing warning instances.
- `git diff --check`: passed.

The focused graph lane's single warning is the existing Starlette `TestClient`/`httpx` deprecation.
The complete suite reported 28 warning instances from existing Starlette/FastAPI and websocket
deprecations, pytest collection of two model classes, short fixture JWT key length, and unawaited
test-mock coroutine paths. No warning, skip, or failure was suppressed.

## Preliminary failures and corrections

The original frozen target was not changed, but the original evaluator implementation was later
rejected during an adversarial hands-off audit: it returned a hardcoded table matching the expected
labels, round-tripped those result objects as “replay,” and hardcoded violation counts to zero. A
probe made the real projector raise on every call while the evaluator still reported 13/13. That
green result was invalid evidence. The repaired evaluator now executes the real contracts and records
projection hashes; its first post-repair execution passed the unchanged target. The same audit found
and the repair closed truncated-pack causal promotion, grouped unreviewed causal material, unrelated
inference receipts, historical-state loss, false targeted reprojection, bounded replay loss, partial
service lineage, missing-product authorization, and the CLI's missing product parameter.

Earlier preliminary tooling and acceptance runs also exposed these retained issues:

1. The first default-cache Ruff invocation could not write the sandboxed user UV cache. Verification
   was rerun with the task-local `/tmp/ace-tp4-uv` cache; no lint result was discarded.
2. The first focused graph/Cognify regression had one failure because an existing test mock still
   expected an unscoped relationship proposal. The production contract intentionally requires
   product identity, so the compatibility expectation was updated; the unchanged lane then passed.
3. The first disposable restart attempt could not bind loopback under the filesystem sandbox. It was
   rerun with explicit local-test authorization.
4. The first authorized TP4 restart run found a real append-only persistence defect: a generic
   identity accessor selected `proposal_id` for an assertion revision, so a reopened revision
   collided with the original. Persistence now selects the stable identity by exact record type. The
   same full record chain then passed across database and service restart.
5. The first complete extension-disabled compatibility attempt reached 2,095 passed, 26 skipped,
   and 250 deselected with 28 warnings in 797.78 seconds, then was interrupted rather than presented
   as success. Stack inspection showed an order-dependent deadlock in the pre-existing global
   database pool: a healthy overflow connection awaited return to an already-full bounded queue
   while its context manager prevented another acquire. Pool return is now non-blocking and
   discards an overflow connection while retaining the configured capacity. A no-database
   regression pins the invariant.
6. The first focused pool regression rerun inside the filesystem sandbox had 9 passes and one
   loopback-permission failure in an existing closed-port test. The explicitly authorized rerun
   passed all 10 tests in 1.92 seconds.

No corpus label, owner review, frozen TP0/TP3 target, TP4 target configuration, expected label,
required check, or provider budget was changed to obtain the repaired passing result. The machine
result changed because it now includes real projection hashes and the corrected outcome hash.

## Public surface and honest limits

No MCP tool was added: the supported thin MCP contract remains exactly eleven tools. No test-only
endpoint was added. The existing assertion-inspection API now requires a JWT with an explicit product
claim exactly matching the requested product before returning a record; a legacy unscoped token fails
closed. The `ace assertion` CLI requires `--product` (or `ACE_PRODUCT`) and forwards it to the API.
All other TP4 projection and inference services remain internal.

No live or paid provider, customer/private/production data, full OLC backfill, historical backfill,
hosted-service mutation, deployment, publication, commit, push, pull request, or Compose/container
execution occurred.

The 13-case frozen evaluation and disposable restart test establish the bounded v1 contract and its
replay/isolation properties; they do not establish production-scale throughput, multilingual
quality, learned retrieval quality, general causal correctness, calibrated dynamics, rollout
accuracy, cognitive-memory usefulness, or beneficial decision impact. Human causal review is
contractually required but this fixture is not evidence of reviewer reliability. TP5 transition
dynamics, TP6 consequence rollouts, promotion, beneficial impact, T1, and K1–K3 remain out of scope
or `not ready`.

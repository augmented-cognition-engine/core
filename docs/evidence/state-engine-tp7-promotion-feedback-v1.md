# ACE State Engine TP7 explicit promotion and feedback v1

Status: **implemented and bounded acceptance-verified; TP8 and public K1–K3 remain not ready**

This record closes the bounded TP7 packet. A durable grounded conclusion can now move through an
immutable proposal, an authoritative human or allow-listed deterministic disposition, the existing
`insight` memory plane, a real database restart, fresh task-time retrieval, existing I3 use
accounting, and an append-only correction or supersession. TP7 does not turn ingestion, retrieval,
source instructions, simulations, or model output directly into memory, and it does not establish
beneficial impact, causal correctness, autonomous learning, scale readiness, or release readiness.

## Preconditions and frozen target

Before TP7 implementation, the existing dirty worktree and migration head were inspected and
preserved. The complete State Engine roadmap and TP6 implementation, persistence, result, evidence,
restart behavior, and roadmap reconciliation were reviewed. TP6 was then independently reproduced:
its 12 focused consequence-rollout tests passed, its provider-free evaluator output was byte-for-byte
identical to the recorded result with outcome hash
`dfeeb1128166b6dc93bfb41a8911b8a9d3fd3a298a6cd85fff7d709783aab915`, its disposable rollout restart
test passed, and its schema-zero API/thin-client restart test reached migration head v166. No TP6
blocking discrepancy was found.

Before implementation, TP7 froze
[`state_engine_tp7_promotion_feedback_v1.json`](../../evaluations/fixtures/state_engine_tp7_promotion_feedback_v1.json)
with raw SHA-256
`d0f3032702557c5d99fabac3257006accf09d745aefd7c23c3818bc489fdfb81`.
It binds the unchanged TP0 corpus identity and raw hash, the reproduced TP6 fixture/result hashes,
exact proposal/review/receipt/lineage/policy/resolver/ontology versions, four positive cases,
fourteen adversarial cases, all eight lifecycle dispositions, 26 acceptance checks, three sabotage
checks, deterministic bounds and seed, and a zero-call, zero-token, zero-latency, zero-cost provider
budget. The frozen target was not edited after implementation output and has no target corrections.

The recorded machine result is
[`state_engine_tp7_promotion_feedback_v1.json`](../../evaluations/results/state_engine_tp7_promotion_feedback_v1.json),
with raw SHA-256
`e1c160058ca8f9989a6fa1881feff58c3e68dde77720463cccf8b78216ee4278`:

- 4 of 4 positive cases matched;
- 14 of 14 adversarial cases matched;
- all accepted, rejected, expired, contested, invalidated, superseded, failed, and degraded states
  remained inspectable;
- all 26 required checks and all 3 real-path sabotage checks passed;
- zero product-isolation, unauthorized-memory, simulated-observation, beneficial-impact, or provider-
  budget violations; and
- zero provider/model calls, input or output tokens, latency, retries, or cost.

Configuration hash:
`6e866ae12f586d1cf43d4245e37154e725cccb80a30a511aa5406196fa1d88ab`.
Outcome hash:
`d35a4543f63ac021bd398dbc0c7d76bd0d92632effd321f4d774208ae4a7866f`.

The evaluator performs an exact replay through the production `PromotionService.propose`,
`PromotionService.review`, and atomic `PromotionStore.persist_disposition` paths, restarts the real
disposable SurrealKV database, creates a fresh service, and calls the production later-retrieval
path. Its sabotage regression replaces all three production paths with fake implementations and
proves every corresponding sabotage check and the overall result turn false. It also asks the
actual thin MCP server for its registered tool count; the result remains exactly eleven.

## Contracts, meanings, and authority

[`promotion_contracts.py`](../../core/engine/grounded_state/promotion_contracts.py) defines immutable,
extra-forbid, product-scoped v1 proposal, review, receipt, memory-lineage, and retrieval projection
contracts. Stable identities and hashes are derived from exact material. A proposal binds the
product, typed reusable material, task and normalized I1 decision receipt hashes, TP6 context and
evidence pack identities and hashes, exact evidence record versions and coverage, TP4 belief
projection, TP5 transition revisions, TP6 rollout revision and reasoning-use receipt, provenance,
proposer authority, omissions, failures, degradation, contestation, correction and predecessor
lineage, and frozen policy/resolver/ontology versions.

The eligible meanings are deliberately closed: durable conclusion, decision, correction, stable
preference, and reusable reasoning pattern. Raw records, extracted or retrieved claims, arbitrary
source instructions, observed-fact relabeling of simulated states, unknown target meanings, and
material without exact task/evidence/reasoning lineage fail validation or eligibility. Source text
has no execution or review authority.

Proposal and authority are separate. A model can propose typed material but the review contract
forbids model authority. Acceptance requires an authenticated human or an exact allow-listed
deterministic rule; the v1 deterministic allow-list is restricted to the stable-preference rule.
Requested acceptance fails closed to contested, degraded, or failed when exact support is
contested, omitted, degraded, rejected, or otherwise ineligible. Non-accepted receipts cannot name
a memory, and accepted receipts require exact memory lineage. Every receipt states that beneficial
impact is unsupported.

## Persistence, correction, and replay

Additive migration
[`v167_state_engine_tp7_promotion_feedback.surql`](../../core/schema/v167_state_engine_tp7_promotion_feedback.surql)
adds four schema-full, product-scoped, append-only tables for proposals, reviews, receipts, and
memory lineage, plus optional TP7 lineage fields on the existing `insight` table. Update and delete
permissions are denied for TP7 lifecycle tables. The migration contains no source, TP4, TP5, TP6,
Foresight, decision, observation, or legacy-memory mutation or backfill, and is applied twice in the
disposable acceptance.

The store preflights exact stable identities, accepts byte-equivalent replay, rejects conflicting
material, and transactionally creates review, receipt, memory lineage, and the existing insight row.
A partial chain fails closed. Product scope is checked on every load and related receipt. Effective
state is reconstructed from append-only expiry, contestation, invalidation, and supersession edges;
old insight rows are never deleted or rewritten.

An accepted I1 `correction-v1` observation creates a new promoted correction and automatically
supersedes its exact predecessor receipt. The original proposal, receipt, evidence pack, rollout,
memory, and lineage remain inspectable. After restart, authoritative retrieval returns only the
corrected memory while the prior state reports `superseded`.

## Runtime, I3, graph, and public surface

[`promotion.py`](../../core/engine/grounded_state/promotion.py) verifies the real persisted TP4–TP6
chain before proposal persistence or review. Accepted material enters the existing `insight` table;
there is no second memory system. The ordinary task-time loader, bounded interactive probe, and
`/intel/search` filter all promotion-managed rows out of the legacy `status = active` view and add
back only memories selected by current append-only receipts. The real restart acceptance proves the
task loader sees historical rows but returns only the corrected authoritative state.

Later-use recording reuses `intelligence-use-receipt-v1`. One fresh task records retrieval without
injection, reflection, materiality, or benefit. A second matched-control task separately proves
retrieved, injected, reflected, and decision-material states while still reporting
`beneficial_impact_supported = false`. No wording overlap, identifier mention, or model self-report
earns materiality.

The reference extension adds an experimental, authority-gated `promotion-review` task action over
the existing extension invocation and durable task/status lifecycle. Product and reviewer identity
come from authenticated Core actor context. The action reports an already-persisted authoritative
receipt and gives the reporting model no lifecycle authority. It adds no API endpoint and no MCP
tool. Cancellation is explicitly unsupported after preparation because it cannot undo the already
append-only authoritative receipt; retry remains exact and idempotent.

The Living Product Graph exposes bounded proposal, review, receipt, and memory-lineage metadata
under `state_engine.promotion`. Payloads are omitted, authority is read-only, and promotion metadata
is explicitly not source evidence. The naked kernel still operates with extensions removed, and the
thin public MCP contract remains exactly eleven tools.

## Verification

- TP7 contracts, recorded result, runtime loader/API/probe compatibility, Living Product Graph, and
  reference extension action: 89 passed in 1.88 seconds.
- Focused TP0–TP7, I1, I3, graph, and extension compatibility lane: 205 passed, 6 E2E tests
  deselected, 1 existing deprecation warning, in 2.94 seconds.
- Complete disposable TP2–TP7 persistence, replay, isolation, runtime, evaluator/sabotage, and real
  database restart lane: 6 passed, 6 non-E2E tests deselected, in 56.34 seconds.
- Fresh schema-zero database/API/thin-client restart through migration head v167: 1 passed in 37.19
  seconds.
- Migration lint, safety, error handling, application, splitter, and idempotency lane: 33 passed and
  1 optional database test skipped in 0.56 seconds.
- Exact eleven-tool, package-boundary, naked-kernel, startup, runtime-tool, and extension-removal
  lane: 108 passed and 1 skip in 2.62 seconds. Its first sandboxed run had 107 passes and one
  localhost-bind permission failure; the exact lane was rerun with loopback permission.
- Complete extension-disabled non-E2E gate: 6,831 passed, 47 skipped, 255 deselected, 28 existing
  warnings, zero failures, in 493.74 seconds. The first complete run had the same pass/skip counts
  plus one retryable SurrealDB write-conflict error during `test_embedding_reconciler` teardown; the
  exact test passed alone in 1.60 seconds, and the full gate was rerun cleanly.
- Ruff lint and format checks cover all TP7-touched Python modules and tests; repository whitespace
  validation passes.
- Final post-format real TP7 restart, task-time retrieval, recorded-result replay, and sabotage
  acceptance: 1 passed in 16.07 seconds.

## Limitations and non-claims

TP7 uses synthetic/public fixtures and provider-free deterministic evaluation. No private,
customer, hosted, paid-provider, production, Compose, bulk-import, backup/restore, or deployment
path was exercised. No commit, push, pull request, publication, or release is part of this work.

The bounded cases prove contract enforcement, atomic lineage, replay, restart, correction, runtime
selection, and I3 accounting—not reviewer reliability, correctness of promoted conclusions,
general autonomous learning, causal correctness, broad domain validity, throughput, scale,
stability, decision quality, or benefit. L1 remains `candidate` with collection not started; TP8,
T1, B1, E1, public K1–K3, and ACE v0.2.0 readiness are unchanged.

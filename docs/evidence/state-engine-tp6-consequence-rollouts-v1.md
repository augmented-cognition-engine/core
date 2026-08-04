# ACE State Engine TP6 bounded consequence rollouts v1

Status: **implemented and bounded acceptance-verified; TP7, TP8, and public K1–K3 remain not ready**

This record closes the bounded TP6 packet. A task can resolve a small provenance-rich context from
the grounded-state substrate, execute inspectable action, no-action, and named-alternative futures
over one frozen belief projection and exact transition revisions, prove which material entered
later reasoning, and reconcile a compatible observed outcome without relabeling simulation as fact.
TP6 does not promote source text or conclusions into cognitive memory and does not establish
real-world rollout accuracy, general calibration, decision benefit, or production-scale readiness.

## Frozen target and result

Before the first TP6 implementation evaluation, TP6 froze
[`state_engine_tp6_consequence_rollout_v1.json`](../../evaluations/fixtures/state_engine_tp6_consequence_rollout_v1.json)
with raw SHA-256
`03dede642b95710df7a118126fcaa8b88fe6a94a1ff40633863d0ada144c1d8d`.
The target binds the unchanged 40-case TP0 corpus hash
`4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09`,
exact TP3–TP6 policy versions, five selected scenarios, eleven required checks, action/no-action and
named-alternative expectations, prompt-injection and simulated/observed negative controls,
deterministic branch/step/transition/evidence/context/horizon bounds, seed 1729, and a zero-call,
zero-token, zero-cost provider budget. TP0 semantics and TP3–TP5 targets/results were not changed.

The recorded machine result is
[`state_engine_tp6_consequence_rollout_v1.json`](../../evaluations/results/state_engine_tp6_consequence_rollout_v1.json):

- 5 of 5 frozen scenarios matched;
- 2 of 2 reverse-order deterministic replays matched;
- all 11 required checks passed;
- zero product-isolation, prompt-authority, or simulated-observation violations; and
- no provider/model, calls, tokens, latency, retries, cost, failures, or fallbacks.

The final evaluator command completed in 0.5 seconds on the recorded local run.

Configuration hash:
`b35041e7c802c2b593ce24ba99b422d0f0d7afd54867cad7b3f09707effe8e7d`.
Outcome hash:
`dfeeb1128166b6dc93bfb41a8911b8a9d3fd3a298a6cd85fff7d709783aab915`.

Two failed preliminary evaluator attempts are preserved rather than rewritten:

1. [`preliminary-1`](../../evaluations/results/state_engine_tp6_consequence_rollout_v1.preliminary-1.json)
   rejected the frozen `named_alternative` label before any case ran because the reused v1 enum
   stores that meaning as `alternative`. The evaluator added a compatibility alias; the target did
   not change.
2. [`preliminary-2`](../../evaluations/results/state_engine_tp6_consequence_rollout_v1.preliminary-2.json)
   compared the corpus-hash method object rather than calling it. The evaluator call was corrected;
   the target did not change.

Both failures started zero cases and made zero provider calls. A still earlier package command was
denied access to the global package cache and never entered the evaluator. The successful run used
an isolated cache. A sabotage regression replaces production rollout execution with a failure and
proves the evaluator turns red, while a corpus-drift regression rejects a different TP0 hash.

## Contracts and authority boundaries

[`rollout_contracts.py`](../../core/engine/grounded_state/rollout_contracts.py) adds immutable,
extra-forbid, product-scoped v1 contracts for evidence queries, reasoning evidence packs, coverage,
branch assumptions and constraints, rollout proposals, predicted state steps, consequences,
falsifiable outcomes, deterministic execution, model proposals, independent challenge, final
append-only rollout revisions, I3 reasoning use, later observations, and reconciliation. Every
identity is derived from canonical exact material and retains task, invocation, product, projection,
evidence-pack, transition, branch, policy, index, time, horizon, omission, failure, degradation, and
provider-use coordinates relevant to its meaning.

The meanings remain separate:

- evidence is source-attributed untrusted data;
- a TP4 projection is ACE's reviewed as-of belief state;
- a TP5 revision is an inspectable transition hypothesis;
- a TP6 predicted state or consequence is a simulation only;
- a model receipt is non-authoritative proposal material;
- a later observation and reconciliation are distinct post-rollout records; and
- none of these becomes cognitive memory through TP6.

A model cannot choose trusted product scope, mint authoritative lifecycle identity, accept its own
challenge, mark a simulated state as observed, resolve a later outcome, or rewrite a prior rollout.
The implemented acceptance path is entirely deterministic and provider-free. The model-proposal
contract remains available for separately attributable bounded proposals, but TP6 made no live or
paid model call.

## Evidence Query v1 and prompt authority

[`evidence_query.py`](../../core/engine/grounded_state/evidence_query.py) resolves trusted Core scope
through the existing TP3 candidate service and TP4 evidence-pack freezer. The returned reasoning
pack records the exact candidate receipt, pack/version hashes, index versions, record and character
bounds, selected records, omissions, failures, fallbacks, degradation, and all nine coverage states:
supported, provisional, contested, superseded, stale, rejected, unknown, missing, and truncated.
Unknown time remains unknown; post-as-of material is omitted instead of backdated.

The reference extension's
[`evidence-query` action](../../extensions/reference/evidence_query.py) is registered through the
existing experimental task-action surface. Product, workspace, user, invocation, and authorization
scope come from authenticated Core actor context; a caller-supplied product parameter is ignored.
It returns one bounded `ResolvedContextRecord` whose source content is enclosed by
`UNTRUSTED_EVIDENCE_DATA_ONLY` and `END_UNTRUSTED_EVIDENCE_DATA`. Text inside that delimiter has no
system, task, tool, secret, mutation, or scope authority. The action uses existing submit, retrieve,
history, retry, cancel, and task/status journeys. It adds neither an endpoint nor a twelfth MCP tool.

## Deterministic rollouts and independent challenge

[`rollouts.py`](../../core/engine/grounded_state/rollouts.py) binds one exact TP4 projection and hash,
one exact TP4 evidence pack and hash, and explicit accepted or provisionally rollout-eligible TP5
revision IDs and hashes. It applies eligible transition rules in stable identity order. Every branch
exposes its common start, applicable and blocked transitions, missing inputs, constraint failures,
ordered predicted steps, uncertainty, consequences, falsifiable observation windows, provenance,
omissions, failures, and degradation. The v1 bounds are eight branches, 32 steps, 16 transitions,
64,000 context characters, and a 365-day horizon; the frozen evaluation uses tighter limits.

The mandatory independent challenge checks complete projection/evidence/transition lineage,
unsupported assumptions, contested/stale/superseded/rejected/unknown/missing/truncated material,
action/no-action comparability, causal overstatement, domain validity, constraints, horizon,
omissions, prompt authority, product scope, and policy/index availability. Incomplete challenge or
required degraded input cannot produce an eligible rollout. Recalculation creates a new revision
with prior lineage; TP4/TP5 inputs are never mutated.

## Reasoning use and later outcomes

TP6 projects exact evidence, belief entries, transition revisions, assumptions, branches, and
consequences into I3-style retrieved, injected, reflected, and decision-material states. Retrieval,
injection, wording overlap, identifier mention, or model self-report cannot earn materiality. A
matched rollout/no-rollout control must match task hash, provider, exact model, configuration,
decision schema, and toolset, retain two different output hashes, and identify exact changed
decision fields and material items. Without that proof, the receipt stops at retrieved, injected, or
reflected and records the missing materiality evidence.

Later reconciliation binds one immutable rollout revision and compatible predicted outcome, occurs
after the rollout as-of time, cites a separate evidence pack frozen no later than observation, and
retains paired Foresight prediction/resolution references when present. Compatible samples produce
matched, contradicted, or mixed scores; incompatible branch/horizon/variable or absent assignment
remains visibly unresolved and unscored. The original rollout, projection, transition revision,
probability, and consequence hashes remain unchanged.

## Persistence, restart, graph, and public surface

Additive migration
[`v166_state_engine_tp6_consequence_rollout.surql`](../../core/schema/v166_state_engine_tp6_consequence_rollout.surql)
adds ten schema-full, append-only, product-scoped tables for queries, context packs, proposals,
executions, model proposals, challenges, rollout revisions, reasoning-use receipts, observations,
and reconciliations. It contains no destructive migration, backfill, or mutation of TP2–TP5,
Foresight, task, decision, observation, insight, or memory rows. Complete TP6 chains are preflighted
for exact identity collisions and written transactionally.

The disposable restart acceptance applies v166 twice, ingests public fixture evidence, restarts,
resolves a fresh bounded query, replays it after another restart, and proves another product cannot
retrieve the record. It persists complete TP4 and TP5 lineage, executes and atomically persists an
action/no-action rollout, rejects different material under the same claimed identity, persists a
reasoning-use receipt, restarts and exactly replays the rollout, records a separate later evidence
pack and observation with Foresight references, reconciles it, verifies the rollout hash did not
change, restarts again, and reloads the exact observation/reconciliation. A separate fresh-process
API and thin-client acceptance starts from schema zero, reaches migration head v166, restarts the API,
and preserves its durable task/decision/correction/foresight contract.

The Living Product Graph reads only allowlisted TP6 metadata under `state_engine`. Rollouts are
labeled `read_only_simulation_projection` and `simulated_consequence_not_observation`; payloads are
omitted and no rollout appears under `intelligence.observations` or insights. Reconciliations retain
their separate read-only observed-outcome meaning. The naked kernel still operates with extensions
and grounded-state adapters absent. The supported thin MCP registration remains exactly eleven.

## Verification

- TP6 contracts, rollouts, controls, reconciliation, evaluator replay/sabotage, migration, and graph
  projection: 46 passed in 0.74 seconds.
- Focused TP0–TP6, Foresight, I1, I3, extension-action, task/status, graph, MCP, package, and roadmap
  regression lane: 433 passed with 1 existing deprecation warning in 4.99 seconds.
- Migration lint, safety, failure, and idempotency lane: 31 passed, 1 optional database test skipped,
  in 0.52 seconds.
- Complete disposable TP2–TP6 persistence, evidence-query, rollout, reconciliation, isolation, and
  restart lane: 5 passed, 6 non-E2E tests deselected, in 39.50 seconds.
- Fresh schema-zero database/API/thin-client restart through v166: 1 passed in 34.20 seconds.
- Ruff lint and format checks cover every TP6-touched Python module and test; final repository
  whitespace/error validation also passes.
- Complete extension-disabled non-E2E gate: 6,814 passed, 47 skipped, 253 deselected, 28 warnings,
  zero failures, in 532.26 seconds. The warnings are existing framework deprecations, collection
  notices, short test JWT-key warnings, and coroutine resource warnings.

The first sandboxed complete-gate attempt was stopped after its first failure at 1,445 passed,
96 skipped, and 253 deselected: an existing canvas proxy test could not bind its loopback port under
the sandbox. The complete gate was rerun with local-loopback permission and passed with the totals
above. This environmental failure is retained here and was not recast as a product failure.

## Limitations and non-claims

TP6 used only synthetic/public fixtures and provider-free deterministic execution. It made no
customer, private, production, hosted, paid-provider, or historical-backfill access. Compose and
container execution did not occur; the restart proofs used isolated local SurrealKV and API
processes. No hosted service was mutated. No commit, push, pull request, publication, or deployment
is part of this record.

Five frozen cases and one later-outcome mechanism prove bounded contracts and replay, not forecast
accuracy, probability calibration, reviewer reliability, domain breadth, sustained ingestion,
production throughput, scale, stability, decision quality, or benefit. Matched-control mechanics do
not establish general material influence, and outcome reconciliation does not establish general
calibration. TP7 promotion, TP8 scale/stability, L1 beneficial impact, T1, and public K1, K2, and K3
readiness remain out of scope or `not ready`.

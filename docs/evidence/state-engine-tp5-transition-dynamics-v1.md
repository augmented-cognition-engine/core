# ACE State Engine TP5 transition dynamics v1

Status: **implemented and bounded acceptance-verified; TP6 and public K2 remain not ready**

This record closes the bounded TP5 implementation packet. ACE can now represent an inspectable,
versioned hypothesis about how one typed world-state variable may change into another without
relabeling an observation, belief-state assertion, prediction, or temporal association as causal
truth. TP5 freezes transition inputs for later rollouts; it does not simulate a future, promote a
conclusion into cognitive memory, or claim general causal correctness.

## Frozen target

Before implementation evaluation, TP5 froze
[`state_engine_tp5_transition_dynamics_v1.json`](../../evaluations/fixtures/state_engine_tp5_transition_dynamics_v1.json)
against the unchanged TP0 corpus hash
`4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09`.
The target binds eight selected owner-reviewed cases, ten mandatory acceptance checks, exact v1
ontology/resolver/challenge/calibration policy versions, deterministic bounds, and a zero-call,
zero-token, zero-cost provider budget. The TP0 corpus and its owner-reviewed labels were not edited.

The first execution that reached the evaluator passed the unchanged target. An earlier command did
not initialize the evaluator because the package runner was denied access to its global cache; it
made no evaluation or provider call and is not counted as an implementation result.

## Contract and lifecycle

[`transition_contracts.py`](../../core/engine/grounded_state/transition_contracts.py) adds immutable,
extra-forbid, product-scoped v1 records for:

- typed state variables, conditions, assignments, triggers, and deterministic precondition or
  constraint rules;
- bounded transition proposals linked to an exact TP4 belief projection and evidence pack;
- independent challenge receipts that reconcile every selected pack record searched;
- exact-material reviews and append-only hypothesis revisions;
- deterministic branch inputs that freeze the starting projection and rule evaluations without
  creating a simulated fact;
- separate observed transition outcomes with paired optional Foresight forecast/resolution links; and
- calibration receipts that retain the original revision hash and every outcome reference.

Stable hypothesis identity covers source condition, target assignment, trigger, mechanism, rules,
delay, and ontology. Exact proposal, challenge, review, revision, branch-input, outcome, and
calibration identities additionally cover their complete material and lifecycle context. Models may
propose bounded material but cannot select product scope, accept or reject lifecycle state, resolve
an observed outcome, or rewrite a prior revision.

[`transitions.py`](../../core/engine/grounded_state/transitions.py) implements the provider-free
challenge, review, resolution, rule-evaluation, branch-input, and calibration path. A transition is
rollout-eligible only when it is provisionally or fully accepted, mechanistic or causal, bound to a
complete non-degraded challenge over the exact evidence pack, and has no contrary evidence,
omission, failure, or degraded reason. Temporal sequence or reaction alone is rejected as an
accepted transition. Accepted causal status additionally requires exact human review and at least
two supporting records from two independently reviewed source origins.

Contrary episodes remain contested and visibly degraded. Missing human causal review, unknown time,
unavailable mechanism, and cross-product inputs remain proposed or rejected with explicit degraded
reasons. Typed domains reject impossible assignments, while source conditions and deterministic
rules block inapplicable branch inputs. Stale and superseded revisions retain exact prior and
supersession lineage.

Observed outcomes live in a separate record meaning and bind the exact immutable transition
revision plus a separate post-revision evidence pack frozen no later than the observation. An
outcome at or before the revision time cannot calibrate it. When an outcome comes through Foresight
reconciliation, the prediction and resolution references are required as a pair. Calibration
recomputes a separate receipt from all exact outcome records; neither the hypothesis revision nor
its original probability is mutated.

## Persistence and restart

Additive migration
[`v165_state_engine_tp5_transition_dynamics.surql`](../../core/schema/v165_state_engine_tp5_transition_dynamics.surql)
adds seven append-only, product-scoped tables for proposals, challenges, reviews, revisions,
deterministic branch inputs, outcomes, and calibration receipts. No TP2 evidence, TP4 belief, legacy
forecast, observation, or cognitive-memory row is backfilled or rewritten.

[`transition_persistence.py`](../../core/engine/grounded_state/transition_persistence.py) preflights
stable-identity conflicts and writes a complete missing TP5 chain in one transaction. Lookup binds a
typed product record directly, including valid hyphenated product identifiers. The same correction
was applied to TP4 lookup after the disposable acceptance exposed the raw-string recast defect.

The disposable SurrealKV acceptance persists the exact TP4 pack, assertion revisions, and belief
projection; atomically persists the TP5 proposal/challenge/review/revision; freezes a deterministic
branch input; restarts the database and creates a fresh service; reproduces the exact revision and
branch input; denies the same identities in another product; records a contrary later outcome;
persists its separate post-revision evidence pack; calibrates without rewriting the revision;
restarts again; and reloads the exact outcome and calibration receipt. Migration v165 is applied
twice before the test.

## Frozen evaluation result

The real evaluator in
[`transition_evaluation.py`](../../core/engine/grounded_state/transition_evaluation.py) executes the
TP4 projector, TP5 proposal compiler, complete challenge, transition review/resolver, deterministic
branch-input compiler, causal negative control, product-isolation probe, impossible-assignment
invariant, and later-outcome calibration. Reversing evidence, assertion, target, and projection-entry
arrival order produces identical challenge, revision, and branch-input material.

The recorded result is
[`state_engine_tp5_transition_dynamics_v1.json`](../../evaluations/results/state_engine_tp5_transition_dynamics_v1.json):

- 8 of 8 frozen cases matched;
- 8 of 8 reverse-order deterministic replays matched;
- all 10 required checks passed;
- zero product-isolation or causal-gate violations; and
- zero model calls, input tokens, output tokens, or estimated cost.

Outcome hash:
`233c24afb28a273c057c5adaf988dc77824caef267e3442ae380405b69989a15`.

The evaluator has a sabotage regression that replaces the real transition resolver with a failing
function and proves the evaluation fails. Expected states are therefore not reported from a
hard-coded actual-output table.

## Verification

- TP5 contract, adversarial lifecycle, real-evaluator sabotage, supersession, and calibration lane:
  20 passed.
- Focused TP0–TP5 and legacy relational-assertion compatibility lane: 119 passed, 1 skipped.
- Disposable TP2–TP5 SurrealKV persistence, product-isolation, and restart lane: 4 passed.
- Schema-zero real API/database restart through migration head v165: 1 passed.
- Complete root schema/migration lint, safety, application, failure, splitter, and idempotency lane:
  54 passed, 21 skipped where optional database fixtures were unavailable.
- Exact eleven-tool client, naked-kernel, package-boundary, startup, and focused TP5 group: 71 passed.
- Extension-disabled repository non-E2E gate: 6,801 passed, 47 skipped, 251 deselected, 28 existing
  warnings, zero failures.
- Ruff lint and format verification over all grounded-state and affected test modules: 21 files
  passed; the final patch also passed whitespace/error diff validation.

## Boundary and limitations

No public API endpoint or MCP tool was added. The supported thin MCP surface remains exactly eleven
tools. TP5 remains an internal Core lifecycle used by the later TP6 reasoning bridge. Extension
dynamics are represented by a typed derivation route and bounded provenance; Core does not import a
domain extension or grant it product/identity authority.

No live or paid provider, customer/private/production data, hosted mutation, historical backfill,
deployment, publication, commit, push, pull request, or shared local database was used.

This bounded result establishes deterministic contract behavior, causal fail-closed gates,
append-only restart continuity, and later-outcome calibration mechanics. It does not establish
transition accuracy, calibrated real-world probabilities, reviewer reliability, domain coverage,
production-scale throughput, consequence-rollout quality, decision benefit, K1 scale readiness, or
public K2 readiness. TP6 rollouts, TP7 promotion, TP8 scale/stability, L1 beneficial impact, T1, and
K1–K3 remain separate gates.

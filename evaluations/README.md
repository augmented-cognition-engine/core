# ACE evaluation harness

This directory provides a neutral, reproducible comparison format. It does not call ACE production
orchestration. A suite contains frozen tasks, one public rubric per task, recorded outputs, and
provider-reported operational metrics. Every variant is scored by the same evaluator.

Variants are `single_model_ungrounded` (one strong model call with the full task but no ACE memory or
orchestration), `ace`, `no_memory`, `fixed_roster`, and `no_calibration`. Live comparisons must use the
same model/version and matched input plus output token budget where the transport supports a cap. If a
transport cannot enforce that cap, record the divergence; do not silently call the run matched.

Access path (`api`, `subscription`, or `local`) is metadata, not a quality tier. Compare like-for-like
models when possible and report path limitations separately. Cost is computed only from an explicit
suite price table or a recorded value; unknown cost remains `null`.

Run the credential-free contract suite:

```bash
uv run python -m core.engine.evaluation.cli evaluations/fixtures/offline_contract.json \
  --json-out evaluations/results/offline_contract.json \
  --markdown-out evaluations/results/offline_contract.md
```

Live suite files are deliberately opt-in and require both `--allow-paid-live` and
`ACE_EVAL_ALLOW_PAID=1`. The guard prevents an accidentally labelled live suite from spending money;
model invocation remains the responsibility of an explicit runner or captured-results workflow.

The offline fixture uses synthetic outputs and validates metric plumbing only. It must never be cited
as product-quality evidence or used to update a baseline after seeing a regression. Create a new,
versioned suite when tasks or rubrics change, and retain prior results.

After the two-phase M2 verifier has produced a successful
`evaluations/results/m2_signature_live.json`, run the live comparison explicitly:

```bash
uv run python -m core.engine.evaluation.live_runner
```

This invokes the configured model for the strong ungrounded baseline and the ACE
no-memory, fixed-roster, and loop-context no-calibration variants. It records
unavailable provider token/cost data as unknown. The frozen n=1 result is evidence
of material memory use, not general quality superiority; token budgets were not
transport-matched and blinded human judgment remains future work.

## State Engine TP0 current-runtime baseline

The TP0 baseline runs the supported thin MCP contract against the owner-approved 40-case temporal
corpus. It is provider-free and write-free because it measures whether current ACE exposes the
structured State Engine input/output contract, not whether an unconstrained model can write
plausible prose after seeing the test answers:

```bash
uv run python -m core.engine.grounded_state.baseline
```

The frozen environment, budgets, seed, scoring rules, and limitations live in
[`state_engine_tp0_runtime_baseline_v1.json`](fixtures/state_engine_tp0_runtime_baseline_v1.json).
The recorded result is honestly `capability_not_established`: 0 exact matches and 40 unsupported
cases, with zero model calls and database writes. See the generated
[baseline report](results/state_engine_tp0_runtime_baseline_v1.md) and the durable
[evidence record](../docs/evidence/state-engine-tp0-runtime-baseline-v1.md).

## State Engine TP3 candidate retrieval

The provider-free TP3 evaluator runs the predeclared multi-signal retrieval target against the
frozen TP0 corpus without a database, network connection, or model call:

```bash
uv run python -m core.engine.grounded_state.candidate_evaluation
```

The frozen configuration and budgets live in
[`state_engine_tp3_candidate_retrieval_v1.json`](fixtures/state_engine_tp3_candidate_retrieval_v1.json).
The recorded result reports 100% gold-neighbor recall at `k=20`, zero false associations across the
six directed negative controls, deterministic replay, vector/entity/temporal ablations, and an
inspectable vector-index-unavailable fallback. This bounded 62-occurrence fixture result establishes
TP3 contract behavior, not production-scale retrieval quality. See the generated
[candidate report](results/state_engine_tp3_candidate_retrieval_v1.md) and the durable
[evidence record](../docs/evidence/state-engine-tp3-multi-signal-candidate-retrieval-v1.md).

## State Engine TP4 belief-state projection

The provider-free TP4 evaluator compiles the owner-reviewed semantic inputs, then executes the
predeclared v1 epistemic ontology, reviewed-assertion policy, resolver, real belief projector, causal
negative controls, product isolation, and reverse-order replay across 13 selected TP0 cases:

```bash
uv run python -m core.engine.grounded_state.belief_evaluation
```

The immutable target and zero-provider budget live in
[`state_engine_tp4_belief_projection_v1.json`](fixtures/state_engine_tp4_belief_projection_v1.json).
The recorded machine result includes every actual projection hash and matches 13 of 13 expected
states and 13 of 13 deterministic replays,
with zero product-isolation, causal-negative-control, or unlinked-operational-entry violations and
zero model calls, tokens, or cost. Database/service restart and public-surface checks are deliberately
outside the pure evaluator and are recorded in the durable
[TP4 evidence record](../docs/evidence/state-engine-tp4-belief-state-projection-v1.md). This bounded
fixture proves contract behavior, not production-scale belief or causal quality. See the frozen
[`state_engine_tp4_belief_projection_v1.json`](results/state_engine_tp4_belief_projection_v1.json)
result. Its outcome hash is
`f09127fda74a31246c69eded4e78983f9a6678d770de2134082c21e5bd757bd0`.

## State Engine TP5 transition dynamics

The provider-free TP5 evaluator builds real TP4 belief projections, then executes the frozen
transition proposal, complete challenge, review/resolution, deterministic branch-input,
causal-negative-control, product-isolation, impossible-assignment, and later-outcome calibration
paths across eight selected TP0 cases:

```bash
uv run python -m core.engine.grounded_state.transition_evaluation
```

The immutable target, bounds, policy versions, and zero-provider budget live in
[`state_engine_tp5_transition_dynamics_v1.json`](fixtures/state_engine_tp5_transition_dynamics_v1.json).
The recorded result matches 8 of 8 expected cases and 8 of 8 reverse-order replays, passes all ten
required checks, and reports zero product-isolation or causal-gate violations and zero model calls,
tokens, or cost. Each case records the exact challenge, transition revision, and deterministic
branch-input hashes. Database/service restart evidence is recorded separately in the durable
[TP5 evidence record](../docs/evidence/state-engine-tp5-transition-dynamics-v1.md). This bounded
fixture proves contract mechanics, not real-world transition accuracy or calibration quality. See
the frozen
[`state_engine_tp5_transition_dynamics_v1.json`](results/state_engine_tp5_transition_dynamics_v1.json)
result. Its outcome hash is
`233c24afb28a273c057c5adaf988dc77824caef267e3442ae380405b69989a15`.

## State Engine TP6 bounded consequence rollouts

The provider-free TP6 evaluator builds real TP4 projections and provisionally eligible TP5
revisions, then executes the frozen Evidence Query/context, action/no-action/named-alternative
rollout, independent challenge, I3 matched-control, prompt-injection, simulated/observed isolation,
product-isolation, replay, and later-outcome reconciliation checks:

```bash
uv run python -m core.engine.grounded_state.rollout_evaluation
```

The immutable target, seed, exact TP3–TP6 policy versions, five scenarios, eleven checks, negative
controls, bounds, and zero-provider budget live in
[`state_engine_tp6_consequence_rollout_v1.json`](fixtures/state_engine_tp6_consequence_rollout_v1.json).
The result matches 5 of 5 scenarios and 2 of 2 deterministic replays, passes all eleven checks, and
reports zero product-isolation, prompt-authority, or simulated-observation violations and zero calls,
tokens, latency, retries, or cost. The two preliminary evaluator failures are retained beside the
passing result. Database/service/API restart evidence is recorded in the durable
[TP6 evidence record](../docs/evidence/state-engine-tp6-consequence-rollouts-v1.md). This bounded
fixture proves contract mechanics, not real-world forecast accuracy, calibration, scale, decision
quality, or benefit. See the frozen
[`state_engine_tp6_consequence_rollout_v1.json`](results/state_engine_tp6_consequence_rollout_v1.json)
result. Its outcome hash is
`dfeeb1128166b6dc93bfb41a8911b8a9d3fd3a298a6cd85fff7d709783aab915`.

## State Engine TP7 explicit promotion and feedback

The provider-free TP7 evaluator runs inside the real disposable persistence/restart acceptance so
it can execute the production proposer, review, atomic memory persistence, database restart, fresh
retrieval, correction, and I3 paths rather than score a fabricated trace:

```bash
uv run pytest \
  tests/test_grounded_state_ingestion.py::test_tp7_promotion_feedback_memory_use_and_correction_survive_restart \
  -q --tb=short
```

The target was frozen before implementation in
[`state_engine_tp7_promotion_feedback_v1.json`](fixtures/state_engine_tp7_promotion_feedback_v1.json).
It binds four positive cases, fourteen adversarial cases, every lifecycle disposition, 26 required
checks, three production-path sabotage checks, deterministic bounds, exact TP0/TP6 hashes, and a
zero-provider budget. The recorded
[`state_engine_tp7_promotion_feedback_v1.json`](results/state_engine_tp7_promotion_feedback_v1.json)
result passes all cases and checks with zero calls, tokens, latency, retries, cost, unauthorized
memory writes, simulated-observation violations, or beneficial-impact claims. Its outcome hash is
`d35a4543f63ac021bd398dbc0c7d76bd0d92632effd321f4d774208ae4a7866f`.

The same acceptance replaces the production proposer, atomic persistence method, and later
retrieval method with fake implementations and proves the evaluator turns red. This establishes a
bounded governed promotion path, not conclusion correctness, reviewer reliability, autonomous
learning, scale, decision quality, or benefit. See the durable
[TP7 evidence record](../docs/evidence/state-engine-tp7-promotion-feedback-v1.md).

## State Engine TP8 scale and stability

TP8 freezes a synthetic/public-safe 200,000-claim, 236,000-semantic-record workload and runs it
through the production ingestion, candidate, evidence-query/pack, belief, transition, rollout, and
reasoning-use services on disposable SurrealKV. The packaged runner exposes freeze checking,
focused schema preparation, bounded load/resume, counts, sustained ingestion, adapter comparison,
large-corpus planes, State Engine planes, and deterministic current-head migration interruption:

```bash
uv run python scripts/run_state_engine_tp8.py freeze-check
uv run python scripts/run_state_engine_tp8.py --url ws://127.0.0.1:18008 prepare
uv run python scripts/run_state_engine_tp8.py --url ws://127.0.0.1:18008 load
uv run python scripts/run_state_engine_tp8.py --url ws://127.0.0.1:18008 counts
uv run python scripts/run_state_engine_tp8.py --url ws://127.0.0.1:18008 sustained
uv run python scripts/run_state_engine_tp8.py --url ws://127.0.0.1:18008 planes
uv run python scripts/run_state_engine_tp8.py --url ws://127.0.0.1:18008 state-planes
```

Every database target must be explicitly disposable. Failure flags intentionally stop database or
client processes and should be used only with recorded PIDs and stores. The frozen
[`state_engine_tp8_scale_stability_v1.json`](fixtures/state_engine_tp8_scale_stability_v1.json)
contains identities, counts, hardware, topology, versions, bounds, failure points, and thresholds.
The [machine summary](results/state_engine_tp8_scale_stability_v1.json),
[raw outputs](results/state_engine_tp8_raw), [readiness decision](results/state_engine_tp8_readiness_v1.md),
and [durable evidence](../docs/evidence/state-engine-tp8-scale-stability-v1.md) publish passing and
preliminary failing results. K1 is ready for the named single-node capability; K2 and K3 remain
candidate pending the explicit pre-R7 packet.

## State Engine K1-K3 readiness audit

The follow-on audit freezes the exact pre-R7 target before measurement, revalidates K1 without
repeating TP8's expensive trials, repeats all eight TP5 domains five times beside the retained large
corpus, and runs five repeated fresh database/API/worker/thin-client K3 journeys:

```bash
uv run python scripts/run_state_engine_readiness.py freeze-check
uv run python scripts/run_state_engine_readiness.py --url ws://127.0.0.1:18009 k1
uv run python scripts/run_state_engine_readiness.py --url ws://127.0.0.1:18009 k2
uv run python scripts/run_state_engine_readiness.py k3 --store /path/to/disposable/store \
  --raw-dir evaluations/results/state_engine_k1_k3_raw/k3-final \
  --k2-result evaluations/results/state_engine_k1_k3_raw/k2-domain-matrix.json
```

The [machine summary](results/state_engine_k1_k3_readiness_v1.json),
[readable result](results/state_engine_k1_k3_readiness_v1.md), and
[durable evidence](../docs/evidence/state-engine-k1-k3-readiness-v1.md) advance K1, K2, and K3 to
ready for the declared bounded single-node capabilities. Host-specific raw and preliminary process
artifacts are retained outside the release; their final hashes and failure summary remain in the
published records. R7 is unblocked but was not started. The packet makes no real-world causal-
accuracy, calibrated-forecasting, beneficial-impact, distributed, deployment, or release-readiness
claim.

## Decision-delta receipts

The IA-01 fixture generalizes the materiality contract without rerunning M2 or invoking a provider:

```bash
UV_CACHE_DIR=/tmp/ace-ia01-uv-cache uv run python -m core.engine.evaluation.decision_delta \
  evaluations/fixtures/decision_delta_contract_v1.json \
  --json-out evaluations/results/decision_delta_contract_v1.json \
  --markdown-out evaluations/results/decision_delta_contract_v1.md
```

`ace.decision-delta-receipt/v1` records exact structured before/after decisions, matched-control
conditions, memory identity/provenance, six separate evidence levels, route and surface provenance,
operational metrics, replay hashes, and degraded reasons. The eight recorded tasks deliberately
include irrelevant, contested, invalidated, null, harmful, and mismatched-control cases. The
cross-path case is deterministic portability conformance—not live cross-model quality evidence.
See the generated [comparison report](results/decision_delta_contract_v1.md).

## I3 intelligence-use receipts

The I3 suite promotes decision-delta semantics into the supported task/Living Product Graph read
contract and limits causal comparison to the six structured I1 decision fields:

```bash
uv run python -m core.engine.evaluation.decision_delta \
  evaluations/fixtures/i3_intelligence_use_v1.json \
  --json-out evaluations/results/i3_intelligence_use_v1.json \
  --markdown-out evaluations/results/i3_intelligence_use_v1.md
```

`intelligence-use-receipt-v1` covers material, null, irrelevant, reflected-only, stale,
invalidated, contested, harmful, product-isolation, route-mismatch, evaluation-failure,
partial-lineage, and restart cases. The matched live subscription-backed route is frozen in
`evaluations/results/i3_live_provider_v1.json`; rerun it only under the recorded one-treatment/
one-control stopping rule with `scripts/run_i3_live_provider.py`. Material influence remains
distinct from beneficial impact, which is outside I3.

## L1 foresight-impact gate

The L1 evaluator computes later-outcome scores from a checksum-frozen public-data probe and refuses
to promote favorable subset comparisons:

```bash
python3 -m scripts.evaluate_l1_foresight_impact \
  --csv /path/to/checksum-verified/online_shoppers_intention.csv \
  --fixture evaluations/fixtures/l1_foresight_impact_v1.json \
  --result evaluations/results/l1_foresight_impact_v1.json
```

`ace.foresight.impact-evaluation/v1` requires no-foresight, naïve/base-rate, and matched model-only
controls, cluster-aware uncertainty, pre-outcome resolution lineage, material use, outcome
provenance, and supported intervention/confounder attribution. The current probe is intentionally
`benefit_not_established`: it is slightly worse than persistence, its eight-cluster intervals span
zero, and it has no matched model-only or intervention evidence. See the
[L1 evidence gate](../docs/evidence/l1-foresight-impact-evidence.md).

The separately frozen prospective protocol can be checked before any cohort exists:

```bash
python3 -m scripts.verify_l1_preregistration \
  --registration evaluations/fixtures/l1_preregistration_v1.json \
  --result evaluations/results/l1_preregistration_readiness_v1.json
```

Its historical recorded state is `collection_not_started`. The stricter pre-outcome executable-
protocol audit is reproducible with:

```bash
python3 -m scripts.verify_l1_collection_start \
  --registration evaluations/fixtures/l1_preregistration_v1.json \
  --readiness evaluations/results/l1_preregistration_readiness_v1.json \
  --attempt evaluations/fixtures/l1_collection_start_v1.json \
  --audit-code core/engine/evaluation/l1_collection_start.py \
  --audit-script scripts/verify_l1_collection_start.py \
  --intake-code core/engine/evaluation/l1_preregistration.py \
  --analysis-code core/engine/evaluation/foresight_impact.py \
  --result evaluations/results/l1_collection_start_v1.json
```

That receipt is `invalidated`: collection did not start, no target outcome was inspected, and the
impact evaluator was not invoked. The v1 registration cannot accept a later cohort because the
cohort, exact route, primary outcome, observation schema, analysis window, cluster definition,
attribution verification, leakage boundaries, and randomized-arm estimator were not operationally
frozen. A successor requires a new preregistration identity and hash before collection.

The passing agent-only executable successor is frozen as
`ace.foresight.impact-agent-benchmark-preregistration/v7`. It uses 48 independent workload
clusters, exact blocked assignment across selectively applicable resolved ACE foresight,
last-observation persistence, frozen base rate, and matched model-only. All 192 main decisions are
durable before one fresh workload seed per cluster is created and shared across its four arms. The
protocol permits no replacement, no interim analysis, and one terminal cluster-level analysis.
Reproduce its no-outcome validation with:

```bash
uv run python -m scripts.run_l1_agent_benchmark dry-run \
  --protocol evaluations/fixtures/l1_agent_benchmark_v7.json \
  --benchmark-code core/engine/evaluation/l1_agent_benchmark.py \
  --collection-runner scripts/run_l1_agent_benchmark.py \
  --out /tmp/l1_agent_benchmark_dry_run_v7.json
```

The recorded live route, closed collection, and single analysis are
`evaluations/results/l1_agent_benchmark_route_v7.json`,
`evaluations/results/l1_agent_benchmark_collection_v7.json`, and
`evaluations/results/l1_agent_benchmark_analysis_v7.json`. All 192 cases and 48 clusters were
eligible. The terminal result is `benefit_supported`: the cluster-adjusted 95% lower bound is above
zero against last-observation persistence, naïve/base-rate, and matched model-only. Do not rerun the
analysis or start another v7 cohort. V2/v3 invalidations, v4's integrity failure, v5's negative
all-controls result, and v6's single-case I3 lineage failure remain preserved rather than rewritten;
exact v6 and v7 benchmark/runner sources are archived in `evaluations/source/`.

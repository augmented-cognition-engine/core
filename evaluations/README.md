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
[L1 evidence gate](../docs/l1-foresight-impact-evidence.md).

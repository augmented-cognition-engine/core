# I2 attributable-deliberation deterministic report

Scenario: Online Retail II cancellation-policy rollout

Final bounded decision: Keep the cancellation-policy rollout staged until cancellation and repeat-purchase guardrails are measured.

| Shape | Coverage | Synthesis | Conflicts | Completeness |
|---|---|---|---:|---|
| independent | complete | not_applicable | 0 | complete |
| pipeline | complete | complete | 1 | complete |
| team | partial | degraded | 0 | degraded |
| adversarial | complete | complete | 2 | complete |

This report uses deterministic final artifacts and zero model calls. It demonstrates the receipt contract,
not hidden reasoning access, correctness, causality, benefit, or general model quality.

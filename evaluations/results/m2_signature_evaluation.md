# Evaluation: m2-signature-live-v1

Run kind: **live**

| Variant | Tasks | Quality | Continuity | Latency ms | Calls | Tokens | Est. cost USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| single_model_ungrounded | 1 | 0.7500 | 0.0000 | 30235 | 1 | 1781 | unknown |
| ace | 1 | 1.0000 | 1.0000 | 352627 | unavailable | unavailable | unknown |
| no_memory | 1 | 0.5000 | 0.0000 | 204689 | unavailable | unavailable | unknown |
| fixed_roster | 1 | 0.7500 | 0.0000 | 109965 | unavailable | unavailable | unknown |
| no_calibration | 1 | 1.0000 | 1.0000 | 148095 | unavailable | unavailable | unknown |

Access paths are descriptive, not quality tiers: subscription.

## Unsupported documentation claims

- ACE outperforms the baseline (n=1, no blinded human judge, unmatched observable token budgets).
- No-calibration is a complete calibration ablation; it removes loop-context calibration only.
- Per-variant token/cost attribution is unavailable for the recorded ACE and ablation runs because they completed through a different provider singleton than the measurement probe. Raw subscription-credit ledger rows exist but cannot be attributed honestly to a variant after the fact. The runner now shares the orchestration provider for future runs.

## Live evaluations still required

- Repeat trials with a transport exposing matched token caps and provider usage.
- Add blinded human judgments and uncertainty before quality claims.

# Evaluation: offline-contract-v1

Run kind: **synthetic**

> This is a deterministic harness contract run with synthetic recorded responses. It is not evidence that ACE outperforms a baseline.

| Variant | Tasks | Quality | Continuity | Latency ms | Calls | Tokens | Est. cost USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| single_model_ungrounded | 1 | 0.7500 | 0.0000 | 100 | 1 | 105 | 0.000360 |
| ace | 1 | 0.7500 | 1.0000 | 240 | 3 | 195 | 0.000600 |
| no_memory | 1 | 0.7500 | 0.0000 | 210 | 3 | 165 | 0.000510 |
| fixed_roster | 1 | 1.0000 | 1.0000 | 260 | 4 | 230 | 0.000700 |
| no_calibration | 1 | 1.0000 | 1.0000 | 225 | 3 | 184 | 0.000572 |

Access paths are descriptive, not quality tiers: api, local, subscription.

## Unsupported documentation claims

- README: 'Nothing is hardcoded' is absolute and is not established by component tests.
- README: 'Every decision compounds in a living graph' is not supported by longitudinal outcome evidence.
- README: the model is described as swappable without published cross-provider behavioral evaluation.
- README: 'a whole committee' is broader than the documented dispatcher behavior, which may select independent execution.

## Live evaluations still required

- Run frozen prompts through ACE and the ungrounded single-model baseline using the same model and matched token budget.
- Run no-memory, fixed-roster, and no-calibration ablations through actual orchestration paths.
- Collect repeated trials for variance, blinded human quality judgments, continuity across sessions, latency, calls, provider-reported tokens, and actual or documented estimated cost.
- Repeat across API, sanctioned subscription, and local paths without assigning a quality tier to an access path.
- Publish sample size and uncertainty before claiming improvement.

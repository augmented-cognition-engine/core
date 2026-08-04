# State Engine TP8 scale and stability result

Overall result: **pass for the frozen single-node TP8 packet**

| Measure | Observed | Frozen threshold |
|---|---:|---:|
| Initial claims / semantic rows | 200,000 / 236,000 exact | at least 200,000 / 236,000 exact |
| Sustained ingestion | 990.410 claims/s | at least 20 claims/s and 68,000/day |
| Candidate retrieval p95 | 14.189 ms | at most 1,000 ms |
| Evidence query and pack p95 | 16.510 ms | at most 1,500 ms |
| Belief / transition / rollout | 7.493 / 10.815 / 13.131 ms | at most 2,000 / 2,000 / 3,000 ms |
| Initial storage | 826,015,744 bytes | at most 2,147,483,648 bytes |
| Database restart | about 11 seconds | at most 15 seconds |
| Restore | 28.97 seconds | at most 300 seconds |
| Product / simulation / raw-memory violations | 0 / 0 / 0 | 0 |
| Provider calls / tokens / cost | 0 / 0 / $0 | 0 / 0 / $0 |

Database, adapter, client, transaction-child, and current-head migration failures were injected and
recovered at exact receipt boundaries. Schema zero, v0.1.x upgrade, backup/restore, current and N−1
extension envelopes, naked kernel, exact eleven-tool thin MCP, package boundary, and same-database
versus external-content adapter semantics passed.

Preliminary load and query failures remain in the machine result and raw directory. Arbitrary
mid-file interruption of historical v014 failed closed and is unsupported; v167→v168 interruption
and resume passed.

Readiness: **K1 ready; K2 candidate; K3 candidate**. See the
[machine result](state_engine_tp8_scale_stability_v1.json),
[readiness receipt](state_engine_tp8_readiness_v1.md), [raw outputs](state_engine_tp8_raw), and
[durable evidence record](../../docs/evidence/state-engine-tp8-scale-stability-v1.md).

# Pre-v1.0 RAG retrieval acceptance v1

Status: **passing for the frozen provider-free ranking packet**

| Measure | Result | Frozen threshold |
|---|---:|---:|
| Cases | 5 | 5 |
| Recall@5 | 100% | 100% |
| Mean reciprocal rank | 1.000 | at least 0.800 |
| False associations | 0 | 0 |
| Product-isolation violations | 0 | 0 |
| Superseded-correction violations | 0 | 0 |
| No-answer distance-gate violations | 0 | 0 |

Fixture hash: `7e21336f34d51ba0fb8ff9eba0692aa501e29016a2c0d082621c8b506e81122d`

Result hash: `6df690e598e3cebf7f60713f0926f8ad5747f9276c0ceaa8cc66255b1355e3f9`

The implementation also received a disposable `EXPLAIN FULL` verification on 2026-08-13 against the
exact Compose-pinned SurrealDB 3.2.3 image. The vector query produced `KnnScan` using
`insight_hnsw`, with product and active-state predicates pushed into the scan. The lexical query
produced `FullTextScan` using `insight_search` and ordered the computed `search::score`. The bounded
machine receipt is [`rag_retrieval_surreal_plan_v1.json`](rag_retrieval_surreal_plan_v1.json).

Current-main reconciliation on 2026-08-14 used base `cd16703` (Core 0.8.3 plus single-user owner
authority). The expanded implementation and contract lane passed 95 tests, and the authority,
onboarding-unit, and frozen-public-contract lane passed 92 tests. Both database-backed RAG lifecycle
tests passed against a fresh, fully migrated SurrealDB 3.2.3 instance. The broader database-backed
onboarding lane passed 18 of 19 tests; its one `originating_event` linkage failure reproduces unchanged
on untouched `origin/main` and is therefore not introduced by this packet. Ruff formatting/lint and
Git whitespace validation passed.

This bounded fixture validates ranking mechanics and required negative controls. It does not claim
customer-corpus relevance, multilingual quality, high-concurrency capacity, or distributed
availability.

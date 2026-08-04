# ACE State Engine K1-K3 readiness evidence v1

Status: **bounded pre-R7 audit complete; K1, K2, and K3 ready; R7 unblocked, not started**

This record closes the explicit readiness packet left by TP8. The authoritative machine result is
[`state_engine_k1_k3_readiness_v1.json`](../../evaluations/results/state_engine_k1_k3_readiness_v1.json),
the readable result is
[`state_engine_k1_k3_readiness_v1.md`](../../evaluations/results/state_engine_k1_k3_readiness_v1.md),
and the frozen target is
[`state_engine_k1_k3_readiness_v1.json`](../../evaluations/fixtures/state_engine_k1_k3_readiness_v1.json).
The target file SHA-256 is
`0818b3b8acfd86051bd13ff1e6111748d42a78a617133bd13e75d40a7e55df00`.
The current classification delta is in the
[`state-engine-core-boundary-readiness-v1.md`](../design/state-engine-core-boundary-readiness-v1.md)
addendum; the hashed TP8 boundary source remains unchanged.

## What was measured

K1 revalidated the frozen TP8 source hashes, dataset identities, retained corpus counts, published
single-node performance receipts, exact eleven-tool boundary, extension ownership decisions,
product isolation, and simulation/observation separation. The retained post-sustained store held
220,000 claims and 256,000 semantic records. The expensive TP8 scale and recovery trials were not
repeated.

K2 repeated all eight frozen TP5 domains five times in fresh product scopes beside that corpus. The
40 results exactly matched review state, causal strength, rollout eligibility, and degraded state;
all 40 replayed deterministically; 35 abstained as required; all challenges completed; the five
mechanistic cases calibrated against the predeclared matched/contradicted sequence without rewriting
their original revisions. Transition p95 was 8.924 ms. Unsupported assertion acceptances,
provenance failures, cross-product visibility, provider activity, retries, and cost were all zero.

K3 ran five repeated journeys through real durable task and extension-invocation routers, a
production worker process, SurrealKV, and fresh unchanged eleven-tool clients. Each journey created
control and action/no-action tasks, accepted an authority-gated promotion, reconciled a frozen
matched later outcome, restarted the database/API/worker, demonstrated exact decision-material use
from a fresh client, captured a correction, superseded the initial promotion, restarted again, and
used only the corrected authoritative memory. Task p95 was 81.799 ms, promotion p95 42.534 ms,
retrieval p95 11.214 ms, and maximum full restart 2.186 seconds. All five journeys passed with zero
failures, retries, degraded states, isolation leaks, simulated observations, or provider use. The
authoritative clean-scope run executed all 35 task submissions freshly with zero idempotent replays.

## Defect and audit trail

One audit-blocking product defect was fixed: the production later-use bridge now preserves an exact
matched comparison already present in the runtime trace when it delegates to the TP7 promotion
service. It does not create comparison evidence. The focused regression is
`test_production_later_use_bridge_preserves_recorded_matched_comparison`. No migration changed.

The retained TP8 store also exposed a preparation limitation: its selectively applied State Engine
schema planes did not make it a full monolith API database. On the disposable audit clone, the
harness verified the current required table set, completed three missing additive base-runtime
tables, and reconciled the stale schema receipt. The final bounded K3 API deliberately mounted only
the production task, extension-invocation, intelligence, and capture surfaces under test; unrelated
scheduler, runner, canvas, and notification subsystems were excluded. The production worker and
thin client were not replaced.

All preliminary failures remain indexed in the retained local
`evaluations/results/state_engine_k1_k3_raw/preliminary-failures.json` audit directory. That raw
directory is intentionally not a release artifact: it contains host-specific process paths, large
superseded trials, and operational logs. The release carries the complete canonical machine receipt,
readable result, raw K1/K2/K3 hashes, and this failure summary instead. Preliminary failures include
wrong retained-database selection, audit mapping and dependency-order defects, stale schema receipt
and missing runtime-table findings, an overbroad monolith startup dependency, rollout-coordinate
mapping, and omitted bounded API routers. Thresholds and frozen expectations were never changed
after measurement.

## Commands and environment

The reproducible runner supports:

```bash
uv run python scripts/run_state_engine_readiness.py freeze-check
uv run python scripts/run_state_engine_readiness.py --url ws://127.0.0.1:18009 k1
uv run python scripts/run_state_engine_readiness.py --url ws://127.0.0.1:18009 k2
uv run python scripts/run_state_engine_readiness.py k3 --store /path/to/disposable/store \
  --raw-dir evaluations/results/state_engine_k1_k3_raw/k3-final \
  --k2-result evaluations/results/state_engine_k1_k3_raw/k2-domain-matrix.json
uv run python scripts/run_state_engine_readiness.py summarize \
  --k1-result evaluations/results/state_engine_k1_k3_raw/k1-revalidation.json \
  --k2-result evaluations/results/state_engine_k1_k3_raw/k2-domain-matrix.json \
  --k3-result evaluations/results/state_engine_k1_k3_raw/k3-journeys.json
```

The measured environment was macOS 26.6 arm64, Python 3.12.13, uv 0.11.14, and SurrealDB 3.2.1.
The raw K1/K2/K3 hashes are respectively
`ff781718d0f81bf8e540d33d07694aa9c66d7d5ec443a1377044074e5afa618b`,
`159a01b17549cf53c1ea424612654a60760ad29d659e13b1b8b83c25a1515700`, and
`3e104d732d4f56f42fefeee32c31ccfcdca8466bbbcc440c64d9b58a779d564c`.

## Verification and limits

- Focused State Engine lane: 62 passed, 10 deselected.
- Schema/migration lane: 51 passed, 2 deselected.
- Thin-client/naked-kernel/package-boundary lane: 31 passed, 1 skipped.
- Full extension-disabled non-E2E regression: 6,840 passed, 47 skipped, 258 deselected.
- Ruff: all checks passed; format: 1,878 files already formatted.
- Compilation, frozen-fixture integrity, JSON validation, and diff checks: passed.

No real-world causal accuracy, calibrated forecasting, beneficial impact, general learned world
model, autonomous learning, distributed-system, hosted-service, deployment, release, or v0.2.0
readiness claim follows from this audit. L1 remains candidate, and T1, B1, E1, and release readiness
remain unchanged. R7 may now be planned separately; this audit did not start it.

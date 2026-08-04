# State Engine K1-K3 readiness audit v1

Status: **passed — K1 ready, K2 ready, K3 ready; R7 unblocked but not started**

The audit repeated the bounded packet named by TP8 without changing its target after measurement.
It used the retained synthetic/public-safe TP8 corpus through disposable local clones, loopback
processes, deterministic provider-free reasoning, and fresh product scopes. It did not repeat the
expensive TP8 load, failure-injection, migration, or backup/restore trials.

The frozen configuration is
[`state_engine_k1_k3_readiness_v1.json`](../fixtures/state_engine_k1_k3_readiness_v1.json), SHA-256
`0818b3b8acfd86051bd13ff1e6111748d42a78a617133bd13e75d40a7e55df00`. The complete machine
receipt is [`state_engine_k1_k3_readiness_v1.json`](state_engine_k1_k3_readiness_v1.json). Raw passing
and preliminary process artifacts remain in the local audit worktree, outside the release artifact;
their final K1/K2/K3 hashes are retained below.

## Decisions

| Gate | Decision | Measured result |
|---|---|---|
| K1 | ready | Frozen TP8 identities and evidence hashes matched; the retained store reconciled 220,000 claims and 256,000 semantic records; all Core-boundary checks held; the expensive TP8 trials were not repeated. |
| K2 | ready | Five repetitions across eight frozen domains produced 40/40 exact case matches, 40/40 deterministic replays, 40 challenges, 35 required abstentions, five scored predeclared calibrations, and zero unsupported acceptances, provenance violations, isolation violations, provider calls, retries, tokens, or cost. Transition p95 was 8.924 ms against the 2,000 ms ceiling. |
| K3 | ready | Five repeated journeys produced 5/5 passing fresh-process task, promotion, outcome reconciliation, restart, later-use, correction, supersession, and post-correction retrieval paths. There were zero failures, retries, degraded states, identity/lineage/continuity failures, isolation leaks, simulation-as-observation rows, provider calls, tokens, or cost. |

K3 task p95 was 81.799 ms against 5,000 ms, promotion p95 was 42.534 ms against 2,000 ms,
fresh-retrieval p95 was 11.214 ms against 1,000 ms, and maximum database/API/worker restart was
2.186 seconds against 45 seconds. All five action/no-action rollouts reconciled to the predeclared
`matched` outcome with score 1.0 while preserving the original rollout revision. Every fresh thin
client exposed exactly eleven tools. All 35 authoritative task submissions were fresh executions,
with zero idempotent replays. Each later task recorded retrieved, injected, reflected, and
decision-material use through an exact matched control; none claimed beneficial impact.

## Narrow product defect fixed

The production promoted-memory task bridge discarded an already-recorded matched comparison when
it persisted the later-use receipt. That made honest fresh later use stop below decision-material
even though the runtime trace contained the exact treatment/control material. The bridge now passes
that existing comparison to `PromotionService.record_later_use`; it does not infer or synthesize a
comparison from task prose. A focused regression covers the production call path. No schema or
migration changed.

## Audit findings and preserved failures

The retained TP8 store was sufficient for K1/K2 State Engine planes but was not directly a full API
startup database: its State Engine v168 tables coexisted with a stale v1 schema receipt and three
missing base-runtime tables (`framework`, `discipline`, and `reasoning_event`). The audit verified
the required table set, completed only those additive definitions, and advanced the receipt on the
disposable clone. The original retained store was not changed. K3 then used a bounded process that
mounted the production task, extension-invocation, intelligence, and capture routers with the real
durable task lifecycle, plus the ordinary production worker and unchanged thin client.

Harness mapping, persistence-order, startup-surface, and result-assembly failures were not hidden or
reclassified as product results. Their machine index and referenced process logs remain preserved in
the maintainer's local raw audit directory, which is excluded from the release because it contains
host-specific paths, large superseded trials, and operational logs. No dataset identity, repetition
count, expected outcome, provider budget, latency ceiling, or readiness threshold was loosened.

## Verification

- Focused State Engine, production bridge, and grounded-state regression: 62 passed, 10 deselected.
- Schema and migration safeguards: 51 passed, 2 deselected.
- Thin-client, naked-kernel, and package-boundary checks: 31 passed, 1 skipped.
- Full extension-disabled non-E2E regression: 6,840 passed, 47 skipped, 258 deselected.
- Ruff: all checks passed; format: 1,878 files already formatted.
- Compilation, frozen-fixture integrity, JSON validation, and `git diff --check`: passed.

## Environment and artifact identity

- macOS 26.6 (25G72), arm64
- Python 3.12.13; uv 0.11.14; SurrealDB 3.2.1
- K1 raw SHA-256: `ff781718d0f81bf8e540d33d07694aa9c66d7d5ec443a1377044074e5afa618b`
- K2 raw SHA-256: `159a01b17549cf53c1ea424612654a60760ad29d659e13b1b8b83c25a1515700`
- K3 raw SHA-256: `3e104d732d4f56f42fefeee32c31ccfcdca8466bbbcc440c64d9b58a779d564c`
- Machine summary file SHA-256: `6d6c582f8d2e007fe74dfc5d52c312c7b8ee3cd924432152265d96e3ab5b9c99`
- Machine summary outcome hash: `6ebfb55ae0b4bc007ba63a7c0ca2974c8caa4aed2f8cc62d505678076f84735f`

## Limits

This is synthetic/public-safe, deterministic, provider-free, single-node loopback evidence. K2
measures inspectable contract mechanics, abstention, and predeclared calibration behavior—not
real-world causal or forecast accuracy. K3 proves durable material use, not beneficial impact.
Distributed operation, hosted providers, deployment, release, L1, T1, B1, E1, and v0.2.0 release
readiness remain outside this audit. R7 is unblocked by these gate decisions but was not executed or
authorized here.

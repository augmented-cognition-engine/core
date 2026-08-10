# T1B execution limits and timeout receipts work packet

Status: **active candidate for ACE 0.5.0; does not complete T1 or B1**

## Outcome

ACE Core enforces a caller- or trusted-extension-declared wall-clock limit around one durable task
attempt and records an honest terminal timeout receipt. Every attempt that terminates in the current
Core process reports its measured elapsed wall time and explicitly states which provider, CPU,
memory, distributed, and cross-process resource facts remain unavailable. Restart reconciliation
preserves the declared limit but does not invent elapsed time that the new process never observed.

## Contract

- `task-execution-limits-v1` declares one bounded `wall_time_seconds` value.
- The accepted and running task receipt exposes the effective limit and its process-local topology.
- Core enforces the deadline around orchestration, cancels the in-process orchestration coroutine,
  and persists `status=degraded`, `execution.state=timed_out`, and `error.code=execution_timeout`.
- `task-resource-report-v1` records Core-measured elapsed wall time, the effective deadline, whether
  it was exceeded, and terminal provider usage when orchestration returned it.
- Duplicate submission reuses the immutable receipt; a changed limit changes direct-task replay
  identity. Extension retries remain new linked attempts under the existing retry contract.
- Trusted extension task plans may declare the same neutral limit. Domain Packs gain no imperative
  execution or control-flow capability.

## Explicit limits

T1B does not claim CPU or memory enforcement, distributed deadlines, remote-worker cancellation,
portable container equivalence, resumable provider generation, or complete provider usage after a
deadline interrupts orchestration. Those remain later T1 and B1 packets.

## Acceptance

T1B may be marked candidate only when focused direct-task and extension tests prove declared-limit
propagation, deterministic replay identity, completed resource reporting, timeout cancellation,
bounded public failure data, and retry eligibility. Repository-wide verification and an independent
artifact journey remain required before T1B can pass.

# T1C durable task attempt and replay work packet

Status: **active candidate for ACE 0.5.0; does not complete T1 or B1**

## Outcome

Every newly accepted Core task has a durable `task-attempt-v1` identity in its first persisted
receipt. After a direct task terminates as `failed` or is reconciled to `degraded` following a
runtime restart, an authenticated caller can explicitly create one linked successor from the
persisted request. Duplicate and concurrent process-local resume requests converge on that same
successor. ACE does not claim that provider generation resumes mid-token.

## Contract

- `task-attempt-v1` records the attempt number, root task, predecessor, chosen successor, retry
  reason, authenticated actor, request time, and retry-policy version.
- Core predeclares the task ID before the first task-row write, so attempt one and its root identity
  are durable together; legacy rows receive a bounded attempt-one projection.
- `POST /tasks/{task_id}/resume` returns `pending`, `running`, `completed`, and `cancelled` attempts
  unchanged. Only `failed` and `degraded` direct attempts can create a successor.
- The original private `TaskCreate` coordinates are revalidated, then replayed with a deterministic
  successor ID and idempotency key. The predecessor records exactly one `resumed_by_task_id`.
- Resume authority is bound to the original product, authenticated principal, and any explicit
  workspace claims. Invalid or conflicting lineage fails closed.
- Extension invocations project the same generic task lineage but remain resumable only through
  `POST /extension-invocations/{task_id}/resume`, which repeats extension-owned preparation and
  authorization before Core execution.

## Explicit limits

T1C does not claim distributed exactly-once admission, cross-process locking, remote-worker
recovery, mid-token provider continuation, external-effect compensation, portable execution, or
automatic retry. The current single-process lock closes duplicate races only within one API
process; deterministic successor identity provides restart-safe replay against the shared store.

## Acceptance

T1C may be marked candidate only when focused tests prove first-write attempt identity, request
reconstruction, immutable predecessor/successor lineage, duplicate and concurrent convergence,
product/principal/workspace isolation, extension-route enforcement, invalid-lineage rejection, and
a real SurrealKV/API restart with a fresh client. Repository-wide verification and an independent
installed-artifact journey remain required before T1C can pass.

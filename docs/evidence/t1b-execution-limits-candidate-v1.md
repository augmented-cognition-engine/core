# T1B execution limits and timeout receipts candidate evidence (v1)

**Status:** candidate, merged to main; released-artifact evidence pending

**Date:** 2026-08-09

**Outcome:** second bounded T1 control primitive for ACE 0.5.0 Reasoning into Action

## Claim

The candidate adds a domain-neutral `task-execution-limits-v1` contract to direct Core tasks and
trusted extension task plans. Core can enforce a declared process-local wall-clock deadline around
orchestration and persist a terminal `degraded/timed_out` receipt with an explicit partial resource
report instead of reporting failure as success or fabricating provider usage.

This record does not pass T1 or B1. It does not establish CPU or memory enforcement, distributed
deadlines, remote-worker termination, portable container equivalence, resumable provider
generation, exactly-once external effects, compensation, or unrestricted autonomy.

## Source and artifact identity

The candidate was built on branch `codex/t1b-execution-limits` from Core main commit
`141e38bdd1a293519b75d3441a52ec003323ea4d`. [PR #72](https://github.com/augmented-cognition-engine/core/pull/72)
merged head `c11b82986bf62c215c641053e8d5d5eb39d8c75a` to main as squash commit
`701c7ef62d1087f809c372437b72064167b33a27`.

The locally built wheel retained the unreleased base version `ace-core==0.4.4`:

```text
ace_core-0.4.4-py3-none-any.whl
SHA-256 d8ea9e3619ea6560491b11263ed29e2f83c29aa4f25d627b29a89627bb7b86be
```

The wheel version is not a new release claim. A later release must bind its own tag, version,
trusted publication, public-index hashes, and installed-package journey.

## Public review and CI

PR #72 passed final-head [CI run 152](https://github.com/augmented-cognition-engine/core/actions/runs/31353132061)
before merge. The required jobs all completed successfully:

- Lint;
- Security Audit;
- Canvas typecheck, tests, and naked build;
- Tests (fast gate);
- Naked kernel with all extensions disabled; and
- Docker build and health-endpoint verification.

The PR was marked ready only after all six jobs passed, then squash merged without changing the
verified head.

## Contract result

The implementation and focused tests establish:

- direct task replay identity changes when the declared limit changes;
- trusted extension task plans propagate the same neutral limit without granting Domain Packs
  imperative control flow;
- accepted and running receipts expose the limit, enforcement mode, and current-process topology;
- deadline expiry cancels the in-process orchestration coroutine and persists
  `status=degraded`, `execution.state=timed_out`, and `error.code=execution_timeout`;
- the timeout receipt exposes Core-measured elapsed wall time, the effective deadline, incomplete
  provider telemetry, and explicit CPU, memory, and distributed-reporting limits;
- completed tasks report Core wall time plus available model-call, retry, and token telemetry;
- extension timeout receipts remain terminal, expose no fabricated output, and are eligible for a
  new linked retry under the existing attempt contract; and
- real-store restart reconciliation preserves the declared limit while refusing to invent elapsed
  time from a process that did not observe the original attempt.

The frozen ownership, acceptance, and exclusion rules are in the
[T1B work packet](../design/t1b-execution-limits-work-packet-v1.md).

## Verification

Focused task, extension, cancellation, and real-restart verification:

```text
100 passed across the focused lifecycle suite
tests/test_task_cancellation_restart.py: 1 passed against disposable SurrealKV
```

Repository regression and naked-kernel verification:

```text
7384 passed, 50 skipped, 260 deselected in 174.20s
4 passed in 0.83s
```

Repository-wide Ruff lint, format, and `git diff --check` passed before roadmap reconciliation.
The first sandboxed broad run could not bind existing localhost fixtures; rerunning with the
repository's required localhost test capability produced the clean result above. No product
failure was suppressed.

## Isolated wheel probe

The candidate wheel and all declared public dependencies were installed into a new Python 3.12
environment under `/private/tmp`. The probe ran outside the source checkout, imported
`core.engine.api.tasks` from that environment's `site-packages`, submitted a task with a 10 ms
declared limit, and used a deterministic never-completing orchestration fixture.

The installed artifact returned:

```json
{
  "status": "degraded",
  "execution_state": "timed_out",
  "deadline_exceeded": true,
  "wall_time_limit_ms": 10,
  "telemetry_completeness": "partial"
}
```

The receipt also named unavailable provider usage, CPU and memory measurement, and distributed
resource usage. This is an isolated installed-wheel contract probe, not a public-index deployment.

## Remaining closeout gate

T1B remains a candidate until a released artifact from the public package index reproduces the
bounded journey and binds the exact tag, package version, hashes, and limitations. T1A also still
awaits its released-artifact closeout.

T1 remains not ready because cross-process replay/recovery, portability, distributed topology, and
broader resource enforcement remain open. B1 remains not ready because no writable execution
adapter has yet proved the complete approval-to-action-to-review-and-promotion journey.

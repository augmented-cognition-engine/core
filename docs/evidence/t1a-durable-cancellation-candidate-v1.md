# T1A durable cancellation candidate evidence (v1)

**Status:** candidate, merged to main; released-artifact evidence pending

**Date:** 2026-08-09

**Outcome:** first bounded T1 control primitive for ACE 0.5.0 Reasoning into Action

## Claim

The candidate hardens ACE's existing experimental extension-invocation cancellation seam so an
authenticated product/user/workspace owner can stop an action that negotiated cancellation,
receive one immutable terminal cancellation fact, and recover a truthful extension receipt after
runtime restart.

This record does not pass T1 or B1. It does not establish distributed cancellation, portable
in-flight execution, exactly-once action, external-effect reversal, compensation, or unrestricted
autonomy.

## Source and artifact identity

The candidate was built from branch `codex/t1a-durable-cancellation` based on Core main commit
`6657615464644b18a479bcfd18343c16e25a10ff`. [PR #70](https://github.com/augmented-cognition-engine/core/pull/70)
merged head `ffb3c8913067099d27266149b17e210b7813556b` to main as squash commit
`e9164c2b2d9f9cb8baf901fc441078e063acdbcb`.

The locally built wheel retained the unreleased base version `ace-core==0.4.4`:

```text
ace_core-0.4.4-py3-none-any.whl
SHA-256 80cce09d06de8272db1317dd0c023be08852392a17fe2067411d87f3fb503d43
```

The wheel version is not a new release claim. A later release must bind its own tag, version,
trusted publication, public-index hashes, and installed-package journey.

## Public review and CI

PR #70 passed the final-head [CI run 148](https://github.com/augmented-cognition-engine/core/actions/runs/31349860505)
before merge. The required jobs all completed successfully:

- Lint;
- Security Audit;
- Canvas typecheck, tests, and naked build;
- Tests (fast gate);
- Naked kernel with all extensions disabled; and
- Docker build and health-endpoint verification.

The PR was mergeable, marked ready for review only after the first full run passed, and squash
merged only after the stronger final head with the real SurrealKV restart test passed the same
required workflow.

## Contract result

The implementation and focused tests establish:

- unsupported actions return `409 cancellation_unavailable` without invoking the Core lifecycle;
- active local work persists `requested` before interruption and then records `acknowledged`,
  `status=cancelled`, and `execution.usable_output=false`;
- concurrent duplicate requests serialize into one `requested → acknowledged` transition;
- repeat requests preserve the first terminal actor, reason, and timestamps for acknowledged,
  completed-before-request, and stopped-process results;
- a completion race is re-read before Core reports a stopped-process result;
- a missing owning process produces visible degraded/interrupted state rather than false success;
- startup reconciliation converts abandoned pending/running work into a terminal degraded fact; and
- startup also rebuilds the public extension receipt, preventing a stale `running` projection from
  surviving beside that reconciled task.

The frozen ownership, state, acceptance, and exclusion rules are in the
[T1A work packet](../design/t1a-durable-cancellation-work-packet-v1.md).

## Verification

Focused lifecycle and extension API verification:

```text
54 passed in 0.73s
```

Repository regression and kernel boundary verification:

```text
7380 passed, 50 skipped, 259 deselected in 177.33s
4 passed in 0.86s
```

Repository-wide Ruff lint, format, and `git diff --check` passed. Existing warnings in the broad
suite were non-failing deprecation, test-collection, fixture-key, and coroutine-cleanup warnings;
no new failure was suppressed.

The disposable real-store restart test also passed:

```text
tests/test_task_cancellation_restart.py
1 passed in 1.64s
```

## Isolated wheel probe

The candidate wheel was installed with its declared dependencies into a new Python 3.12 virtual
environment under `/private/tmp`, and the probe ran from outside the source checkout. The imported
module path resolved inside that environment's `site-packages`.

The probe supplied a persisted invocation whose pre-restart extension receipt incorrectly said
`running`, while the reconciled durable task facts represented a pending cancellation interrupted
by process loss. Calling the installed artifact's startup reconciliation produced:

```json
{
  "count": 1,
  "task_status": "degraded",
  "terminal": true,
  "cancellation": {
    "supported": true,
    "state": "process_stopped_during_cancellation",
    "requested_at": "2026-08-09T12:00:00Z",
    "acknowledged_at": "2026-08-09T12:00:01Z",
    "actor": "user:artifact"
  },
  "raw_core_output": {
    "available": false,
    "content": null
  }
}
```

This is an isolated installed-artifact contract probe with a deterministic persistence adapter. It
is not yet a public-index deployment.

## Real durable-store restart

The candidate also started a disposable SurrealDB SurrealKV process, created a real persisted
`running` task with `cancellation.state=requested` and a stale `running` extension receipt, then
invoked startup reconciliation from a fresh Python runtime process. The fresh runtime reconciled
exactly one task to terminal degraded/interrupted state, preserved the cancellation actor, reason,
and request timestamp, and rebuilt the extension receipt with no available output.

A second fresh runtime reconciled zero tasks and left the full terminal cancellation fact
unchanged. This proves restart idempotence over the real durable adapter used by the single-node
preview. It does not simulate a distributed worker, prove remote-effect reversal, or make process
termination atomic with an external system.

## Remaining closeout gate

The merged source, PR, CI, real-store restart, and local wheel identities are now recorded. The
extension-invocation surface remains explicitly experimental in capability-maturity documentation,
so merge does not silently promote a supported general cancellation API.

T1A remains candidate until a released artifact passes the same journey from the public package
index and its release evidence binds the exact tag, package version, hashes, and limitations.

Until then, the overall roadmap remains unchanged: T1 and B1 are not ready, and 0.5.0 remains next.

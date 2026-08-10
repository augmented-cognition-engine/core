# T1A durable cancellation candidate evidence (v1)

**Status:** candidate, local; public PR/CI and released-artifact evidence pending

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
`6657615464644b18a479bcfd18343c16e25a10ff`. Its eventual PR head and merge identity remain pending
and must be added before public closeout.

The locally built wheel retained the unreleased base version `ace-core==0.4.4`:

```text
ace_core-0.4.4-py3-none-any.whl
SHA-256 80cce09d06de8272db1317dd0c023be08852392a17fe2067411d87f3fb503d43
```

The wheel version is not a new release claim. A later release must bind its own tag, version,
trusted publication, public-index hashes, and installed-package journey.

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
is not yet a public-index deployment or a hard process-kill test against a real SurrealDB runtime.

## Remaining closeout gate

T1A remains candidate until all of the following are bound to the exact public source identity:

1. PR review and required GitHub checks pass;
2. the merged commit is recorded;
3. a real process-restart journey over durable storage reproduces the receipt transition;
4. the supported/public maturity wording is reconciled without broadening the claim; and
5. a released artifact, if T1A is promoted in a patch or minor release, passes the same journey from
   the public package index.

Until then, the overall roadmap remains unchanged: T1 and B1 are not ready, and 0.5.0 remains next.

# T1C durable task attempt and replay candidate evidence (v1)

**Status:** candidate, local branch; merge and released-artifact evidence pending

**Date:** 2026-08-09

**Outcome:** third bounded T1 control primitive for ACE 0.5.0 Reasoning into Action

## Claim

The candidate adds a domain-neutral `task-attempt-v1` receipt projection and explicit direct-task
resume route. Every new Core task persists its attempt-one root identity with the initial row. A
terminal failed or restart-degraded direct task can reconstruct its validated private request and
create one deterministic linked successor. Duplicate and concurrent process-local requests return
that successor rather than silently creating another attempt.

This record does not pass T1 or B1. It does not establish distributed exactly-once admission,
cross-process locking, remote-worker recovery, provider generation continuation, external-effect
compensation, portable execution, or unrestricted autonomy.

## Source and artifact identity

The candidate was built on branch `codex/t1c-durable-task-replay` from Core main commit
`bd50785055b51e165608998e83f79095f1be0cc9`. Merge, pull-request, and final CI identities remain
pending and must be reconciled after public review.

The locally built wheel retained the unreleased base version `ace-core==0.4.4`:

```text
ace_core-0.4.4-py3-none-any.whl
SHA-256 e227188ad618befd53276bf6552b7600beeb34db8a2a4c2e97e50400ebc84cf3
```

The wheel version is not a new release claim. A later release must bind its own tag, version,
trusted publication, public-index hashes, and installed-package journey.

## Contract result

The implementation and focused tests establish:

- the initial task row contains its predeclared `task-attempt-v1` identity and root task ID;
- legacy rows receive an explicit attempt-one projection without rewriting history;
- only direct `failed` or `degraded` attempts create successors, while active, completed, and
  cancelled attempts replay unchanged;
- the original `TaskCreate` coordinates are privately retained, revalidated, and replayed with a
  deterministic successor ID and idempotency key;
- the successor records its root, predecessor, attempt number, reason, authenticated actor,
  request time, and retry-policy version, while the predecessor records exactly one successor;
- duplicate and concurrent calls in one process converge on the same successor;
- product, authenticated principal, and explicit workspace mismatches return not-found;
- malformed or conflicting persisted lineage fails closed;
- generic task replay refuses extension invocations, whose dedicated route must repeat
  extension-owned preparation and authorization; and
- extension attempts project the same generic lineage without replacing their richer
  extension-invocation receipt.

The frozen ownership, acceptance, and exclusion rules are in the
[T1C work packet](../design/t1c-durable-task-replay-work-packet-v1.md).

## Real restart acceptance

The disposable SurrealKV/API journey first completed a normal direct task, then marked its durable
receipt as owned by a prior runtime. A new API process reconciled that receipt to
`degraded/runtime_restarted`. A fresh authenticated client called the generic resume route, created
attempt two from the persisted request, observed deterministic completion, inspected both sides of
the predecessor/successor link, and repeated the resume request to receive the same successor. The
same journey also verified that extension attempt two carries matching generic and
extension-specific lineage.

```text
tests/test_i1_restart_persistence.py: 1 passed in 34.39s
schema zero -> v177 on supported SurrealKV
```

This is restart-safe attempt replay, not mid-token provider continuation.

## Verification

Focused direct-task, extension, replay, concurrency, access, and restart verification:

```text
73 passed across the focused unit lifecycle suite
1 passed against disposable SurrealKV and two API processes
```

Repository regression and naked-kernel verification:

```text
7399 passed, 50 skipped, 260 deselected in 177.69s
4 passed in 0.85s
```

Repository-wide Ruff lint, format, and `git diff --check` passed before roadmap reconciliation.

## Isolated wheel probe

The candidate wheel and all declared dependencies were installed into a new Python 3.12
environment under `/private/tmp`. The probe ran from outside the source checkout and imported
`core.engine.api.tasks` from the environment's `site-packages`. It reconstructed a degraded direct
task, created attempt two, persisted the predecessor link, and repeated the request.

```json
{
  "attempt_number": 2,
  "contract_version": "task-attempt-v1",
  "duplicate_replay": true,
  "root_task_id": "task:installed_root",
  "successor_task_id": "task:retry_2722d5994bf97b1be88ef2954789e0c6"
}
```

This is an isolated installed-wheel contract probe, not a public-index deployment.

## Remaining closeout gate

T1C remains a candidate until the implementation is merged with final-head CI and a released
artifact from the public package index reproduces the bounded journey with exact tag, package
version, hashes, and limitations. T1A and T1B also still await released-artifact closeout.

T1 remains not ready because portability, distributed recovery and topology, remote execution,
and broader resource enforcement remain open. B1 remains not ready because no writable execution
adapter has proved the complete approval-to-action-to-review-and-promotion journey.

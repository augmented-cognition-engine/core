# Decision and correction receipts (I1-01 candidate)

ACE 0.1.x keeps decisions and corrections in its existing durable records. A task-backed product
decision is a `decision` linked to its originating `task`; a human correction is an `observation`
with `observation_type="correction"`. The receipt objects below are bounded public projections,
not a separate memory subsystem.

## Structured task decision

`ace_task` accepts an optional `decision` object alongside the existing task arguments:

```json
{
  "selected_option": "Keep the eleven-tool boundary",
  "scope": "ACE 0.1.x thin MCP contract",
  "assumptions": ["Backward compatibility is required"],
  "alternatives": ["Add a decision-specific tool"],
  "reconsideration_conditions": ["The existing status contract cannot carry the receipt safely"],
  "evidence_refs": ["test:i1-restart"],
  "rationale": "Use the existing task and capture paths",
  "decision_type": "direction"
}
```

These values must be supplied structurally. ACE does not extract them from the task description,
model output, logs, or prose containing words such as “accepted.” When the task completes,
`ace_status(task_id="task:…")` exposes `task.decision_receipt` with contract version
`decision-receipt-v1`:

```json
{
  "contract_version": "decision-receipt-v1",
  "decision_id": "decision:…",
  "originating_task_id": "task:…",
  "selected_option": "Keep the eleven-tool boundary",
  "scope": "ACE 0.1.x thin MCP contract",
  "assumptions": ["Backward compatibility is required"],
  "alternatives": ["Add a decision-specific tool"],
  "reconsideration_conditions": ["The existing status contract cannot carry the receipt safely"],
  "evidence_refs": ["test:i1-restart"],
  "product_id": "product:…",
  "created_at": "…",
  "route": {"provider": "…", "model": "…"},
  "human_disposition": {
    "contract_version": "human-disposition-v1",
    "state": "unresolved",
    "actor": null,
    "actor_class": null,
    "authority": null,
    "surface": null,
    "rationale": null,
    "recorded_at": null,
    "policy_version": null
  },
  "completeness": {"state": "complete", "missing_fields": [], "degraded_reason": null}
}
```

The existing CLI feedback prompt and `PATCH /tasks/{task_id}` record `accepted`, `edited`, or
`rejected` as an authenticated structured disposition. Until that operation occurs the state is
`unresolved`. The disposition records the authenticated actor, bounded actor class and authority,
surface, timestamp, and supplied rationale or policy version. `edited` still uses the existing
task-output edit semantics; it does not silently rewrite missing decision fields.

## Linked correction

For `observation_type="correction"`, `ace_capture` additionally accepts
`affected_decision_id`, `affected_task_id`, `lifecycle_state`, and one of
`supersedes_correction_id`, `invalidates_correction_id`, or `contests_correction_id`. A successful
write returns a `correction-v1` object with a stable observation-backed correction ID, product,
authenticated actor, source surface, creation time, SHA-256 content hash, confidence, lifecycle,
and typed relationships. Transition links retain the prior correction row and mark it
`superseded`, `invalidated`, or `contested`; they do not delete history.

`ace_load` returns the same linked fields in its `corrections` list, including bounded provenance
and an explicit provenance completeness state. Product ownership is checked for every referenced
task, decision, or correction and cross-product references fail as not found.

## Degraded behavior and privacy boundary

- Legacy or unstructured tasks expose `decision-receipt-v1` with `decision_id: null`, explicit
  missing fields, and `completeness.state: "degraded"`; ACE does not reconstruct facts from prose.
- Legacy corrections with unavailable actor, hash, surface, link, or lifecycle data report those
  fields as absent and provenance as degraded.
- Unknown future receipt/disposition versions are not interpreted as v1. Decision fields remain
  absent with an explicit unsupported-version reason; unknown correction-specific links and
  lifecycle fields remain absent behind a degraded compatibility marker.
- `ace_status` omits the original private task text and returns only a bounded summary of retained
  intelligence rather than unrelated insight content.
- Correction content returned by `ace_load` is bounded and common credential forms are redacted.
  Bearer tokens, API keys, passwords, secrets, model scratchpads, and hidden chain-of-thought are
  outside this contract.
- Stable persistence proves identity continuity only. It does not prove that a decision or
  correction is correct, useful, causal, or beneficial.

This candidate slice does not complete I1, I2, I3, R4, distributed recovery, contributor
disagreement, or materiality lineage. It preserves exactly eleven thin MCP tools and adds no new
execution authority.

## Bounded restart evidence

`tests/test_i1_restart_persistence.py` starts a disposable SurrealKV store and a real uvicorn API
process. Production API startup itself replays migrations from schema zero through v144 before the
test exercises `ace_task`, `ace_status`,
`ace_capture`, and `ace_load` through the standalone thin client. It records CLI-surface accepted
feedback through the existing authenticated task-feedback endpoint, stops the API, starts a fresh
API process and client against the same store, and asserts the same task, decision, correction, and
typed relationship identities. Its deterministic orchestration fixture reports zero tokens and
makes no model call. The same acceptance passed against the documented SurrealDB 3.1.4 deployment
pin and the locally available 3.2.1 runtime. The API startup and standalone installer share one
audited legacy-compatibility policy; v142 and later remain fail-closed on every statement error.

Evidence retained on 2026-07-21:

- focused decision/correction, task-feedback, thin-MCP, capture/load, migration-lint, and migration-
  safety suite: `82 passed`;
- disposable migration/restart acceptance: `1 passed` on each verified runtime; API startup applied
  migrations through v144, v144 was
  reapplied over existing legacy-shaped task/decision/observation rows without changing their
  captured values, and the fresh API/client process returned identical identities and links;
- full reconciled-main, zero-extension non-e2e suite: `6366 passed, 47 skipped, 242 deselected`;
- repository Ruff check and Git whitespace/error check: passed.

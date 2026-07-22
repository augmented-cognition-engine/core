# Decision and correction receipts (I1)

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
  "originating_actor": "user:…",
  "originating_actor_class": "authenticated_user",
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
  "completeness": {"state": "complete", "missing_fields": [], "degraded_reason": null},
  "provenance": {"state": "complete", "missing_fields": []}
}
```

The existing CLI feedback prompt and `PATCH /tasks/{task_id}` record `accepted`, `edited`, or
`rejected` as an authenticated structured disposition. Until that operation occurs the state is
`unresolved`. The disposition records the authenticated actor, bounded actor class and authority,
surface, timestamp, and supplied rationale or policy version. `edited` still uses the existing
task-output edit semantics; it does not silently rewrite missing decision fields.

## Linked correction

For `observation_type="correction"`, `ace_capture` additionally accepts
`affected_decision_id`, `affected_task_id`, `lifecycle_state`, optional `expires_at`, and one of
`supersedes_correction_id`, `invalidates_correction_id`, or `contests_correction_id`. A successful
write returns a `correction-v1` object with a stable observation-backed correction ID, product,
authenticated actor, source surface, creation time, SHA-256 content hash, confidence, lifecycle,
and typed relationships. Transition links retain the prior correction row and mark it
`superseded`, `invalidated`, or `contested`; they do not delete history.

An optional `expires_at` timestamp preserves the stored correction and its stored lifecycle while
the read projection reports `lifecycle_state="expired"` once the timestamp passes. A non-active
stored lifecycle remains authoritative, so expiry never overwrites supersession, invalidation, or
contestation history.

`ace_load` returns the same linked fields in its `corrections` list, including bounded provenance,
`stored_lifecycle_state`, `expires_at`, and an explicit provenance completeness state plus
`missing_fields`. Product ownership is checked for every referenced task, decision, or correction
and cross-product references fail as not found.

## Degraded behavior and privacy boundary

- Legacy or unstructured tasks expose `decision-receipt-v1` with `decision_id: null`, explicit
  missing fields, and `completeness.state: "degraded"`; ACE does not reconstruct facts from prose.
- Legacy corrections with unavailable actor, hash, surface, link, lifecycle, or expiry data report
  those fields as absent and name every missing provenance field instead of reconstructing it.
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

I1 does not claim decision correctness, beneficial outcomes, attributable multi-contributor
deliberation (I2), material retained-intelligence effects (I3), distributed recovery, or execution
authority. It preserves exactly eleven thin MCP tools.

## Bounded restart evidence

`tests/test_i1_restart_persistence.py` starts a disposable SurrealKV store and a real uvicorn API
process. Production API startup replays migrations from schema zero through v145 before the test
exercises `ace_task`, `ace_status`, `ace_capture`, and `ace_load` through the standalone thin
client. The journey records unresolved, accepted, edited, and rejected dispositions plus active,
superseded, contested, invalidated, and expired corrections. It stops the API, starts a fresh API
process and client against the same store, and asserts identical task, decision, correction,
provenance, lifecycle, and typed relationship identities. Its deterministic orchestration fixture
reports zero tokens and makes no model call.

Evidence retained on 2026-07-22:

- focused decision/correction, authorization, isolation, redaction, task-feedback, thin-MCP,
  capture/load, migration-lint, migration-safety, restart, and kernel suite: `94 passed`;
- disposable schema-zero-to-v145 restart acceptance: `1 passed` on the supported SurrealDB 3.1.4
  pin and `1 passed` on 3.2.1, with the complete disposition and lifecycle matrix preserved across
  fresh API/client processes;
- full zero-extension non-e2e suite: `6373 passed, 47 skipped, 242 deselected`;
- exact naked-kernel boundary: `4 passed`;
- repository Ruff check and format check: passed.

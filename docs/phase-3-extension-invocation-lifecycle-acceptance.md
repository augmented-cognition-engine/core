# Phase 3 extension-invocation lifecycle acceptance

Date: 2026-07-23

Decision: **pass**

Exit gate: **Concurrent retry and restart tests pass.**

The durable extension-invocation runtime remains **experimental**. This acceptance closes only
Phase 3 lifecycle behavior. It does not accept or mark Phases 4–7 complete, make the HTTP surface a
supported 0.1.x contract, or change the eleven-tool MCP boundary.

## Accepted responsibility boundary

Core owns:

- durable invocation and attempt persistence;
- product/user/workspace access checks;
- deterministic idempotency, correlation, and retry identity;
- ordered attempt history and predecessor/successor lineage validation;
- task execution, restart reconciliation, and attempt-level recovery;
- retry actor, reason, request time, policy version, and root lineage;
- cooperative cancellation state and public task status;
- bounded public errors and provider/model provenance in receipts; and
- public receipt normalization, history, listing, retry, and cancellation endpoints.

An extension owns:

- domain reference kinds and repository adapters;
- domain-specific preparation and outcome projection/validation;
- authorization inside its own data source;
- immutable artifact production; and
- any later human-decision, approval, adoption, or domain-retention workflow.

An extension may declare cancellation support, but it does not own or mutate Core task lifecycle.
Core stays domain-neutral; no Marketing type or action is present in the lifecycle implementation.

## Accepted lifecycle

```text
create
  → pending
  → running
  → completed | failed | degraded | cancelled

resume(pending | running | completed | cancelled)
  → return the same attempt as an idempotent replay

resume(failed | degraded)
  → create or reuse immutable successor N+1
  → successor.retry_of_task_id = predecessor.id
  → predecessor.resumed_by_task_id = successor.id
  → preserve root_invocation_id, correlation, capability, and envelope hash

runtime loss(pending | running)
  → degraded/interrupted prior attempt
  → never claim mid-token continuation
  → explicit resume may create a fresh linked successor
```

Cancellation is a Core-owned sub-lifecycle:

```text
unsupported
  → unavailable

supported + active local work
  → requested
  → acknowledged + cancelled

task wins the completion race
  → completed_before_cancellation

requested but no local runtime work exists
  → process_stopped_during_cancellation + degraded
```

`requested_at` and `acknowledged_at` preserve both supported-cancellation transition times. A
restart converts a persisted pending cancellation to `process_stopped_during_cancellation`.

## Scenario-to-test evidence matrix

| # | Required scenario | Evidence | Result |
|---|---|---|---|
| 1 | History returns the complete ordered attempt chain | `test_history_query_is_rooted_in_retry_lineage_not_correlation`; `test_history_returns_complete_ordered_chain`; real restart history assertion in `test_same_decision_and_correction_relationship_survive_real_api_restart` | Pass. History is workspace-scoped, ordered by attempt number, no longer truncated at 50, and validates the complete chain before projection. |
| 2 | An interrupted or failed attempt creates attempt 2 | `test_resume_interrupted_invocation_creates_linked_successor`; real restart test | Pass. Attempt 2 records predecessor, root, reason, actor, request time, policy, and a deterministic key. |
| 3 | A failed attempt 2 creates attempt 3 with the original root | `test_retrying_failed_successor_creates_attempt_n_plus_one`; three-attempt history case | Pass. Attempt 3 points to attempt 2 and retains attempt 1 as root. |
| 4 | Concurrent resume requests converge on one deterministic successor | `test_concurrent_resume_calls_converge_on_same_successor`; task idempotency contract tests | Pass in the supported single-process preview host. Both requests use `resume-v1:{task_id}:{N+1}` and resolve to one successor identity. |
| 5 | Pending, running, completed, and cancelled attempts replay idempotently | `test_resume_replays_non_retryable_attempt_states_idempotently`; `test_retry_reuses_receipt_without_duplicate_orchestration` | Pass for all four states; no successor submission occurs. |
| 6 | Malformed lineage fails closed | `test_malformed_lineage_fails_closed_for_resume_and_history`; `test_history_fails_closed_on_incomplete_successor_link`; receipt compatibility tests | Pass with bounded 409 codes; no retry or history projection proceeds. |
| 7 | A missing extension after restart fails closed without altering history | `test_resume_fails_closed_when_extension_is_unavailable_after_restart` | Pass. No successor submission or predecessor update occurs. |
| 8 | Foreign product, user, or workspace access is denied | `test_resume_rejects_foreign_product_before_submission`; `test_resume_rejects_foreign_user_before_submission`; `test_resume_and_history_reject_foreign_workspace`; workspace-filtered history query | Pass with not-found behavior before submission/history access. |
| 9 | Unsupported cancellation is recorded as unavailable | `test_unsupported_cancellation_is_recorded_without_executing` | Pass. Core persists `unavailable`, returns a generic 409 code, and does not cancel work. |
| 10 | Supported cancellation records requested and acknowledged states | `test_supported_cancellation_persists_requested_then_acknowledged`; `test_supported_cancellation_delegates_to_core_lifecycle` | Pass. The durable transition sequence and both timestamps are present. |
| 11 | A task completed before cancellation is represented distinctly | `test_cancellation_records_completed_before_request`; `test_cancellation_rechecks_terminal_state_before_reporting_stopped_process` | Pass as `completed_before_cancellation`, preserving completed task status. |
| 12 | Missing runtime work during cancellation becomes process-stopped-during-cancellation | `test_cancellation_records_process_stopped_when_runtime_job_is_absent`; restart reconciliation contract assertion | Pass with a durable degraded state and bounded public error. |
| 13 | A real two-process SurrealKV restart preserves the prior attempt and allows a linked successor | `test_same_decision_and_correction_relationship_survive_real_api_restart` | Pass. Two API processes share a real SurrealKV store; public history returns attempts 1 and 2 after restart. |
| 14 | Every attempt retains provider/model provenance and bounded public errors where available | `test_receipt_preserves_attempt_lineage_and_provenance`; `test_failed_and_degraded_states_are_explicit_and_errors_are_bounded`; real restart provider assertion | Pass. Missing provenance stays explicit degradation rather than being fabricated. |
| 15 | The naked kernel remains free of domain actions and passes boundary tests | `tests/test_kernel_boundary.py`; Canvas no-extension leakage tests; full `ACE_DISABLE_EXTENSIONS=1` lane | Pass. No Marketing concepts were added to Core. |

## Defects corrected during acceptance

1. History previously returned the requested task as a fallback when lineage was malformed or the
   chain query returned no rows. It now fails closed.
2. History previously limited the query to 50 rows despite promising the complete attempt chain.
   The arbitrary chain truncation was removed.
3. History previously validated only the requested attempt. It now validates every attempt,
   contiguous numbering, root identity, predecessor and successor links, correlation, envelope
   hash, capability identity, and terminal completeness of the returned chain.
4. An empty or non-string `resumed_by_task_id` was previously accepted by the local lineage
   validator. It now fails validation.
5. Acceptance coverage now explicitly exercises attempt 3, all idempotent replay states, malformed
   and incomplete chains, workspace denial, supported cancellation transitions, and public history
   after a real restart.

No Marketing implementation change was required. The public v1 request and receipt shapes were not
changed.

## Exact verification record

Commands were run from `/Users/eamirian/Projects/ace-core` unless noted.

| Command | Result |
|---|---|
| `uv run pytest tests/extensions/test_task_actions.py tests/test_extension_invocations_api.py tests/test_task_public_contract.py tests/test_kernel_boundary.py tests/test_schema_migration_lint.py tests/test_schema_migration_errors.py tests/test_migration_safety.py -q --tb=short` | **86 passed** |
| `uv run pytest tests/extensions tests/test_extension_invocations_api.py tests/test_extension_registry.py tests/test_kernel_boundary.py tests/test_mcp_specs.py tests/test_mcp_tools.py tests/voice/test_proactive_line_extension.py -q --tb=short` | **105 passed** |
| `uv run pytest tests/test_i1_restart_persistence.py -q --tb=short` | **1 passed in 25.65s** |
| `uv run pytest -m 'not e2e' -q --tb=short` | **6,644 passed, 46 skipped, 235 deselected** |
| `ACE_DISABLE_EXTENSIONS=1 uv run pytest -m 'not e2e and not requires_extensions' -q --tb=short` | **6,636 passed, 47 skipped, 242 deselected** |
| `PYTHONPATH=/Users/eamirian/Projects/ace-ext-b2b-marketing /Users/eamirian/Projects/ace-core/.venv/bin/pytest /Users/eamirian/Projects/ace-ext-b2b-marketing/ace_ext_b2b_marketing/tests -m 'not e2e' -q --tb=short -p no:cacheprovider` | **355 passed, 4 skipped, 4 deselected** |
| Isolated Marketing `extension-invocation.test.ts` run using Core's installed Vitest runtime | **3 passed** |
| `(cd core/ui/canvas && npm test)` | **290 passed** |
| `(cd core/ui/canvas && npm run build:naked)` | **9 boundary tests passed; TypeScript and production build passed** |
| `(cd core/ui/canvas && npm run build)` | **TypeScript and production build passed** |
| `uv run ruff check .` | **passed** |
| `uv run ruff format --check .` | **passed; 1,819 files already formatted** |
| `/Users/eamirian/Projects/ace-core/.venv/bin/ruff check --no-cache /Users/eamirian/Projects/ace-ext-b2b-marketing/ace_ext_b2b_marketing` | **passed** |
| `git diff --check` in each repository | **passed in both repositories** |

The Marketing UI is not currently wired into the Core Vitest include roots in these worktrees. A
direct cross-repository test path therefore reports no collected files; the three adapter tests
were copied to a temporary fixture and run unchanged against Core's installed Vitest runtime.
No repository file was created or modified for that run.

A supplementary Marketing-wide `ruff format --check --no-cache` was not a configured acceptance
gate and exited 1 because 104 pre-existing files would be reformatted. No bulk formatting was
applied; Marketing Ruff lint is green.

## Verified limitations and risks

- Recovery is attempt-based. It does not continue a lost provider stream mid-token.
- The supported preview host is single-process. The concurrency result does not claim distributed
  recovery, portable task claiming, or exactly-once provider execution.
- Provider work may have happened before a runtime failure. Retry can repeat provider calls or
  external side effects; Core does not reverse those effects.
- Cancellation is process-local and cooperative. It does not guarantee provider-side cancellation,
  external-side-effect reversal, or resource reclamation.
- Extension code is trusted in-process code. Core isolation checks do not make an unsafe extension
  repository adapter safe.
- A complete receipt proves lifecycle and contract coverage, not semantic correctness, benefit,
  approval, or adoption.
- No live-provider or metered call was made for this acceptance.
- The runtime and HTTP surface remain experimental. Phases 4–7 remain unaccepted.

# Scanner hardening — code-review dispositions v1

- Date: 2026-08-17
- Reviewed change: `codex/ace-1.1.x-scanner-hardening` (PR #207), a 1.1.x fix for the three PI12
  smoke findings (worktree admission, graph→product binding, malformed node IDs).
- Reviewers: four independent finder passes over `git diff origin/main...HEAD`.

## Fixed in this PR (defects in the change, or its docstring's implied contract)

1. **Cross-product graph hijack.** The first-cut binding wrote
   `UPDATE graph SET product = <principal> WHERE graph_id = $gid` unconditionally, letting a
   principal rebind — and merge nodes into — another product's graph. Replaced with admission-side
   authorization: the scan route requires the principal's product (403 if absent), refuses a scan
   targeting a graph bound to a different product (non-confirming 404), and binds **only if
   unbound** so a scan can never steal an existing binding.
2. **`.git` admission event-loop hang.** `os.path.exists` admitted any entry named `.git`,
   including a FIFO, which `Repo()` (synchronous, on the event loop) opens and blocks on forever.
   Admission now accepts `.git` only as a directory or a regular file beginning with `gitdir:`,
   restoring a synchronous 400 for everything else.
3. **Misleading 422 field attribution.** The shortcut request builder blamed `node_id` for any
   validation failure; `get_history`/`get_related` now pre-admit `graph_id` like `get_impact`, and
   the refusal names the field that actually failed.
4. **`validate_start` record-ID regex.** `[\w./-]+` admitted characters no real node ID contains
   (all IDs are `_slug()` output, `[a-z0-9_]`). Beyond the 500 on a bad ID, `graph_file:x--`
   interpolated into `SELECT * FROM {start} WHERE graph_id = $graph_id` turned the isolation fence
   into a SurrealQL line comment. Narrowed to `[\w]+`, which admits every real ID and closes both.
5. **Test validity.** The worktree-admission test's `scan_repo` mock expired before the background
   task ran, so it exercised the real scanner. The patch now covers the task's execution and the
   test asserts the mock was used.

## Deferred — real, but out of scope for this narrowly scoped fix

- **Binding altitude (MCP and external scan paths).** `core/engine/mcp/tools.py` (`ace_scan_repo`,
  fire-and-forget, `graph_id="default"`) and `core/engine/scanner/external.py` (competitor graphs)
  do not bind the `graph` record's product, so graphs they create are unreadable through the
  traversal gate. The clean fix is to bind inside `scan_repo`'s own graph UPSERT, but MCP has no
  principal/product in scope, so threading product through that layer is a subsystem change, not a
  patch. This is a **pre-existing** gap this PR did not regress. → own 1.1.x issue.
- **`delete_graph` and `scan_status` lack product scoping.** `DELETE /scanner/scan/{graph_id}`
  destroys any product's graph, and `scan_status` enumerates any graph's existence and metadata —
  both undermining the non-confirming-404 isolation the traversal path enforces. Pre-existing, and
  a distinct defect class (unauthorized delete/enumerate). → **Fixed** on
  `codex/ace-1.1.x-graph-authorization` (stacked on this branch): both endpoints now require the
  principal's product and refuse a missing, unbound, or foreign graph with a non-confirming 404
  via a shared `_load_owned_graph` helper, before returning metadata or deleting anything.
  Residual, noted: `scan_status`'s in-memory running-scan path still returns a metadata-free
  `running`/`failed` status to any caller who guesses the exact ephemeral graph_id, because a
  durable ownership record does not exist until the scan binds the graph on completion. Low
  severity (no counts, paths, or content); a future owner-tracking map would close it.
- **`init_project.py` conditioned rebind can miss.** Its `WHERE graph_id='default' AND repo_path=…`
  can match zero rows after a different checkout is scanned into `default`, failing silently at
  debug level. Related to the deferred altitude work; folded into that issue.

# ACE 1.2 PI12 — Code Intelligence dogfood smoke v1

- Date: 2026-08-17
- Purpose: first PI12 evidence step for the [1.2 work packet](../design/personal-intelligence-v1.2-work-packet-v1.md) —
  demonstrate that the shipped 1.1 Code Intelligence foundations operate against the ACE repository
  itself, before the matched `ACE Builds ACE` program runs.
- Scope: bounded smoke. This is not the PI12 matched comparison, not a release gate, and it makes
  no benefit claim. It exercises scan → persisted graph → restart → authorized traversal.
- Subject: clean clone of `codex/ace-1.2-personal-intelligence-packet` (baseline `eab2aa2` + freeze
  docs), commit `88c7466`, with a real `.git` directory.
- Environment: macOS arm64, Python 3.12.13, SurrealDB 3.2.1 (disposable rocksdb store, port 8901,
  isolated from any production instance), ACE source at 1.1.0 baseline, API on port 3210,
  no live model provider (none required for this path).

## Steps and results

1. **Pure contract substrate** — `uv run pytest tests/intelligence -q`:
   **746 passed, 2 skipped** (pack compiler, detection, routing, synthesis, epistemic status,
   source mapping, ledger, activation, governed reasoning).
2. **Schema** — `scripts/schema_apply.py` against the empty disposable instance:
   **178 files applied; schema v179 validated** (110 audited legacy compatibility events).
3. **Readiness** — `ace doctor`: API PASS, authentication PASS, **MCP 11/11 public tools
   registered**; overall "not operationally ready" only for the absent model provider, which this
   journey does not use.
4. **Scan** — `POST /scanner/scan` on the clean clone: completed in ~33s —
   **3,212 files, 27,904 functions, 13,651 imports** (`graph_id=smoke_ace_core`).
5. **Restart continuity** — the API process died after scan completion (exit 137, cause not
   established; suspected memory pressure). After restart, `GET /scanner/scan/…/status` returned
   `completed, node_count=31117, edge_count=13651` from SurrealDB — the graph survived the death
   of the process that built it.
6. **Authorized traversal** — with the graph bound to `product:platform` (see finding B):
   - `GET /graph/impact/graph_file:core_engine_core_config_py` returned the real inbound
     dependents of `config.py` (`onboarding/scaffolder.py`, `scripts/schema_apply.py`,
     delegated-activation tests, …);
   - `GET /graph/related/graph_file:core_engine_api_scanner_py` returned its true import
     neighborhood (`core/engine/core/db.py`, `core/engine/core/tasks.py`, …);
   - `GET /graph/history/graph_file:core_engine_scanner_scanner_py` returned the node with an
     **honestly empty** co-change set — the shallow clone has one commit, and the system reported
     that truthfully rather than fabricating history.

## Findings (each needs a disposition)

- **A — Scanner rejects git worktrees.** `core/engine/api/scanner.py` requires `.git` to be a
  directory; in a linked worktree `.git` is a file, so scanning the worktree returned
  `400 "Not a git repository"`. Reproduced live. Coding agents (including the `ACE Builds ACE`
  program itself) work in worktrees, so this is a candidate narrowly scoped 1.1.x fix.
- **B — Raw scans produce product-unbound, unreadable graphs.** `/scanner/scan` writes the `graph`
  record with no `product` link, and the product/graph isolation gate in
  `core/engine/api/graph_traverse.py` correctly refuses unbound graphs with a non-confirming 404.
  The only code that writes the binding (`core/engine/runtime/init_project.py:89`) has **no
  callers anywhere on `origin/main`** — unreachable dead code. For this smoke the binding was
  applied manually with the identical statement that dead path would have run
  (`UPDATE graph SET product = product:platform WHERE graph_id = …`), disclosed here as a
  diagnosis-mode step, after which authorization passed and traversal worked. Disposition needed:
  either the scan path binds the graph under the authenticated principal, or the raw-scan journey
  is documented as requiring the extension-owned path. The dead `init_project.py` is itself a
  textbook disconnected-function finding of the kind Code Intelligence exists to detect.
- **C — Malformed node IDs return 500.** URL-encoded path-style node IDs
  (`/graph/impact/core%2F…%2Fconfig.py`) produced `500 Internal Server Error (ValidationError)`
  rather than a 4xx refusal. Robustness candidate for 1.1.x.
- **D — API process exit 137 after scan.** Observed once, cause not established; scan data was
  already durable and restart recovered cleanly. Recorded as an observation, not a defect claim.

## Limitations

- One machine, one run, no matched baseline, no concurrent participants, no stale-context event —
  the full PI12 program remains open.
- The manual product binding in finding B means step 6 exercised the authorized read path but not
  a fully supported end-to-end public journey for raw scans.
- History/co-change intelligence was structurally exercised but empty by construction (depth-1
  clone).

# PI12 subject registration — PI8 (first preregistered subject)

- Registered: 2026-08-18
- Operator: this session (claude-fable-5 as program operator; does not author subject code)
- Harness: ace-builds-ace-harness-v1, frozen config digest
  `5ec835f197ebfb8c9e81e72b506ff119b1e77e0ab795139fd39b7ab5c8a18130` (commit a48eb8a)
- Runner: reviewed at commit `ce84027` (pinned; run from branch codex/pi12-arm-runner)
- Authorization: Edwin's direct confirmation given in the operator session ("yes, launch PI8").

## Subject

- Subject id: **PI8** — ACE 1.2 Personal Intelligence "Grounded Ask and correction" (J7/J8).
- Frozen repository head: **`3899ae741909a0da7675767e77a924fcfeea6c18`** (origin/main tip at
  registration). All three arms build against this exact head in isolated worktrees.
- Frozen subject prompt: `pi8-subject-prompt.md` (identical for every arm — fairness).
- Answer key / acceptance criteria: frozen in the subject prompt's "Acceptance criteria" section.

## Arms (order B → A → C)

| Arm | Model | ACE | Disposition |
|---|---|---|---|
| B | claude-sonnet-5 | none | floor control; evidence only, never merges |
| A | claude-fable-5 | none | reference ceiling; evidence only, never merges |
| C | claude-sonnet-5 | shipped 1.1 Code Intelligence MCP | production candidate; only arm that merges, after ordinary review |

- Env for every arm: CC 2.1.224 (verified), no-web allowlist (Read/Write/Edit/Bash/Glob/Grep/
  TodoWrite), `--strict-mcp-config`, 8h wall-clock, max 1 rerun. Model access verified headless for
  both claude-sonnet-5 and claude-fable-5.
- Arm C precondition (operator): a live authenticated Core 1.1.x ACE backend with the code-
  intelligence MCP; runner preflight aborts (exit 4) unless `ACE_HEALTH_URL` reports and matches
  `1\.1\.`; zero ACE MCP calls flagged degraded post-run. **Backend + provider still to be stood up
  before arm C — pending the provider decision.**

## Verdicts to compute

- Within-tier **C vs B** (does ACE lift Sonnet above bare Sonnet?).
- Tier-jump **C vs A** (does Sonnet+ACE match/exceed bare Fable?).
- Token figures compared within tier only (Sonnet vs Fable tokenizers differ).

## Run log

(arm run metadata + result paths appended below as each completes; capture records emitted in-band;
retrospective PI2–PI7 records appended to docs/evidence/ace-builds-ace-v1.md after PR #234 merges.)

### 2026-08-18 operator preflight notes (before first subject run)

- CLI had auto-updated 2.1.224 → 2.1.234 at 08:33 local (post-handoff drift). Edwin manually
  repinned via `claude install 2.1.224` at ~16:24 UTC; version verified before each launch.
  Preregistered environment restored — no drift in any counted run.
- Runner bug found in review: `run-arm.sh:82` reads the prompt via `"$OLDPWD/$PROMPT_FILE"` with an
  already-absolute `PROMPT_FILE` (doubled path, ENOENT). Workaround without modifying the pinned
  script: byte-identical mirror of `pi8-subject-prompt.md` placed at the doubled path under the
  repo root (`cmp`-verified). Subject reads identical bytes.
- Runner dependency gap: GNU `timeout` absent on this macOS host (no coreutils). Provided a
  stdin-inheriting python3 shim (GNU-compatible exits: 124 cap / 127 missing cmd / passthrough)
  prepended to PATH for runner invocations only. Shim tested before use.
- VOID launch (not a subject run, counts toward no rerun budget): `aba-PI8-armB-20260818T162429Z`
  exited 127 at `timeout` lookup before `claude` started — zero tokens, no session, worktree clean
  and removed. Records archived in `runs/`.

### Arm launches

- **Arm B** `aba-PI8-armB-20260818T162829Z` — claude-sonnet-5, started 2026-08-18T16:28:30Z,
  cc 2.1.224, frozen head `3899ae7`, worktree `.../aba-PI8-armB-20260818T162829Z-S3w6`.
  **COMPLETED** 17:07:36Z: exit 0, terminal_reason=completed, 187 turns, 39.0 min, $19.66,
  session `001506bc-5d72-4cf5-9844-c4766f139f32`, out 153,307 tok (cache_read 50.1M,
  cache_create 388k). 18 files changed (7 modified, 11 new incl. 6 test files). Note: subject's
  final message shows it ended waiting on a background-task notification — final summary not
  delivered; operator review establishes test/lint ground truth. Ran through the 16:20Z
  provider incident without erroring.
  **Review (armB-review agent, first review): 6/6 acceptance criteria PASS; overall
  COMPLETE-WITH-DEFECTS.** Operator-verified gates: 72/72 focused tests pass, ruff clean, MCP
  surface unchanged (HTTP router entry). One minor finding: default LexicalGroundedAskAnswerer is
  a self-validated keyword-overlap heuristic (documented as swappable placeholder) — claim
  relevance unverified beyond term overlap. No fail-open defects, no mutation, no scope creep.
  Capture record: `runs/aba-PI8-armB-20260818T162829Z-capture.json` (§8 shape, digest cited).
- VOID launch (not a subject run, counts toward no rerun budget):
  `aba-PI8-armA-20260818T162907Z` terminated at 16:31:00Z by API 500 (`terminal_reason=api_error`,
  0 input/output tokens, num_turns=1, worktree clean → removed; arm B unaffected and running,
  so not systemic). Records archived in `runs/`. Ruled void: server-side failure before any
  subject work — no outcome existed to select on. Operator judgment, flagged for Edwin's review.
- VOID launch #2 for arm A: `aba-PI8-armA-20260818T163245Z` (started 16:32:45Z) terminated
  16:45:07Z by API "server error mid-response" (`terminal_reason=api_error`) after 42 turns /
  12.3 min / $7.42 — subject was still in exploration: worktree had ZERO changes, no selectable
  outcome. Root cause exogenous and documented: status.claude.com shows an active incident from
  16:20 UTC 2026-08-18, "elevated errors" explicitly including claude-fable-5. Ruled void
  (incident-terminated before any subject work product); flagged for Edwin's review. Worktree
  left in place; records in repo root.
- **Arm A** `aba-PI8-armA-20260818T171602Z` — claude-fable-5, started 2026-08-18T17:16:02Z,
  cc 2.1.224 (verified at launch), frozen head `3899ae7`, worktree
  `.../aba-PI8-armA-20260818T171602Z-zxhv`. This is arm A's COUNTED run. Launched at
  Edwin's direction ("try A again please") while the status-page incident was still open
  (indicator: minor) — owner-directed timing, recorded for §7 transparency.
  **COMPLETED** 17:41:03Z: exit 0, terminal_reason=completed, 103 turns, 25.0 min, $22.85,
  session `7025fded-1861-487f-801a-793b01db973f`, out 117,193 tok (cache_read 12.1M,
  cache_create 243k). Change committed locally: branch `pi8-grounded-ask-correction`, commit
  `688b5ab`, 10 files, +2,909 lines. Full final summary delivered.
  Operator gates: subject's 3 new test files 20/20 pass; ruff clean; BUT
  `tests/test_public_core_boundaries.py` FAILS (2 tests) — new `core/engine/core/grounded_ask.py`
  imports `ace.intelligence.contracts.resource_plane` without being added to the legacy-host
  allowlists; subject never ran/updated the existing boundary gates (arm B did). First-review
  defect recorded.
  **Review (same reviewer as arm B, first review): 4/6 PASS, 2/6 PARTIAL (criteria 1, 4);
  overall COMPLETE-WITH-DEFECTS.** Major findings: (1) architectural regression — Core host file
  imports ace.intelligence.contracts directly, failing the unconditional pre-existing boundary
  gate (allowlist-free; only fix is removing the import); (2) reuse violation — correction path
  reimplements the proposal-only feedback machinery in parallel (only the intent enum reused),
  contra the answer key and unlike arm B. Minor: default composer answers only over Brief-shaped
  payloads (narrower than the key's scope), undisclosed in summary. Unsupported claims: 1
  (commit message's "reusing the feedback machinery"). Verified true: double-layer grounding,
  digest-bound corrections, MCP surface unchanged. Process note: subject committed locally
  (`pi8-grounded-ask-correction` @ 688b5ab) — no scoring impact.
  Capture record: `runs/aba-PI8-armA-20260818T171602Z-capture.json` (§8 shape, digest cited).
  **First-review quality comparison (per §6, quality measures only): arm B > arm A** — 6/6 vs
  4/6 criteria, 1 minor vs 2 major findings. Token/latency never compared across tiers.
- **Arm C backend (stood up 2026-08-18 ~18:00–19:00Z; provider decision delegated by Edwin
  "what decision? just do it" → operator chose `claude-cli`):**
  - `ace-core==1.1.0` from public PyPI in an isolated venv (CPython 3.12.13); config isolated via
    `ACE_CONFIG_DIR` in session scratchpad — owner's `~/.ace` and dev instance (ports 3000/8001)
    untouched. Disposable SurrealDB (rocksdb) on 127.0.0.1:8902; schema v179 applied from the
    installed wheel; API on 127.0.0.1:3210 under an auto-restart supervisor (disclosed: the API
    process reproducibly dies right after scan completion — smoke finding D; any mid-run restarts
    will be counted from the supervisor log).
  - DEPENDENCY FIX (disclosed): fresh PyPI resolve gave tree-sitter 0.26.0 which SEGFAULTs the
    scanner (crash report: node_get_start_point in _binding.so); pinned to uv.lock's known-good
    tree-sitter==0.25.2 + tree-sitter-language-pack==1.4.1. Candidate 1.1.x packaging finding.
  - `ace login` OK; `ace doctor`: api/auth PASS, MCP 11/11; `ace doctor --live-provider`:
    model_provider PASS (one live diagnostic call through Claude CLI).
  - Repo scanned at frozen head from the main checkout (worktrees rejected by scanner — smoke
    finding A): graph_id **`default`** (MCP tools' default), 3,265 files / 28,158 functions /
    13,686 imports / 31,424 nodes. Graph manually bound to product:platform (smoke finding B
    workaround, disclosed). Traversal verified end-to-end through the real `ace_mcp_client`
    ace_impact path. A first scan under graph_id `pi8_ace_core` also exists (superseded; subject
    tools default to `default`).
  - Operator run artifacts moved out of the repo root before the counted scan.
  - MCP config: `ace-mcp-config.json` (stdio `ace-mcp-client`, env ACE_URL + ACE_CONFIG_DIR).
  - `ACE_HEALTH_URL=http://127.0.0.1:3210/health` reports `"version": "1.1.0"` (runner regex
    `1\.1\.` satisfied). CLI verified 2.1.224 at launch.
- **Arm C run 1** `aba-PI8-armC-20260818T185240Z` — started 18:52:40Z, COMPLETED 19:33:29Z
  (exit 0, 182 turns, 40.8 min, $21.45, session `aebc1294-0629-4b1f-9c59-c8b8af7c4eb7`, out
  211,116 tok). **RULED DEGRADED/INVALID (§7): zero actual ACE MCP tool calls.** Three
  independent confirmations: transcript parse shows 0 mcp tool_use blocks; ACE API log shows 0
  non-scanner requests in the run window; operator monitor observed subject exit before any API
  traffic. Tools were registered and error-free (availability attachment lists all 11; no MCP
  errors) — the subject chose not to engage ACE and completed the slice bare. Not quietly kept.
  Worktree preserved (`.../armC-20260818T185240Z-uFC1`, 8 local commits) as evidence of the
  adoption-failure mode; it is NOT the C measurement.
  **INSTRUMENT FINDING:** runner's `ace_mcp_calls` post-run check counts transcript LINES
  containing `"mcp__` — the tools-available attachment matches, so it reported 1 and missed the
  degradation. Ground truth requires parsing tool_use blocks. Candidate runner fix before PI9.
- **Arm C rerun (1 of 1, sanctioned)** `aba-PI8-armC-20260818T193907Z` — started 19:39:07Z,
  COMPLETED 20:07:58Z (exit 0, 143 turns, 28.8 min, $16.23, session
  `6fce6fd9-3c63-494d-aebe-e6b2a7655a02`, out 157,999 tok). **ZERO ACE MCP calls again**
  (transcript parse 0; ACE API log 0 non-scanner requests; monitor confirmed exit with no
  traffic). **RULED DEGRADED/INVALID as the C measurement. No further reruns.**
  **PI8 arm C program finding (preregistered): AVAILABILITY WITHOUT ADOPTION, twice under
  identical clean conditions** — all 11 tools registered and error-free, 31,424-node graph
  verified reachable via the subject's own client, and a bare-Sonnet agent never elected to call
  ACE. Notable: in both C runs the subject READ ace_mcp_client source as implementation subject
  matter while ignoring the same tools in its own inventory.
  Work product (bare-Sonnet provenance): commit `abf4950`, 17 files, +4,915 lines. Operator
  gates: its 52/52 new tests pass, ruff clean, unconditional core→ace.intelligence gate PASSES;
  one allowlist gate fails (new core hosts use the sanctioned ace.application pattern but are
  not registered in the gate's allowlist — two-line test edit).
  **Review (same reviewer, first review): 6/6 PASS as bare-Sonnet work product; overall
  COMPLETE-WITH-DEFECTS.** Only real defect mechanical (allowlist registration); minor: note-string
  claim binding (verified injection-safe), Brief-only Ask scope + no durable Ask-event record
  (both disclosed), 2,638-line plan doc to trim. Zero unsupported claims.
  **Reviewer three-way shipping ranking: C-rerun > B > A** — C-rerun is the only arm touching
  zero pre-existing contract/service files and fully delegating authz + feedback to existing
  unmodified services. Recommendation: ship C-rerun as ordinary 1.2 delivery (with allowlist
  fix); consider arm B's raw-Observation grounding later as a strict-superset widening.
  Capture record: `runs/aba-PI8-armC-20260818T193907Z-capture.json`.
  Merge disposition is Edwin's call (valid C measurement does not exist; handoff rule 8 path).
- **Delivery (Edwin: "ship C-rerun", 2026-08-18):** operator applied review fixes on top of
  `abf4950` as commit `512a192` — (1) registered both new Core hosts in the boundary-test
  allowlist; (2) rerouted the API route's two `ace.application` contract imports through the
  Core host (third boundary assertion caught this at line 166 — API modules reach `ace` only
  via hosts); (3) removed the 2,638-line plan doc from the change (preserved as
  `runs/aba-PI8-armC-20260818T193907Z-plan-doc.md`). Full boundary suite + all PI8 tests green,
  ruff clean. Two `test_contract_boundaries.py` failures confirmed PRE-EXISTING at the frozen
  head (local_source modules, PI4/PI7) — reproduced on clean base; separate fix needed.
  Branch **`pi8-grounded-ask-c`** pushed to origin. **PR #236 opened by Edwin**
  (https://github.com/augmented-cognition-engine/core/pull/236) — ordinary review → merge from
  here. PI8 subject registration closes when #236 merges and the capture records append to
  docs/evidence/ace-builds-ace-v1.md (after PR #234).

## PI8 verdicts (computed per harness §6)

- **C vs B (within-tier):** NO VALID ARM C MEASUREMENT — both C runs degraded (zero ACE
  adoption). The preregistered comparative claim for PI8 is therefore VACANT, and the recorded
  program result for arm C is the adoption failure itself, which per §6 ships as a valid
  (negative-class) outcome.
- **C vs A (tier-jump):** same — no valid C measurement; not computed.
- **B vs A (descriptive, non-preregistered observation):** bare Sonnet outscored bare Fable at
  first review on the frozen answer key — 6/6 PASS / 1 minor finding (B) vs 4/6 PASS +
  2 PARTIAL / 2 major findings (A). Tokens/latency not compared across tiers.
- Program-level: PI8 contributes one intelligence-curve point whose content is
  "provisioned-but-unadopted"; `prior_slice_provenance` empty; proposal kind `context` (adoption
  fix) recorded in the arm C capture records for PI9/PI10 measurement.

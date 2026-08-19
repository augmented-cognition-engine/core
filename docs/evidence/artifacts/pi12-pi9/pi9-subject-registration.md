# PI12 subject registration — PI9 (second preregistered subject)

- Registered: 2026-08-18
- Operator: this session (claude-fable-5 as program operator; does not author subject code)
- Harness: ace-builds-ace-harness-v1, frozen config digest
  `5ec835f197ebfb8c9e81e72b506ff119b1e77e0ab795139fd39b7ab5c8a18130` (commit a48eb8a)
- Runner: `codex/pi12-arm-runner` @ **`e88ae86`** (PI8's three instrument defects repaired:
  portable timeout, prompt-path, tool_use-parsing ace_mcp_calls). Extracted copy sha256 prefix
  `0cebd5f6b18a231b25b9b2bb` at `run-arm-e88ae86.sh`.
- Authorization: Edwin's direct instruction in the operator session ("run PI9").

## Subject

- Subject id: **PI9** — ACE 1.2 Personal Intelligence "ownership depth" (J9/J10): export and
  deletion truthfully covering derived artifacts; restart continuity; write-quiescence during
  confirmed deletion documented or implemented. Core layer. (Work packet §6.)
- Frozen repository head: **`45b48b80789214c4f5de9f443fa0bb208171d890`** (origin/main tip at
  registration). **This head includes PR #237 — the task-shaped thin-client MCP surface — making
  PI9 the preregistered before/after test of the PI8 adoption finding.**
- Frozen subject prompt: `pi9-subject-prompt.md` (identical for every arm; answer key derived
  verbatim from work-packet §2 J9/J10, §4 decision 9, §6 PI9 row, §7 scope exclusions).

## Arms (order B → A → C)

Same as PI8: B bare claude-sonnet-5 (floor, evidence-only); A bare claude-fable-5 (ceiling,
evidence-only); C claude-sonnet-5 + shipped 1.1 ACE MCP (production candidate, merges after
ordinary review). Env: CC 2.1.224 (verified at registration; verified again at each launch),
frozen no-web allowlist, `--strict-mcp-config`, 8h cap, max 1 rerun per arm.

- Arm C backend: fresh disposable stand-up at the frozen head per the PI8 recipe (ace-core==1.1.0
  venv with tree-sitter pinned 0.25.2/1.4.1, fresh SurrealDB rocksdb store, schema v179, API
  under restart supervisor, scan main checkout at frozen head into graph_id `default`, manual
  product binding per smoke finding B, doctor + live-provider PASS, traversal verified through
  ace_mcp_client before launch).
- Primary PI9-specific observable: **ACE adoption** — count of actual mcp__ tool_use calls
  (repaired counter), time-to-first-call, and which tools. PI8 recorded 0 calls twice on the
  pre-#237 surface; any adoption here is the before/after point.

## Verdicts to compute

Same as PI8 (§6): within-tier C vs B; tier-jump C vs A; tokens within tier only. Plus the
adoption before/after against PI8's zero.

## Run log

- **Arm B** `aba-PI9-armB-20260818T213359Z` — claude-sonnet-5, 21:34:00Z → 22:13:01Z,
  COMPLETED exit 0: 185 turns, 33.4 min, $23.55, out 147,172 tok, session
  `0dd296ce-9870-4715-9247-c90fd2515446`. 7 commits, 15 files, +2,355/−1, clean tree.
  Operator gates: 50 tests pass (5 new test files + contract boundaries), ruff clean; ONE
  boundary-allowlist failure — new `core/engine/core/personal_intelligence_derived_artifacts.py`
  not registered in the host-adapter allowlist (same registry-omission class as PI8 arms A/C).
  **Review: 7/7 PASS, COMPLETE-WITH-DEFECTS.** Sole real defect = the registry omission
  (mechanical; import discipline verified correct). Reviewer highlights: the strongest test seen
  across PI8+PI9 — a genuine e2e restart-continuity test that kills and respawns a real SurrealDB
  process against the same on-disk store and asserts byte-identical reopen of sources, Briefs,
  corrections, and ownership receipts; disclosures bound into contract content-hash identity
  (tamper-evident); write-quiescence correctly shipped as a typed, pinned documented limitation;
  the most conservatively-worded evidence packet of any arm (zero unsupported claims); reviewer
  independently verified the "no derived-artifact stores" architectural claim. Minor: AM4/Agent
  Memory adjacency not cross-referenced in the disclosure prose (verified out of scope anyway).
- **Arm A** `aba-PI9-armA-20260818T213417Z` — claude-fable-5, 21:34:18Z → 22:15:04Z,
  COMPLETED exit 0: 104 turns, 36.2 min, $33.18, out 120,914 tok, session
  `68896c74-68de-438a-bbcc-e6a8eaee47a3`. 1 commit (4187017), 14 files, +1,537/−9, clean tree.
  Operator gates: ALL GREEN — its 4 test files pass, full `test_public_core_boundaries.py`
  10/10, `test_contract_boundaries.py` passes, ruff clean. (Reversal vs PI8, where arm A broke
  the unconditional boundary gate.)
  **Review: 7/7 PASS, overall COMPLETE — first unqualified COMPLETE in the program.** All 9
  deleted lines verified as refactor noise (no compat regression). Highlights: real product-fenced
  QUERY-based enumeration of the four derived-artifact classes plus ACTIVE erasure with
  post-erasure verification; fails closed with no port attached; stale-preview check extended to
  derived-artifact drift; per-class export checksums + named control-plane exclusions; wire-level
  backward compat via the repo's own exclude_if pattern; avoided the allowlist trap by
  construction (no new host file). Weakness vs arm B: restart-continuity evidence is an honest
  in-memory JSON round-trip, categorically weaker than arm B's real DB kill/respawn e2e.
  **MATERIAL COMPARATIVE FINDING (reviewer): arm B's production port hardcodes covered=True,
  count=0 for the four artifact classes WITHOUT querying — factually false if a product ever
  shares Personal + Code Intelligence footprints. Arm A queries product-fenced counts and
  discloses them as surviving, and additionally discloses the qdrant vector copy arm B never
  mentioned. Weigh in any ordinary-delivery design choice.**
- **Arm C** `aba-PI9-armC-20260818T221001Z` — claude-sonnet-5 + ACE MCP (task-shaped surface
  from #237 on the frozen head), started 22:10:10Z. RUNNING. Backend: fresh store at frozen
  head, graph `default` 3,295 files / 28,225 fn / 13,912 imports / 259 decisions / 451
  co-change edges, product-bound, traversal client-verified pre-launch. Adoption monitor armed
  on the ACE API log (PI8 baseline: zero calls in both runs).
  **COMPLETED 22:39:39Z — RULED DEGRADED/INVALID (§7): ace_mcp_calls=0 (repaired tool_use
  counter) + zero ACE API traffic + monitor confirmation.** 77 turns, 29.4 min, $7.25, out
  61,936 tok, session `60d2a111-9c83-42ea-a896-ba9378e2f42a`. Notably lighter run than the bare
  arms (dirty worktree, uncommitted, claims all criteria met — reviewer scores as bare work
  product). **PI9 adoption before/after: the task-shaped surface (#237) did NOT move adoption:
  0 calls on the old surface (PI8 ×2), 0 calls on the new surface (PI9 run 1).**
- **Arm C rerun (1 of 1, sanctioned; protocol symmetry with PI8)**
  `aba-PI9-armC-20260818T224101Z` — 22:41:01Z → 23:06:41Z, COMPLETED exit 0: 118 turns,
  25.4 min, $10.98, out 88,284 tok, session `296da3d6-e136-44f2-8136-24afbe4d2b72`.
  **ace_mcp_calls=0 (repaired counter) + zero API traffic + monitor confirmation. RULED
  DEGRADED/INVALID. No further reruns.**
  **PI9 arm C program finding, final: ZERO ADOPTION ×4 arm-C runs across two subjects and two
  tool surfaces (pre- and post-#237). The task-shaped-descriptions intervention is measured and
  falsified as a standalone adoption fix. Transcript forensics (run 1): the ACE tools never
  entered the subject's deliberation at all — zero consider-and-reject events; the binding
  constraint is attention/election, not description quality. Next intervention class per the
  capture proposals: push/ambient delivery or workflow-level instruction (host-side).**
  Rerun work product (bare provenance, uncommitted, 8 files): operator gates ALL GREEN — 37
  tests incl. both boundary suites, ruff clean repo-wide. Includes what appears to be a real
  process-restart test harness; review + delivery ranking dispatched.
  **Review: 6/7 PASS + 1 PARTIAL (export), COMPLETE-WITH-DEFECTS.** Narrowest of the three
  (hardcoded disclosure default, no host port, no CLI surfacing, quiescence on proof only) but
  contributes one novel asset: an AST-based architectural-boundary regression test keeping the
  "no derived-artifact pipeline" claim executable rather than prose. Its subprocess-boundary
  restart test verified EXECUTED (not skipped) by operator. No evidence doc (uncommitted work).
  **Reviewer delivery ranking: COMPOSE — arm A's design as base (host-injectable port with real
  product-fenced queries + active erasure resolves arm B's hardcoded-count risk), graft arm B's
  SurrealDB kill/respawn restart e2e (closes arm A's evidentiary gap; mechanical port), add arm
  C's boundary-regression test as defense-in-depth (code-drift guard complementing arm A's
  data-level queries). Do not carry arm B's unqueried port or arm C's hardcoded contract shape.
  All three extend the identical contract surface from the same head — graft, not rewrite.**

## PI9 verdicts (per §6)

- **C vs B: no valid arm C measurement** (both runs degraded, zero adoption). Vacant; the
  adoption failure is the recorded arm C result. **C vs A: not computed** (same).
- **B vs A (descriptive):** arm A outscored arm B at first review — COMPLETE (7/7, zero
  defects, all gates green by construction) vs COMPLETE-WITH-DEFECTS (7/7 but registry
  omission + the hardcoded covered/count=0 correctness risk flagged in comparative review).
  **Inverts PI8's ordering (Sonnet > Fable there).** Program tier story after two subjects:
  mixed, 1–1 — honestly reported, no aggregation per §6.
- **Intelligence-curve point:** provisioned-but-unadopted ×2 subjects; the #237 curve
  annotation records intervention-1 (task-shaped surface) as measured-ineffective for adoption.

## Delivery (rule 8, closed 2026-08-19)

With no valid arm C measurement, PI9 shipped as ordinary work in two halves, both merged:
- **#241** — additive surviving-derivative disclosure (Decision 9 disclosure half; reworked to
  the additive digest-excluded pattern after operator review flagged the original Literal edit).
- **#244** — derivative COVERAGE (delivery half), implemented by the operator from Edwin's
  direct subject prompt: preview enumerates the six AM4-vocabulary derivative kinds with exact
  product-fenced counts; confirm erases via a fail-closed host port before primary erasure;
  proof report derived deterministically from the preview (replay-safe); payload-filter Qdrant
  deletion; kill-respawn restart e2e (arm-B pattern). All gates green at merge.
Arm work products archived as diffs in `runs/` (armB 2707, armA 2046, armC 1349/838 lines);
all arm worktrees removed. The three-arm evidence base (arm A's port design, arm B's restart
e2e pattern, arm C's AST boundary-test idea) materially informed #244's design.

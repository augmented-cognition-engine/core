# PI12 subject registration — PI10 (third preregistered subject) — FROZEN 2026-08-19

**STATUS: FROZEN.** (1) F3 disposition recorded by the owner on issue #49: re-argued
containment scoped to the new bundle-registration surface; F3 proper remains open, re-dated
2026-11-05. (2) Isolation gate PASSED: a fresh arm-style worktree at the frozen head shows
zero `dc91c49` hits in `git log --all` and `git cat-file -e dc91c49` fails.
- **Frozen head: `e2e5e739479a4951f355bd39b1b6199cfe02b921`** (origin/main tip at freeze;
  contains #240–#246 including the A0 repository-relative-target fix this subject's arm C′
  depends on).
- **Runner v3: `run-arm-v3.sh`, sha256 prefix `36980ef5301bab127dad8572`** (extends pinned
  e88ae86: arm CP/C′ ambient-hook install from the frozen worktree via PYTHONPATH; scripted
  participant-2 stale-context induction for C/C′ with method+timestamp recorded in meta).
- **Additional frozen disclosures:**
  - In headless mode `UserPromptSubmit` fires exactly once (the subject prompt), so C′'s
    ambient surface has ONE injection opportunity per run — push-once-at-start vs C's
    pull-never baseline. The adoption metric counts journey injections + any MCP tool calls.
  - 1.1.0 defect (found in pre-flight, live-verified): the journey endpoint answers exactly
    once per fresh index store — first call 200, all subsequent calls 409 "snapshot
    precondition". Operator protocol: the index store is wiped immediately before the C′
    launch and no journey call intervenes, so the arm's single injection gets the working
    shot. Full injection verified end-to-end pre-freeze (2,355-byte cited context for the
    packet-pointed activation.py).
  - 1.1.0 defect: an incremental rescan overwrites the graph record's node/edge counters with
    the delta (tables unaffected; true counts recorded from tables: 3,314 files / 31,972
    nodes / 14,440 edges at freeze).
  - The subject prompt's working rules name the pack-machinery files via the packet's own §5
    reuse-map pointer (activation.py, compiler.py, schemas/) — packet-derived, identical for
    every arm; necessary because the A0 target derivation requires an existing repository
    Python file named in the prompt.
  - Environment anomaly: this session's background tasks were externally mass-killed three
    times (cause unknown; owner confirmed not them). All arm runs launch as detached daemons
    with file-based monitoring, immune to task sweeps.

- Registered: 2026-08-19 (draft)
- Operator: this session (claude-fable-5 as program operator; does not author subject code)
- Harness: **ace-builds-ace-harness-v2**, frozen config digest
  `08fe233c26a798657530a146b4ad66ef624d5abb7f0cb8cfa6be0cb6e64bb48c` (commit 0a133c3, recorded
  per §9 by #243). v1 values carry forward; v2 adds arm C′ and the code-intelligence-consultation
  measure with the C′-vs-C verdict.
- Runner: `codex/pi12-arm-runner` @ `e88ae86` + a **v3 extension (to be reviewed & pinned before
  freeze)** adding: arm C′ launch (installs the pinned `ace_mcp_client.ambient_hook` into the arm
  session config), and the v1 §3 ACE-arm session requirements (≥2 concurrent participants; ≥1
  stale-context event, induced if necessary, induction method recorded).
- Authorization: Edwin's selection of "run PI10 as the v2 subject first" with three recorded
  conditions (2026-08-19), F3 disposition pending.

## Exposure disclosure (owner condition a)

A complete non-arm implementation of this subject (commit `dc91c49`, 8 files, +2,746 lines)
existed before this registration, authored 2026-08-19 by a bare claude-fable-5 Claude Code
session in an isolated worktree off `a1cb8d7`, with no ACE assistance and no arm-session memory.
**Its design was summarized to the owner before this registration.** The subject scope and answer
key in `pi10-subject-prompt.md` are derived exclusively from the frozen packet text
(work-packet §6 PI10 row, Decisions 1, 3, and 14), issue #218, and the pre-existing activation
machinery as reuse substrate — not from anything dc91c49 chose. The operator drafted the prompt
after reading only those sources; the authoring session independently confirmed the packet text
and #218 suffice to derive the scope.

## Isolation record (owner condition b)

- `dc91c49` was bundled to two locations outside any repository (owner Desktop; pi12 archive,
  `pi10-dc91c49-exploratory.bundle`, verified) with its full diff archived.
- The branch `worktree-pi10-solution-bundles` and its worktree were removed from the shared dev
  repository with the authoring session's explicit consent (its lock waived, all work committed);
  `git log --all` there no longer reaches dc91c49.
- The operator clone (from which all arm worktrees are created) **never contained the object**
  (`git cat-file -e dc91c49` fails; zero hits in `git log --all`).
- PRE-LAUNCH GATE: `git log --all` executed inside a freshly created arm worktree must show no
  dc91c49 before the first arm launches; the output is appended here.

## Exploratory run record (owner condition c; spec §7 — excluded from the comparative result)

`dc91c49` is recorded as a **disclosed exploratory run** (a free bare-Fable reference point) and
a **Decision 16 retrospective experience capture**, with facts supplied by its authoring session:
2026-08-19, claude-fable-5 via Claude Code, fresh isolated worktree off `a1cb8d7`, bare arm-A
profile (no ACE, no arm memory); sources: packet PI10 row + Decisions 1/3/14 + issue #218 +
existing domain-activation machinery; deliverable: solution_bundle contracts + application
service + two bundle manifests + policy doc + 41 tests; verification at completion: 41/41 new
tests, whole-repo ruff clean, full non-e2e suite green modulo failures proven pre-existing
against a pristine origin/main archive; process: test-first with a golden receipt fixture pinned
for additive-only contract evolution. Not registered before running; therefore exploratory.
**Disposition: rule-8 fallback if arm C′ fails review beyond one rerun.**

## Subject

- Subject id: **PI10** — Solution Bundle machinery (work-packet §6; issue #218). Core +
  Application. Gated on **#49 F3** — owner disposition pending, to be linked here.
- Frozen repository head: **`a1cb8d7...`(full SHA recorded at freeze)** — current origin/main;
  contains #240 (ambient trigger, the C′ dependency), #241/#244 (PI9), #242/#243 (v2 freeze).
  Verified free of dc91c49.
- Frozen subject prompt: `pi10-subject-prompt.md` (identical for every arm).

## Arms (order B → A → C → C′, per v2)

| Arm | Config | Disposition |
|---|---|---|
| B | bare claude-sonnet-5 | floor control; evidence-only |
| A | bare claude-fable-5 | reference ceiling; evidence-only |
| C | claude-sonnet-5 + 1.1 ACE via eleven-tool MCP (pull) | **election control — evidence-only on this subject** (v2) |
| C′ | claude-sonnet-5 + same backend via pinned ambient hook (push) | **production path; the single arm whose output merges**, after ordinary review |

- Env: CC 2.1.224 (still pinned; verified at each launch), frozen no-web allowlist,
  `--strict-mcp-config`, 8h cap, max 1 rerun per arm.
- C and C′ session requirements (v1 §3, carried into v2 pins): ≥2 concurrent participants and
  ≥1 stale-context event. Planned induction (to be finalized at freeze): a scripted second
  participant session, operator-launched, that performs one recorded mutation of the shared
  workspace state mid-run (method + timestamp recorded). **Compliance note:** PI8/PI9 arm C runs
  did not implement this v1 requirement (single-participant sessions); disclosed here rather than
  silently carried forward — moot for their verdicts (both C runs were degraded on zero adoption)
  but binding for PI10.
- Arm C/C′ backend: fresh disposable stand-up at the frozen head per the documented recipe
  (tree-sitter pinned 0.25.2/1.4.1; graph_id `default`; product binding; doctor + live-provider
  PASS; traversal verified through ace_mcp_client before launch).

## Verdicts to compute (v2)

- **C′ vs C (within-tier adoption-mechanism):** adopted_and_better / adopted_but_neutral /
  no_adoption / worse — the preregistered 0→N test of ambient (push) vs election (pull).
  Baseline: code-intelligence consultation was 0 in all four v1 C runs (PI8 ×2, PI9 ×2).
- **C′ vs B (within-tier)** and **C′ vs A (tier-jump)** — quality measures per §6; tokens within
  tier only.
- B vs A descriptive observation continues the tier series (PI8: B>A; PI9: A>B).

## Run log

- **Arm B** `aba-PI10-armB-20260819T195424Z` — claude-sonnet-5, COMPLETED: 109 turns, 24.3 min,
  $9.74, out 103,605 tok, session `f074b85b-fd8b-42ac-9541-c6191778a61f`. Uncommitted, 8 files.
  Operator gates: its 4 test files 25/25, ruff clean, public-core + kernel gates pass; ONE
  contract-boundaries loaded-by-public-surface failure (registry trap, 6th program occurrence).
  **Review: 7/7 PASS, COMPLETE-WITH-DEFECTS.** MATERIAL FINDING: resolution is purely a
  function of the manifest — no installed-component cross-check, so a manifest naming
  never-compiled artifacts could activate (arm A models InstalledSolutionComponents and fails
  closed; the decisive design difference). Registry omission ×2 (one masked by an accidental
  transitive import). Minor: unbounded failure text vs arm A's typed 240-char report.
  Strengths vs A: code lives literally in ace/intelligence/packs/ per the packet pointer;
  fixtures build REAL compiled packs through the actual compiler pipeline; executable
  Decision-1 noun-boundary test (A's is prose); deactivation-injected-failure atomicity;
  full-content persisted-revision leakage scan.
- **Arm A** `aba-PI10-armA-20260819T195424Z` — claude-fable-5, COMPLETED: 57 turns, 20.9 min,
  $18.55, out 73,410 tok, session `8d89d041-141c-4e01-bb2b-011751975f4d`. Commit 60f8729,
  3 files +1,629. Operator gates: 14/14 own tests, ruff clean, public-core + kernel pass; same
  loaded-by-public-surface failure (5th occurrence).
  **Review: 7/7 PASS, COMPLETE-WITH-DEFECTS (registry omission only).** Reviewer highlights:
  most precisely answer-key-mapped test suite of the program (determinism pinned to a literal
  digest; injected mid-commit failure with store post-condition; preview proven zero-I/O; all
  three co-activation sub-claims independently tested); genuine reuse of pack-activation
  contracts + governed-state commit; live_authority=False doubly enforced; tightest commit
  message of the program (every claim verified).
- **Arm C** `aba-PI10-armC-…` — election control, RUNNING (detached), participant-2 induction
  armed. **Arm C′** queued behind it (index-store wipe immediately before launch).
- **Arm C** `aba-PI10-armC-20260819T202209Z` — election control, COMPLETED: 121 turns, 33.9 min,
  $11.34, session `8e4f81c9-c149-4f0a-9404-c18cda4fca76`. **Consultations: 0 (fifth consecutive
  election zero program-wide) — the baseline measurement, valid per v2 (evidence-only role).**
  Participant-2 induction fired at T+10:05, POST /observations 201 (API-log-recorded; the runner's
  meta echo mis-pathed — minor v3 defect noted). Work product: 6 commits, 3,883 lines incl. an
  1,841-line plan doc; boundary gates 24/24 (registered all three __init__ surfaces; published
  schemas). Spot-check-comparable quality per reviewer; not fully scored (control role).
- **Arm C′** `aba-PI10-armCP-20260819T205833Z` — ambient, COMPLETED: 99 turns, 22.6 min, $9.81,
  session `db74ea33-65ba-4611-a953-e22d925d8f32`. **Consultations: 1 — the ambient injection
  fired at T+6s (journey 200, grounded cited context for activation.py). First non-zero ACE
  consultation of the program; MCP election remained 0 as designed.** Participant-2 induction
  fired (2nd observations POST). Gates: 31/31 own tests, ruff+format clean, ALL boundary gates
  28/28. **Review: 7/7 PASS, COMPLETE-WITH-DEFECTS** — cleanest integration of the four arms
  (schema publication with live-contract sync tests; fixed-phrase bounded failure discipline,
  strongest of any arm; unique concurrent-deactivation race test; single-pack manifest reading
  of Decision 1). Shares the installed-component gap (3 of 4 arms); lacks arm A's golden-digest
  pin and arm B's Decision-1 boundary test.

## PI10 verdicts (harness v2)

- **C′ vs C (preregistered adoption-mechanism verdict): `adopted_but_neutral`.** The ambient
  mechanism produced the program's first consultation (0→1 at T+6s) — adoption by mechanism is
  PROVEN. But the election control independently achieved the two candidate injection
  fingerprints (registry-surface registration, schema publication), and the work products are
  comparably complete — the single session-start injection did not measurably lift quality on
  this subject. Operator framing correction on the record: the reviewer falsified the
  "C′ uniquely cleared the registry trap" claim by inspecting C directly (both ACE arms cleared
  it; all four program bare arms did not — n too small to interpret).
- **C′ vs B (within-tier quality):** comparable-to-stronger (C′ cleaner integration + all gates
  green vs B's material installed-component gap shared, minus B's real-pipeline fixtures);
  descriptive, no clean better/worse.
- **B vs A (descriptive):** both 7/7; complementary strengths (A: installed-check, golden pin,
  typed bounded failures; B: real compiler fixtures, Decision-1 boundary test, deactivation
  atomicity). Tier series after three subjects: PI8 B>A, PI9 A>B, PI10 ≈ — mixed, as reported.
- **Delivery (v2 rule: C′ is the single merging arm on adoption subjects):** C′ is VALID —
  recommendation: take C′'s work product through ordinary review → merge, grafting in review
  the three known small gaps (arm A's installed-component fail-closed check + golden-digest
  pin; arm B's Decision-1 boundary regression test). dc91c49 remains the rule-8 fallback,
  unused.
- **Program finding (PI12, three subjects complete):** ambient/push delivery SOLVES adoption
  (5 election zeros vs first-turn injection); a single session-start injection is NOT yet
  sufficient for measurable quality lift on bounded, well-specified subjects. The
  intelligence-curve point is `adopted_but_neutral` — the mechanism is validated, the value
  demonstration moves to richer injection surfaces (per-turn/per-edit triggers, which the
  A0 design doc already scopes) and to subjects with higher prior-knowledge leverage.
- Registry-trap tally final: 4 of 4 bare arms failed it; both PI10 ACE arms passed; repo-side
  fix proposal stands for closeout.

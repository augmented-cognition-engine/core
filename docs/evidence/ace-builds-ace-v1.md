# ACE Builds ACE evidence record v1

## Freeze record (opening entry, per harness spec §9)

- Date: 2026-08-18
- Harness: `ace-builds-ace-harness-v1`
- Frozen at: commit `a48eb8a7e0d224370f6ebef0621429514ec65534` (squash merge of PR #230, owner-approved)
- Config digest (SHA-256 of `docs/design/ace-builds-ace-harness-config-v1.json` at the frozen
  commit): `5ec835f197ebfb8c9e81e72b506ff119b1e77e0ab795139fd39b7ab5c8a18130`
- Spec: [`docs/design/ace-builds-ace-harness-v1.md`](../design/ace-builds-ace-harness-v1.md) at
  the same commit.

**From this entry forward, the harness is frozen.** Arm runs under any configuration whose digest
differs from the value above are exploratory by definition (spec §7). Configuration changes
require a `-v2` harness with its own digest; v1 runs remain reported under v1.

## Preregistered scope at freeze

- Eligible subjects: **PI8, PI9, PI10** (minimum two). PI2–PI7 merged before this freeze and are
  admissible only as `retrospective: true` records excluded from the preregistered comparative
  result (spec §8.2); unannotated gaps are valid and reported.
- Arms per subject, in order: B (bare `claude-sonnet-5`, evidence-only), A (bare
  `claude-fable-5`, evidence-only), C (`claude-sonnet-5` + shipped 1.1 Code Intelligence, the
  production path). Optional exploratory arm D (`claude-fable-5` + ACE) on at most one subject.
- Verdicts per subject: within-tier (C vs B) and tier-jump (C vs A), as defined in spec §6.
- Operator: the 1.2 ingestion session, acting under spec §2 rules 7–8 (operator is not an arm;
  production safety valve).
- Pre-existing exploratory material: `docs/evidence/ace-1.2-pi12-code-intelligence-smoke-v1.md`
  predates this freeze and is exploratory, not an arm run.

## Amendment freeze record (v2, per harness spec §9)

- Date: 2026-08-19
- Harness: `ace-builds-ace-harness-v2` (amends v1; all v1 values carry forward)
- Frozen at: commit `0a133c3253fd156ba3abbac57c62ad06b7d9dd39` (squash merge of PR #242,
  owner-approved)
- Config digest (SHA-256 of `docs/design/ace-builds-ace-harness-config-v2.json` at the frozen
  commit): `08fe233c26a798657530a146b4ad66ef624d5abb7f0cb8cfa6be0cb6e64bb48c`
- Spec: [`docs/design/ace-builds-ace-harness-v2.md`](../design/ace-builds-ace-harness-v2.md) at the
  same commit.

**From this entry forward, the v2 configuration is frozen.** v2 adds **arm C′** (`claude-sonnet-5`
+ ACE via the ambient hook, differing from arm C only in the ACE-access mechanism) and the
**code-intelligence-consultation** primary measure with the within-tier **C′-vs-C** verdict, so the
0→N adoption flip is preregistered rather than exploratory. v1 arm runs (PI8) remain reported under
v1 and are never relabeled; runs under any configuration whose digest differs from the value above
are exploratory (spec §7). Arm C′ depends on the ambient trigger merged in PR #240 (commit
`f4a3f24f25322e2407c9f2710086f32f1544789f`).

### v2 preregistered scope
- Adoption-comparison subjects: PI9 and/or PI10 run **both** C (election control, evidence-only) and
  C′ (ambient; the single merging arm), per owner confirmation; must be registered before the
  subject's arms run.
- New within-tier verdict: **C′ vs C** — adopted_and_better / adopted_but_neutral / no_adoption /
  worse — reported separately from the unchanged C-vs-B and C-vs-A verdicts.

## Run log

### PI8 — Grounded Ask and correction (J7/J8) — 2026-08-18

First preregistered subject. Frozen head `3899ae741909a0da7675767e77a924fcfeea6c18`
(origin/main tip at registration); frozen subject prompt and answer key identical for every arm;
CC pinned 2.1.224; config digest as frozen above. Full operator registration, void rulings,
environment workarounds, and review reports:
[`artifacts/pi12-pi8/pi8-subject-registration.md`](artifacts/pi12-pi8/pi8-subject-registration.md).
One §8 capture record per arm-run in [`artifacts/pi12-pi8/`](artifacts/pi12-pi8/).

| Arm-run | Model / config | Outcome |
|---|---|---|
| `aba-PI8-armB-20260818T162829Z` | bare claude-sonnet-5 | **Completed**, 187 turns / 39.0 min. First review: 6/6 acceptance criteria PASS, 1 minor finding (self-validated lexical answerer placeholder). Operator gates 72/72 + ruff clean. |
| `aba-PI8-armA-20260818T171602Z` | bare claude-fable-5 | **Completed**, 103 turns / 25.0 min. First review: 4/6 PASS + 2 PARTIAL, 2 major findings (Core→`ace.intelligence` boundary regression failing a pre-existing unconditional gate; parallel reimplementation of the proposal-only feedback machinery contra the answer key), 1 unsupported claim. |
| `aba-PI8-armC-20260818T185240Z` | claude-sonnet-5 + shipped 1.1 ACE MCP | **Degraded/invalid as the C measurement (§7): ZERO ACE MCP calls** across 182 turns despite 11 registered, error-free tools and a verified 31,424-node code graph. Confirmed by transcript tool_use parse, ACE API request log, and a live traffic monitor. |
| `aba-PI8-armC-20260818T193907Z` | claude-sonnet-5 + shipped 1.1 ACE MCP (sanctioned rerun 1 of 1) | **Degraded/invalid again: ZERO ACE MCP calls** across 143 turns under byte-identical conditions. No further reruns. As bare work product: reviewer scored 6/6, COMPLETE-WITH-DEFECTS, and ranked it first of the three arms for delivery. |

Void launches (listed per §7; zero subject work product in each, rulings in the registration):
`armB-…T162429Z` (exit 127, host lacked GNU `timeout`), `armA-…T162907Z` (provider API 500 at
start), `armA-…T163245Z` (provider incident kill mid-exploration, clean worktree; documented
status-page incident from 16:20Z).

**Verdicts (per §6):**

- **C vs B (within-tier): no valid arm C measurement.** The preregistered comparative claim for
  PI8 is vacant. The recorded arm C program result is the adoption failure itself:
  **availability without adoption** — a fully provisioned, verified ACE backend and a bare-Sonnet
  agent that never elected to call it, twice. Ships as a valid negative-class outcome (§6).
- **C vs A (tier-jump): not computed** (same reason).
- **B vs A (descriptive observation, not a preregistered verdict):** bare Sonnet outscored bare
  Fable at first review on the frozen answer key (6/6 + 1 minor vs 4/6 + 2 major). Token and
  latency figures are not compared across tiers.
- **Intelligence-curve point (§8.1):** provisioned-but-unadopted; `prior_slice_provenance` empty;
  no compounding claim. The capture records carry a `context`-kind proposal (task-shaped tool
  surface / session-start injection), implemented as ordinary 1.2 work (PR #237) and to be
  measured under this same harness in PI9.

**Delivery (harness §2 rule 8):** with no valid arm C, PI8 shipped as an ordinary implementation
with disclosed bare-model provenance — the arm C rerun's work product plus operator review fixes,
PR #236. The experiment did not block 1.2 delivery.

**Instrument findings recorded for PI9:** the runner's `ace_mcp_calls` check counted transcript
lines (matching the tools-available attachment) rather than `tool_use` blocks and reported 1 for
zero-call runs — fixed on `codex/pi12-arm-runner` (`e88ae86`) alongside the two arm-B launch
defects (`$OLDPWD` prompt-path doubling, missing GNU `timeout`) fixed at `134705f`. PI9
registration pins the repaired runner.

**Retrospective PI2–PI7 (§8.2):** not yet annotated — reported as gaps, which the spec treats as
a valid state. Any future annotation appends here labeled `retrospective: true`.

### PI9 — ownership depth (J9/J10) — 2026-08-18/19

Second preregistered subject, run under harness v1 (same frozen digest). Frozen head
`45b48b80789214c4f5de9f443fa0bb208171d890` — the first head carrying PR #237's task-shaped
thin-client surface, making PI9 the preregistered before/after test of the PI8 adoption finding.
Runner: repaired `codex/pi12-arm-runner` @ `e88ae86`; CC 2.1.224. No voids, no incidents.
Registration and one §8 capture record per arm-run:
[`artifacts/pi12-pi9/`](artifacts/pi12-pi9/).

| Arm-run | Model / config | Outcome |
|---|---|---|
| `aba-PI9-armB-20260818T213359Z` | bare claude-sonnet-5 | **Completed**, 185 turns / 33.4 min. Review: 7/7 PASS, COMPLETE-WITH-DEFECTS — sole defect a boundary-allowlist registry omission; contains the program's strongest single test (real SurrealDB kill/respawn restart-continuity e2e). |
| `aba-PI9-armA-20260818T213417Z` | bare claude-fable-5 | **Completed**, 104 turns / 36.2 min. Review: 7/7 PASS, **COMPLETE — first unqualified COMPLETE of the program**; product-fenced query-verified enumeration + active erasure with post-erasure verification; all boundary gates passed by construction. |
| `aba-PI9-armC-20260818T221001Z` | claude-sonnet-5 + ACE MCP (task-shaped surface) | **Degraded/invalid (§7): ZERO ACE MCP calls** (repaired tool_use counter + API log + live monitor). Transcript forensics: the tools never entered deliberation at all. |
| `aba-PI9-armC-20260818T224101Z` | same (sanctioned rerun 1 of 1) | **Degraded/invalid again: ZERO ACE MCP calls.** As bare work product: 6/7 PASS + 1 PARTIAL; contributes an AST boundary-regression test idea. |

**Verdicts (§6):**

- **C vs B and C vs A: no valid arm C measurement — vacant.** The recorded arm C result is the
  adoption finding at full strength: **zero adoption in 4/4 arm-C runs across two subjects and
  two tool surfaces (pre- and post-#237)**. Intervention 1 (task-shaped tool descriptions,
  PR #237) is measured and falsified as a standalone adoption fix; the binding constraint is
  election/attention, not description quality.
- **B vs A (descriptive):** arm A outscored arm B (COMPLETE vs COMPLETE-WITH-DEFECTS) —
  inverting PI8's ordering. Program tier story after two subjects: mixed, reported without
  aggregation.
- **Intelligence-curve point:** provisioned-but-unadopted ×2. The capture records' `context`
  proposal (remove the election step) was implemented as ordinary work — the A0 ambient trigger
  (PR #240) — and harness **v2** (PR #242, digest recorded per §9) preregisters arm **C′** and
  the adoption metric to measure the 0→N flip on the next subject.

**Delivery (rule 8):** PI9 shipped as ordinary work in two merged halves — #241 (additive
surviving-derivative disclosure) and #244 (derivative coverage: product-fenced enumeration,
fail-closed erasure port, deterministic replay-safe proof report, payload-filter vector
deletion, kill-respawn restart e2e). The three-arm evidence base materially informed #244's
design; the arms' work products are archived with the registration. The experiment did not
block 1.2 delivery.

### PI10 — Solution Bundle machinery — 2026-08-19 (harness v2)

Third and final preregistered subject; the first (and only) run under the **v2** amendment with
arm **C′** and the code-intelligence-consultation measure. Frozen head
`e2e5e739479a4951f355bd39b1b6199cfe02b921` (contains the A0 repository-relative-target fix,
PR #246, found and fixed in this subject's own pre-flight). Runner v3 (`36980ef5…`): arm C′
ambient-hook install from the frozen worktree; scripted participant-2 stale-context induction
for the ACE arms (a v1 §3 requirement disclosed as unimplemented in PI8/PI9's arm C runs).
Registration — including the dc91c49 exposure disclosure, isolation record, §7 exploratory
entry, and three live-verified 1.1.0 defects (single-shot journey index, incremental-scan
counter clobber, journey/index state divergence) — and one §8 capture record per arm-run:
[`artifacts/pi12-pi10/`](artifacts/pi12-pi10/).

| Arm-run | Config | Outcome |
|---|---|---|
| `aba-PI10-armB-…195424Z` | bare claude-sonnet-5 | Completed. 7/7 PASS, COMPLETE-WITH-DEFECTS; material gap: no installed-component cross-check; contributed the executable Decision-1 boundary-test design. |
| `aba-PI10-armA-…195424Z` | bare claude-fable-5 | Completed. 7/7 PASS, COMPLETE-WITH-DEFECTS (registry omission only); the program's most precisely key-mapped test suite; contributed the installed-component fail-closed check and golden-digest pin. |
| `aba-PI10-armC-…202209Z` | + ACE via MCP (election control) | Completed, valid in its v2 evidence-only role. **Consultations: 0 — the fifth consecutive election zero program-wide.** Induction fired T+10:05 (201). |
| `aba-PI10-armCP-…205833Z` | + ACE via ambient hook (the merging arm) | Completed. **Consultations: 1 — the ambient injection fired at T+6s (journey 200): the program's first non-zero ACE consultation.** 7/7 PASS, COMPLETE-WITH-DEFECTS; the only work product of the program's seven with all boundary gates green at first review. |

**Verdicts (v2):**

- **C′ vs C (preregistered adoption-mechanism verdict): `adopted_but_neutral`.** Adoption by
  mechanism is proven — push (ambient injection) consulted where election never did, 1 vs 0
  against five election zeros. Quality did not measurably lift: the election control
  independently matched the candidate injection fingerprints (the reviewer falsified the
  operator's uniqueness framing by direct inspection — recorded as the adversarial process
  working), and the work products are comparably complete.
- **C′ vs B / C′ vs A:** comparable quality; descriptive only. **B vs A:** both 7/7 with
  complementary strengths; tier series ends mixed (PI8 B>A, PI9 A>B, PI10 ≈).
- **Delivery:** per the v2 single-merging-arm rule, C′'s work product merged as **PR #247**
  (base commit + operator review grafts closing the three cross-arm gaps: installed-component
  fail-closed check and golden-digest pin from arm A's design, executable Decision-1 boundary
  test from arm B's). The dc91c49 exploratory implementation (§7, Decision 16 retrospective)
  was not needed as a fallback and never merged.

## PI12 program result (three subjects complete)

Per §6, descriptive per-subject tallies, no aggregation — and in §6's own words: with three
subjects there is no statistical claim.

- **The adoption arc is the program's headline.** Election-based ACE consultation was zero in
  five of five ACE-arm runs across all three subjects and two tool surfaces (pre- and
  post-#237's task-shaped descriptions — intervention 1, measured and falsified). The ambient
  mechanism (A0, PR #240, repaired by #246) consulted on its first preregistered attempt.
  **Push solves adoption; election does not happen.**
- **Value is not yet demonstrated:** one static session-start injection produced
  `adopted_but_neutral` — no measurable quality lift on a bounded, well-specified subject
  against a strong same-model control. The capture records' `context` proposal moves the value
  test to richer injection surfaces (per-turn/per-edit triggers, scoped in the A0 design doc)
  and to subjects where prior-session knowledge is the binding constraint.
- **Comparative quality:** C-vs-B and C-vs-A were vacant on PI8/PI9 (zero adoption) and
  C′-vs-C neutral on PI10. Bare-tier observation: mixed (B>A, A>B, ≈) — no tier claim.
- **The method finding:** across seven scored work products, one calibrated adversarial
  reviewer caught a latent correctness risk (PI9 arm B's hardcoded counts), falsified two
  operator framings, and drove three merged deliveries composed from complementary arm designs
  (#236, #244, #247). Multi-arm generation + adversarial review + composed delivery repeatedly
  produced better-than-any-single-arm results — independent of the ACE adoption question.
- **Instrument integrity:** every void, drift event, environment anomaly, operator error, and
  defect (eight 1.1.x product defects, four instrument defects) is recorded in the
  registrations. Deleting a run was never an available action; none was deleted.

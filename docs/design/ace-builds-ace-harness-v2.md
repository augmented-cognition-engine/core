# ACE Builds ACE comparison harness v2 — ambient-consultation amendment

- Date: 2026-08-18
- Status: **proposed amendment for owner review; not frozen.** Per harness v1 §9, a configuration
  change requires a `-v2` harness with its own digest; v1 runs remain reported under v1. Merging
  this amendment is the owner's approval of the pinned v2 configuration; the freeze completes when
  the merged `ace-builds-ace-harness-config-v2.json` digest is recorded in
  `docs/evidence/ace-builds-ace-v1.md`. Until that digest exists, no PI12 subject run is
  preregistered under v2.
- Amends: [ACE Builds ACE comparison harness v1](ace-builds-ace-harness-v1.md). Everything in v1
  not restated here is unchanged and carries forward verbatim (arms A/B, protocol rules §2.1–2.8,
  measures §5, analysis §6, exclusion/drift §7, capture-record shape §8, freeze procedure §9).
- Authority: packet Decisions 13, 15, 16; candidate Decision 17 (ambient self-improving loop —
  [note](ambient-code-intelligence-auto-trigger-v1.md)), which this amendment does **not** presume
  frozen; it only measures the mechanism that decision proposes.
- Dependency: the ambient trigger (PR #240) must be merged before an arm C′ run, since C′ installs
  it into the arm session. C′ cannot be registered against the v2 digest until that ships.

## 1. Why a v2 is needed (the observed gap)

Harness v1 pins the ACE arm (arm C) to *"the shipped eleven-tool 1.1 Code Intelligence MCP
surface"* (v1 §3) — a **pull** surface: the model must elect to call a tool. In the first PI12
subject run (PI8), **arm C made zero code-intelligence consultations** — a total election failure,
recorded honestly as v1 evidence. That result measures adoption-by-discretion, and it was ~0.

The ambient trigger changes the *mechanism*, not the backend: a gated runtime hook consults the same
journey on relevant turns and injects grounded, cited context, so consultation no longer depends on
the model electing to call a tool. Measuring the resulting **0→N adoption flip as preregistered
evidence** is impossible under the v1 digest, because an ambient-hook arm C differs from the frozen
arm-C configuration — under v1 §7 it would be labeled *exploratory* and excluded from the
comparative result. A frozen v2 is the clean route; anything else makes the flip an anecdote.

## 2. The amendment — add arm C′ and one preregistered measure

### 2.1 New arm

| Arm | Definition | Disposition |
|---|---|---|
| **C′ — mid-tier + ambient ACE** | `claude-sonnet-5` over the **same** live 1.1 backend as arm C, differing from C in exactly one pinned element: ACE is reached through the **ambient hook installed in the session config** (gated, fail-closed, auto-firing the journey on relevant turns) instead of, or in addition to, the eleven-tool MCP surface. Same task, repository head, budgets, tool allowlist, and authority as C. | The production path when the ambient trigger is shipped (proceeds through ordinary review and merge). |

Arm C is **retained as the election control** for the subjects where the adoption comparison is
measured: same everything, ACE reached only through the MCP surface (as in v1). C becomes
evidence-only on those subjects (like A/B); **C′ is the single arm whose output merges**, preserving
v1 §2.5 "only one implementation merges." This makes the flip a **within-tier C vs C′ comparison**
that isolates the adoption mechanism — same model, same backend, election vs. ambient — rather than a
side experiment or a perturbation of the A/B/C tier ladder.

*Owner decision points (flagged, not presumed):* (a) run C and C′ on every v2 subject, or only on
the subject(s) where adoption is the question (recommended: at least PI9 and one of PI10, to get a
two-point within-tier series); (b) confirm C′ (ambient) is the merge path and C (election) is the
control. The exploratory arm D (`claude-fable-5` + ACE, v1 §2) is unchanged and may pair with a
D′ ambient probe under the same rule if the owner wants a top-tier adoption point.

### 2.2 New preregistered measure — code-intelligence consultation

Added to v1 §5 **primary** measures (it is a quality-of-orientation measure, not merely cost):

| Measure | Definition |
|---|---|
| Code-intelligence consultation | Per arm-run: the count of code-intelligence consultations and how many were **load-bearing** (resolved context the agent's accepted change actually used). A consultation is an MCP-tool invocation (arm C / A-with-MCP) or an ambient-injection event (arm C′). Arm C's v1 PI8 value was 0; this measure makes the 0→N flip a first-class, preregistered quantity rather than an incidental observation. Load-bearing consultations reuse the v1 §8 `retrieval_shortcuts` accounting. |

### 2.3 New verdict rule

Added to v1 §6 analysis, within-tier only:

- **Adoption-mechanism verdict (C′ vs C)** — **adopted-and-better**: C′ raises code-intelligence
  consultation above C's near-zero baseline **and** improves a majority of the primary quality
  measures while materially worsening none; **adopted-but-neutral**: consultation rises but quality
  is unchanged (adoption was not the bottleneck — a valid, informative outcome); **no-adoption**: the
  ambient path did not raise consultation (a hook/gate defect, recorded as such); **worse**: C′
  materially worsens a primary measure. Token/latency are compared within tier only (v1 §6). This
  verdict is reported **separately** from the v1 C-vs-B lift and C-vs-A tier-jump verdicts, which are
  unchanged and continue to use arm C (election) as the ACE arm for cross-tier comparability with the
  v1 series.

## 3. Configuration delta (the v2 digest)

`ace-builds-ace-harness-config-v2.json` is `-config-v1.json` plus exactly: (a) the arm C′ definition
and its ambient-hook install step (the hook command, gate/fail-closed settings, and the exact
`ambient_hook` build the session uses — pinned by commit); (b) the consultation measure and the
C′-vs-C verdict rule; (c) the arm-order note (bare arms first, then C, then C′ — disclosed per v1
§2.3, an extension of the same known limitation). Its SHA-256 at the merged commit is the **v2
digest**, recorded per v1 §9. No v1 value is changed; v1 arm-C/A/B PI8 runs remain reported under v1
and are never relabeled.

## 4. Invariants carried forward unchanged

No self-authority (v1 §2.6 — C′ holds no approve/merge/promote/deploy authority; the ambient hook
only *surfaces* cited context, it never activates anything); the production safety valve (v1 §2.8 —
if C′ fails review beyond one rerun, the verdict is recorded honestly and production reverts to an
ordinary implementation; the experiment never blocks 1.2 delivery); fresh sessions, isolated
worktrees, authority parity, minimal-intervention operation, the operator-is-not-an-arm rule, the
exclusion/drift rule (v1 §7 — a C′ run whose config differs from the v2 digest is exploratory), and
the append-only §8 capture-record shape (a C′ run appends the same record; its `context_manifest_refs`
capture the ambient injections' selection/omission receipts). A negative or mixed C′-vs-C result is a
valid outcome and does not gate J1–J10.

## 5. Timing

This amendment must be frozen (merged + digest recorded) **before PI10**, so C′ is preregistered for
the PI9/PI10 subjects and the adoption flip lands as evidence rather than an exploratory anecdote.
The ambient trigger (PR #240) must merge first, since C′ installs it. If #240 is not merged by the
PI9 registration, the owner may (a) hold the v2 freeze until it is, or (b) freeze v2 now and register
C′ only from the first subject after #240 merges — the earlier subjects run under v1 as today.

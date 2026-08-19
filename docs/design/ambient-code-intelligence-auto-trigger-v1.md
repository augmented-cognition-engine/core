# Baked-in code intelligence: a governed self-improving loop (v1)

- **Status:** Candidate decision — proposed **Decision 15** for the ACE 1.2 Personal Intelligence
  work packet. Not yet four-record reconciled (ROADMAP, milestone issue, Project, evidence); not
  frozen. A systems-theory stability review is **complete** (2026-08-18): the safe initial envelope is
  **A0 / propose-only in full plus one A1 cell (`embedding_reconciler`)**; loop-driven A1 beyond that
  is gated on the prerequisites recorded in §4 and [autonomy matrix §9](ace-autonomy-matrix-v1.md).
  Adoption still requires owner sign-off and reconciliation.
- **Date:** 2026-08-18
- **Reconciles against:** [personal-intelligence-v1.2-work-packet-v1.md](personal-intelligence-v1.2-work-packet-v1.md)
  — extends Decision 14 (Code Intelligence composes), obeys Decision 7 (Ask is a governed service),
  Decision 8 (corrections are proposal-only), Decision 11 (eleven-tool MCP surface), and Decision 13
  (ACE holds no approve/merge/promote authority over itself).
- **Thesis:** Code intelligence is not just a lookup an agent may call. It is the **sensing and
  diagnosis stage of a governed self-improving engine** — self-healing, self-improving — baked into
  the ACE runtime so that everyone who builds on ACE inherits an engine that gets better as it is
  used. The auto-trigger is how the loop starts; the loop is the role.

## 1. Problem: a soft trigger is not "baked in"

Today ACE intelligence is surfaced as MCP tools whose *descriptions* ask the agent to call them
("Always call this before starting work in a domain"; "Call this when you encounter code that seems
odd"). Triggering depends on the agent model reading the description and choosing to obey.

We have direct evidence this under-fires. When the PI8 slice was implemented as a **PI12 subject
arm-run, arm C (Sonnet *with* ACE available) made zero MCP calls** — the trigger clauses were
present and the model still never reached for code intelligence, including on
decision/roadmap/functionality-reconciliation questions, which are exactly what the graph exists to
answer. #237 sharpened those clauses, but a sharpened description is still a soft trigger. Whether
it fires is left to per-turn model discretion; a runtime guarantee removes that discretion.

"Auto-triggered / baked in" is a **mechanism** claim, not a wording claim. A description asks; a
mechanism guarantees. And a mechanism that only *reads* undersells the role: the same sensing that
answers a question can detect drift, breakage, and improvement opportunity — and start a loop.

## 2. Principle: push (inject), don't pull (hope it's called)

Move from **pull** — the model decides to call a retrieval tool — to **push** — the runtime detects
a relevant moment, retrieves grounded, cited context, and *injects it into the turn* before the
model answers. Pull depends on per-turn model discretion, which is unreliable and unmeasurable. Push
fires whether or not the model would have thought to ask. The trigger-clause tool stays as an
on-demand "go deeper" path; the injected floor is what makes the capability "just there."

## 3. The role is bigger than retrieval: a governed self-improving loop

Retrieval is stage one. The full role of baked-in code intelligence is a closed control loop:

```
sense → diagnose → propose → (governed) activate → verify → learn → sense …
```

1. **Sense.** Ambient code intelligence over the shared graph: current state, drift between graph
   and source, broken or unresolvable citations, contract/invariant regressions, coverage decay,
   and architecture-improvement opportunities.
2. **Diagnose.** Turn signals into **grounded, cited claims** about what is wrong or improvable —
   or an honest no-answer naming missing coverage. Never an uncited assertion.
3. **Propose.** Emit a **governed re-derivation / repair / improvement proposal** — never a silent
   mutation (Decision 8). Reuses the existing feedback machinery, not a new authority path.
4. **Activate (governed).** A human or explicitly delegated, governed gate approves and activates.
   ACE never approves, merges, promotes, or deploys itself (Decision 13).
5. **Verify.** Confirm the change actually improved things (effectiveness/calibration recompute);
   an honest "no improvement, or made it worse → revert the proposal" is a valid, expected outcome.
6. **Learn.** Fold the verified outcome back into the graph so the next cycle senses better.

### Self-healing — grounded in Sentinel, not invented

ACE already runs a background engine family — `core/engine/sentinel/` (`conflict_detector`,
`decay_manager`, `embedding_reconciler`, `effectiveness_recomputer`, `failure_analysis`,
`evaluator_honesty`, `edge_inference_sweeper`, …). Baked-in code intelligence is the **sensing and
diagnosis layer that feeds these reconcilers**: when the graph drifts from source, a citation stops
resolving, or an invariant regresses, the loop opens a **governed repair proposal** and verifies
non-regression after activation. Self-healing = *detect → propose repair → governed activate →
prove it did not regress*, never a silent fix. (⚠ Prerequisite: `reasoning_edge` has no decay/TTL
today, so stale edges to archived/expired endpoints keep tripping the broken-citation sensor —
endpoint invalidation is required before edge/citation self-heal enters the closed loop; matrix §9.)

### Self-improving — grounded in the feedback/review spine

The governed spine already exists: `ace/application/decision_feedback.py`,
`intelligence_resource_feedback.py`, `intelligence_build_review.py`,
`intelligence_builder_activation.py`. The loop surfaces architecture, coverage, and calibration
improvements as **proposals** through this spine. PI12 already requires an "architecture-opportunity
review or justified no-opportunity" as a one-off experiment step; this decision **productizes that
into a standing capability** — the engine continuously proposes how it could be better, and humans
decide.

### The governance resolution: self-improving ≠ self-authorizing

This is the crux, and it must be explicit. A self-improving engine that could also *authorize its
own changes* is a runaway system ACE's charter forbids. The resolution: **ACE improves itself as a
proposal generator; the actuator is always governed.** Proposal-only (Decision 8), no
self-approve/merge/promote (Decision 13), fail-closed, every action a reversible cited receipt.
"Self-improving, baked in" is true in the cybernetic sense — a continuous sense/diagnose/propose
loop — and safe because a human (or explicitly delegated, governed) hand pulls the activation
trigger. Remove that gate and you do not have a better product; you have an ungoverned one.

## 4. What makes it ambient *and* safe

Four properties make the loop "just there and better," plus a safety envelope because it is now a
feedback loop, not a one-shot read.

1. **Gated, not always-on.** A cheap classifier/heuristic decides *when* to fire — repo/graph in
   scope? turn touches a file, symbol, decision, "why", roadmap, or a health signal? Firing every
   turn floods context and degrades the model. Gate precision is the whole game.
2. **Grounded and cited, fail-closed.** Every injected answer and every proposal reuses
   `GroundedClaimV1Alpha1` / `CitationV1Alpha1` and returns an honest no-answer on missing coverage.
   Auto-anything without citations is only a faster way to be confidently wrong.
3. **A platform primitive, not per-app wiring.** The loop lives in the lowest layer every ACE
   integration inherits — the runtime/adapter middleware — so a Domain Pack author, an app builder,
   Atrium, and an IDE plugin all get self-healing, self-improving intelligence *for free*. If each
   builder must opt in, it is not baked in. This is the operative meaning of "helps builders build
   intelligence."
4. **Layered — hook is the floor, tool is the ceiling.** A deterministic hook guarantees the
   baseline; the trigger-clause tool remains for depth.

**Feedback-loop safety envelope** (required, because an autonomous loop can oscillate or run away):

- **Staged autonomy, assigned per action by the autonomy matrix.** The loop does not carry one
  global autonomy level; every action it requests is tiered by the companion
  [ACE autonomy matrix](ace-autonomy-matrix-v1.md) (A0 surface → A1 auto-heal → A2 propose/review →
  A3 elevated → A-never). The loop chooses *when* to fire; the matrix, enforced at the trust
  boundary, chooses *what autonomy* the resulting action may have. The loop never self-classifies.
- **Loop gain and thresholds are explicit.** Any config constant that governs how strongly a signal
  drives a proposal is loop gain and is treated as such (documented, bounded, reviewed) — per the
  standing rule that a threshold constant functioning as gain gets a systems-theory review.
- **Hysteresis and damping.** Cooldowns and dedupe against open/decided items, keyed on
  **attribution state, not existence** (a repaired-but-still-unattributed node must not be re-proposed
  each cycle). ⚠ The substrate has none of this today: the Sentinel trigger
  `DEFAULT_MUTATION_THRESHOLD=5` (`triggers.py`) is a bare level comparator with no cooldown, and
  `reasoning_edge` has no TTL — together they drive a ~24 h decay⇄repair limit cycle (matrix §9).
  Attribution-keyed dedupe + edge TTL are ship prerequisites.
- **Circuit breaker + rate/budget bounds.** A kill switch and per-cycle budget caps; a degraded or
  uncertain state reverts to surface-only (the rule-8 safety valve, generalized). ⚠ Not present
  today: Sentinel has only a *same-engine* concurrency guard (`scheduler.py:208`), no shared
  cross-engine breaker, and it fails **open** on trigger error (`scheduler.py:318`). A shared breaker
  and a fail-closed override are ship prerequisites (matrix §6.2, §9).
- **Prove-improvement-or-revert.** No self-heal/self-improve action is "done" until the verify stage
  shows it helped; otherwise the proposal is reverted and the loop records why. ⚠ Verify MUST use a
  per-change, short-horizon, pre-registered delta computed from observations the loop **cannot itself
  write**. The 30-day rolling `effectiveness_recomputer` window is too slow and too diluted to serve
  as the damper and is foolable via window dilution, self-generated observations, attribution
  laundering, and re-ID quarantine escape — so it cannot license any auto-act tier.
- **Systems-theory gate.** No L2/L3 loop ships without a feedback-stability review (loop gain,
  oscillation, coupling to other autonomous subsystems). Named as a hard prerequisite in §9.

## 5. How it lands in ACE without breaking its rules

The hard pieces already exist; this decision *connects* them.

- **Engine:** Decision 7's governed Ask service (PI8) is the grounded retrieval/diagnosis engine the
  loop calls.
- **Actuator:** the existing feedback → review → activation spine and Sentinel reconcilers are the
  governed actuators; the loop generates proposals *for* them, holding no new authority.
- **No twelfth MCP tool.** The trigger and loop are runtime/adapter middleware calling existing
  application services — the eleven-tool public surface (Decision 11) stays fixed.
- **Core/Intelligence stay pure.** Sensing/injection/proposal I/O lives in the adapter/runtime
  layer, never in `ace/core` or `ace/intelligence` (Decision 1).
- **Governed like everything else.** Every cycle runs under the ordinary authorization, budget, and
  receipt path, with Decision 12 progressive disclosure (inject a compact cited answer, not a graph
  dump).
- **Composition, extended.** Decision 14 makes Code Intelligence a composable capability over the
  shared graph; this decision adds that co-activated capabilities are consulted **ambiently and
  continuously**, so composition delivers self-healing/self-improving value without depending on an
  agent remembering to ask.

## 6. Anti-patterns / the honest caveats

- **Ungated injection makes agents worse** — context pollution, lost-in-the-middle, confident
  staleness. The bar is gate precision + citation discipline, not "always on."
- **A self-authorizing loop is the failure, not the goal.** Any design that lets ACE activate its
  own changes violates Decision 13. The activation gate is load-bearing.
- **Oscillation and alert-fatigue.** A loop with no hysteresis re-proposes forever and trains
  builders to ignore it; then the capability is worse than nothing. Damping is not optional.
- **Improvement theater.** A proposal that is never verified is a guess. Prove-improvement-or-revert
  is what separates a self-improving engine from one that merely churns.

## 7. Candidate Decision 15 (proposed packet wording)

> **15. Intelligence is a governed self-improving loop, baked into the runtime.** ACE code
> intelligence (the driving case; the pattern general to all forms) is surfaced ambiently as the
> sensing and diagnosis stage of a closed loop — sense → diagnose → **propose** → governed activate
> → verify → learn. A gated runtime trigger consults the governed Ask service (Decision 7) on
> relevant events and injects grounded, cited, fail-closed answers; the same sensing raises
> proposal-only self-heal and self-improve items (Decision 8) into the existing feedback → review →
> activation spine and Sentinel reconcilers. ACE holds no approve/merge/promote/deploy authority
> over itself (Decision 13): the actuator is always a human or explicitly delegated governed gate.
> The loop is runtime/adapter middleware every integration inherits, adds no MCP tool (Decision 11),
> keeps `ace/core` and `ace/intelligence` pure (Decision 1), runs under the ordinary authorization,
> budget, and receipt path with progressive disclosure (Decision 12), and ships under a feedback
> safety envelope (explicit loop gain, hysteresis, circuit breaker, prove-improvement-or-revert).
> Every action the loop requests is tiered by the **ACE autonomy matrix** (companion governance
> decision), enforced at the trust boundary; the loop never self-classifies. Ungated or uncited
> action is prohibited; gate precision, citation
> discipline, and a passing systems-theory stability review are acceptance criteria. An honest
> measured non-improvement is a valid outcome. **Initial shippable envelope (per the stability
> review): A0 surface / propose-only in full, plus exactly one A1 cell (`embedding_reconciler`).**
> Loop-driven A1 auto-heal beyond that is gated on the matrix §9 prerequisites — fail-closed
> boundary override, a real edge-inference gate, a per-change verify damper the loop cannot self-write,
> attribution-keyed hysteresis + edge TTL, and a shared cross-engine circuit breaker.

## 8. Reconciliation and separation from PI12

| Piece | Role | State |
|---|---|---|
| Decision 7 — governed Ask service | The sense/diagnose **engine** the loop calls | Implemented (PI8) |
| Sentinel + feedback/review/activation spine | The governed **actuators** the loop proposes to | Exists |
| #237 — task-shaped tool descriptions | **Soft** trigger; on-demand ceiling | Merged; unmeasured |
| **This note — ambient loop middleware** | **Hard** trigger + governed loop; the guaranteed floor | Candidate (Decision 15) |
| Decision 14 — composition | What co-activates; this note governs **when/how** it fires | Frozen |

**Kept separate from PI12 — structurally, not stylistically.** Decision 15 is a product/architecture
capability; PI12 is an observational meta-experiment.

- **PI12's result is allowed to be null.** Decision 13 states the ACE-Builds-ACE result "does not
  block the J1–J10 gate" and grants ACE no authority over itself. Gating a shippable capability on a
  PI12 measurement would let a valid negative experiment veto the product. Product ships and
  experiment reports independently.
- **The loop has its own success criteria**, testable without the 3-arm program: gate
  precision/recall; integration tests that it fires on the right events, injects grounded **cited**
  context, raises **proposal-only** repairs, and **fails closed**; and prove-improvement-or-revert
  on the verify stage.
- **PI12 stays an independent observer.** A shipped loop will incidentally raise PI12's "later
  material use" and reduce its rework metrics; PI12 may report that as one datum among many, but it
  neither owns nor gates Decision 15. Neither a null PI12 nor a null loop result invalidates the
  other.
- **Slice placement:** a product-track capability (its own slice or an extension of the PI8
  service-caller layer, assigned at reconciliation); explicitly **not** a PI12 deliverable.

Recommended order: (a) reconcile Decision 15 into the packet; (b) systems-theory stability review of
the loop (§9); (c) build the L1→L2 loop as a caller of the Decision 7 service + feedback spine, with
gate + citation + safety-envelope contracts; (d) verify on the product track.

## 9. Out of scope / open questions

- **Systems-theory stability review is a hard prerequisite** before any L2/L3 loop ships — loop
  gain, oscillation, hysteresis sizing, and coupling to existing Sentinel engines (which are
  themselves autonomous). Two autonomous subsystems being connected is exactly the review trigger.
- **Gate implementation.** Heuristic vs. small-classifier vs. hybrid, and its precision/recall
  target; false-fire rate is the primary risk.
- **Event set and per-event budgets.** Which runtime events fire the loop (session-start,
  repo-enter, pre-answer, tool-result, health signal) and their bounds.
- **Autonomy-level assignment per action class.** Which repair/improve classes, if any, ever earn
  L3 bounded auto-act, and inside what envelope. Default is none until evidenced.
- **Approval/activation** of any surfaced proposal remains human/governed and out of scope
  (Decisions 8 and 13 unchanged).
- **Surfaces.** This note specifies runtime/client middleware; per-surface injection points (Atrium,
  IDE, MCP client) inherit the loop but each may need its own wiring.

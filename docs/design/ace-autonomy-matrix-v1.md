# ACE autonomy matrix — governance model for autonomous action (v1)

- **Status:** Candidate governance decision — companion to the self-improving loop note
  ([baked-in code intelligence](ambient-code-intelligence-auto-trigger-v1.md), proposed Decision 17).
  General primitive: it governs **all** autonomous action in ACE, not only the loop. Not four-record
  reconciled; not frozen. A systems-theory stability review is complete (see next block); its
  prerequisites gate any tier above A0 plus one cell.
- **Date:** 2026-08-18
- **Relates to packet Decisions:** 1 (Core/Intelligence purity), 8 (proposal-only corrections),
  10 (personal→shared promotion deferred), 12 (progressive disclosure with receipts),
  13 (ACE holds no approve/merge/promote/deploy authority over itself).

## Stability review outcome (2026-08-18)

A systems-theory gate reviewed this matrix and the loop note against the real Sentinel substrate.
Verdict: **safe to ship A0 (surface / propose-only) in full, plus exactly one A1 cell —
`embedding_reconciler`, the only action that meets the A1 contract** (deterministic, machine-checkable
verify, reversible, no semantic coupling). All other loop-driven A1 auto-heal is **held** until the
§9 prerequisites close. Two matrix claims were contradicted by the code and are corrected in place:

- **Fail-open vs. fail-closed (BLOCKER, verified).** The reused Sentinel trigger layer fails *open* —
  `scheduler.py:318` sets `should_run = True` on any trigger exception; `triggers.py` returns `True`
  on error; no fail-closed wrapper exists in the named attach points. §6.2's "fail-closed" is not yet
  a system property; a boundary override is a ship prerequisite (§6.2, §9).
- **Phantom confidence gate (BLOCKER, verified).** `edge_inference.py:101` clamps `conf = max(0.5, …)`,
  so §5's "Edge inference: A1 ≥conf, else A0" can never route to A0 (§5, §9).

## 1. Why a matrix, not a dial

Autonomy is not a global setting; it is a **property of the action**. "Reconcile an embedding index"
and "change an intelligence assertion" cannot share one autonomy level. A single dial is either too
timid (humans review index rebuilds) or too dangerous (the engine edits governed records
unattended). The matrix assigns autonomy per action, and — critically — an action's allowed autonomy
is the **minimum of two independent ceilings**:

```
effective_tier(action) = min( action_class_ceiling , scope_layer_ceiling )
```

An action gets its low ceiling from *either* being risky in kind *or* touching a foundational layer.
Neither the loop's confidence nor an action's easy reversibility can raise the ceiling the other one
sets.

## 2. Classification rubric (so cells are principled, not ad hoc)

A new action class is placed by four questions:

1. **Reversible?** Undone cleanly, with the reversal itself cheap and proven?
2. **Verifiable?** Is correctness *provable* (reconcile derived state against source) or a *judgment*
   (is this architecture better)? Provable can be autonomous; judgment never is.
3. **Blast radius / authority?** Durable governed records, permissions, external effects — or
   internal derived state only?
4. **Layer?** Core / Intelligence contract / pack / bundle / derived artifact.

## 3. Autonomy tiers

| Tier | Meaning | Who acts | Exists today as |
|---|---|---|---|
| **A0 — Surface** | Sense & report; zero mutation | nobody | notifications / drift signals |
| **A1 — Auto-heal** | Deterministic, self-verifying, fully reversible action on *derived* artifacts; auto-revert on verify-fail | ACE, no human | Sentinel reconcilers |
| **A2 — Propose → review → activate** | Durable records, semantics, judgment; proposal-only | human/governed gate activates | feedback → review → activation spine |
| **A3 — Elevated review** | High blast radius / authority / near-irreversible; stricter gate + backup + rollback + receipt | explicit owner (optionally multi-party) | migration-receipt path |
| **A-never — Fenced** | ACE approving/merging/promoting/deploying *itself* | external only, always | Decision 13 fence |

## 4. The two ceilings

**Action-class ceiling** — from the rubric. Deterministic+reversible+derived → A1; judgment or
durable-record → A2; authority/irreversible → A3.

**Scope/layer ceiling** — the layer caps autonomy regardless of how safe the action looks:

| Layer touched | Max autonomous tier | Why |
|---|---|---|
| Derived artifacts (embeddings, indexes, caches, graph projections) | **A1** | reconstructible from governed source |
| Governed durable records — append-only revision | **A1** | never rewrites history (append only) |
| Governed durable records — claim/decision/assertion change | **A2** | semantics + judgment (Decision 8) |
| Domain Pack / Solution Bundle content | **A2** | declared artifact, human-owned |
| `ace/intelligence` contracts | **A2 (additive only)** | purity; additive, backward-compatible only (Decision 1) |
| `ace/core` contracts | **A0 for the loop; changes via A3 migration** | naked-kernel purity; never auto |
| Authority / permission / personal→shared promotion | **A3** | trust boundary; promotion deferred to 1.4 (Decision 10) |
| ACE's own approve/merge/release/deploy | **A-never** | Decision 13 |

Take the more restrictive. Example: re-deriving a Brief revision is deterministic+reversible
(class → A1) and touches append-only records (layer → A1) ⇒ **A1**. Correcting a *claim* is class
A2 ⇒ **A2**, even though it touches the same records.

**Append-only ≠ reversible.** A1 requires reversibility (§3), but an append is *forward-only*: a
wrong autonomous append is visible to every reader until a superseding append lands. An append-only
action qualifies as A1 **only if** readers key on a `verify_passed` flag so an unverified append is
invisible until it clears verify (effectively ignore-until-proven). Otherwise it is A2.

## 5. The matrix (first cut)

| Action class | Touches | Tier | Gate / verify |
|---|---|---|---|
| Embedding / index / cache reconcile | derived | **A1** | provable vs. source; auto-revert |
| Edge / relationship inference refresh | derived graph | **A1** (⚠ prereq) | PREREQ: `edge_inference.py:101` clamps `conf=max(0.5,…)`, so the "else A0" branch is **inert**; until the floor is removed this cell is unconditional A1 and must meet the §7 verify/reversal contract |
| Stale-source re-ingest → append Brief revision | append-only record | **A1** (verify-gated) | append-only is forward-only, not reversible — A1 only if reader-invisible until `verify_passed` (else A2); see §4 note |
| Correct a claim / change a decision or assertion | durable records | **A2** | human review + cited proposal (Decision 8) |
| Architecture-improvement suggestion | judgment | **A2** (or **A0**) | never auto — propose only |
| `ace/intelligence` additive contract addition | Intelligence | **A2** | additive/back-compat proof + review |
| Contract / schema migration | Intelligence / Core | **A3** | backup + rollback + migration receipt |
| Authority / permission change | governance | **A3** | explicit owner |
| Personal → shared promotion | scope crossing | **A3**, deferred 1.4 | identity/provenance/receipts must survive |
| ACE self-merge / self-release | itself | **A-never** | Decision 13 |

## 6. Enforcement: the boundary reads the cell, not the loop

Two rules make the matrix trustworthy:

1. **The actor only *requests*; the trust boundary *decides*.** The matrix is **declared, versioned
   policy enforced at the boundary** — never evaluated by the loop about itself at runtime. This is
   ACE's existing pattern (the governed acquisition port owns the trust boundary); the matrix
   formalizes it for autonomous action. Attach points already exist: `ace/application/agent_governance.py`,
   `ace/application/composition_policy_admission.py`.
2. **Conservative-by-default, fail-closed.** An action whose class is unknown or ambiguous gets the
   **highest** gate, not the lowest. Misclassification is the entire attack surface, so unknown →
   A2+, never A1. The loop can be wrong about its own classification and still cannot escalate,
   because the boundary — not the loop — reads the cell.

   **⚠ Not yet true in the substrate.** The Sentinel trigger layer (`triggers.py`,
   `scheduler.py:318`) currently fails **open** on error — it fires the engine. Fail-closed is
   therefore a required *override*, not a current property: for any effective tier ≥ A1 the boundary
   MUST convert a trigger/health error to tier A0 (surface only), never "run anyway." This override
   is a ship prerequisite (§9). Fail-open is acceptable only for non-mutating A0 scanners.

## 7. Cell contract

Every cell above A0 declares, as policy:

- **gate** — who/what activates (nobody / owner / delegated-governed / multi-party);
- **verify** — the proof the action must pass before it counts as done (for A1, a machine check; for
  A2+, the review);
- **reversal** — the concrete rollback path, itself tested;
- **receipt** — the durable, cited record written (Decision 12);
- **bounds** — rate, budget, and — for any signal-driven auto-tier — the **loop-gain constant**,
  which is treated as gain: documented, bounded, and covered by the systems-theory review.

## 8. Relationship to the self-improving loop and to Sentinel

- The loop (Decision 17) is **one client** of this matrix: its `sense → diagnose → propose →
  activate → verify` stages request actions whose tier the matrix sets. The loop defines *when* it
  fires; the matrix defines *what autonomy* each resulting action may have.
- **Sentinel already operates at A1** (autonomous reconciliation of derived artifacts). This
  document makes that explicit and brings it under one governing model rather than per-engine
  convention — which matters because the loop and Sentinel are *two autonomous subsystems being
  coupled*, the classic instability trigger.

## 9. Ship prerequisites and open questions

**Ship prerequisites** — must close before any coupled A1 auto-heal beyond `embedding_reconciler`
(from the stability review; severities in parentheses):

- **Fail-closed boundary override (BLOCKER).** Convert Sentinel's fail-open trigger evaluation
  (`scheduler.py:318`, `triggers.py`) to tier-A0 on error for any tier ≥ A1.
- **Real edge-inference gate (BLOCKER).** Remove the `conf=max(0.5,…)` floor
  (`edge_inference.py:101`) so the A1/A0 threshold has authority, or reclassify edge inference as
  unconditional A1 under a real verify/reversal contract.
- **Per-change verify damper (BLOCKER).** Replace the 30-day rolling `effectiveness_recomputer`
  window as the loop's verify with a per-change, short-horizon, pre-registered delta computed from
  observations the loop **cannot itself write** (else it grades its own homework). Re-derivation must
  carry the supersession link so a `contested` claim stays contested across re-ID.
- **Attribution-keyed hysteresis + edge TTL (MAJOR).** Dedupe/cooldown on *attribution state*, not
  existence; add endpoint-invalidation/TTL to `reasoning_edge`. Together these break a ~24 h
  decay⇄repair limit cycle. Cooldown ≥ the slowest coupled engine's period (≥24 h given daily decay).
- **Shared cross-engine circuit breaker (MAJOR).** Sentinel has only a same-engine concurrency guard
  (`scheduler.py:208`). Add one boundary breaker tripping on per-class mutation-rate cap OR
  same-record-touched-by-≥2-engines-in-window OR verify-revert-rate over threshold → drop mutating
  tiers to A0. Size caps from measured steady-state mutation rate (currently unmeasured).
- **Firing hysteresis (MAJOR).** `DEFAULT_MUTATION_THRESHOLD=5` (`triggers.py`) is a bare level
  comparator with no cooldown; add separate arm/disarm thresholds + min-interval + per-cycle proposal
  budget. Declare all three as §7 loop-gain constants.

**Open questions:**

- **`conflict_detector` classification.** It autonomously sets `insight.status='contested'` via LLM
  *judgment*, which the rubric (Q2) says is never autonomous. Classify explicitly: downgrade the
  semantic status change to A2, or redefine quarantine as a non-semantic `needs_review` flag that
  does not alter retrieval trust.
- **Tier drift.** Guardrail against silent reclassification of an action from A2→A1 over time.
  Reclassification is itself an A3 policy change.
- **Multi-party A3.** Whether high-authority actions need more than one owner, and how that composes
  with the single-user product today.
- **Archived-node coverage hole.** `decay_manager` archives (`status='archived'`) are invisible to
  the active-only loader (`decay_manager.py:206`), so the loop can re-derive duplicates it cannot
  sense. Coverage/dedup concern, not a ship blocker.

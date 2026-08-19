# ACE as intelligence-builder OS — north star + Decision 14 amendment (v1)

- **Status:** Candidate north-star + governance decision. Anchors a new **Code-Intelligence-evolution
  version** (provisional 1.3-class — final number set at reconciliation, not here). Amends packet
  **Decision 14**; requires owner sign-off and four-record reconciliation before it is frozen.
- **Date:** 2026-08-18
- **Owner direction (2026-08-18):** every ACE core instance builds/bakes in the full stack including
  Code Intelligence; ACE is an end-to-end harness *and* intelligence system — a full intelligence-
  builder OS. The coding graph must be **smart, functional, and stable** before it is baked in and
  auto-surfaced.
- **Companion notes:** [ambient trigger + self-improving loop](ambient-code-intelligence-auto-trigger-v1.md),
  [autonomy matrix](ace-autonomy-matrix-v1.md).

## 1. North star

**ACE is the full-stack intelligence-builder OS.** Not a minimal kernel you assemble from optional
packs, but a complete intelligence OS that is already assembled: point it at a source — notes, a
repository, a dataset — and it builds governed, cited intelligence out of the box, keeps it current,
and improves itself under governance. Every instance ships the full stack, Code Intelligence
included.

This is a product-identity commitment, and it resolves the adoption problem structurally: capability
that is optional is under-adopted (the PI8/arm-C zero-call finding); capability that is baked in and
ambiently offered is used.

## 2. Decision 14 — amendment

**From** (frozen 1.2 wording): *"Code Intelligence composes; it is not embedded in Core and not
required… a composable System capability any bundle or Topic may co-activate… while remaining a
standalone Solution Bundle for use on non-ACE products. One pack, many compositions — no
embedded/standalone fork."*

**To** (proposed): **Code Intelligence is baked into every ACE instance as part of the full stack.**
There is exactly **one implementation** (no fork). It is **present in every instance and ambiently
offered**, and **gated** so it activates only where it has substrate (a repository/graph in scope).
"Standalone" survives **only as a deployment configuration** — the same bundle deployed alone for a
non-ACE consumer — never as a separate product or codebase. `ace/core` stays pure (Decision 1): baked
into the *instance* is not embedded in the *kernel*.

**What does not change:** the "one pack, no fork" principle (strengthened), the non-ACE standalone
deployment path (preserved as packaging), and kernel purity. **What changes:** the default — present-
and-offered everywhere instead of opt-in; and the realization target — full baked-in-and-active Code
Intelligence is delivered by the new version, not 1.2.

## 3. "Baked in" defined precisely — present-and-gated, not forced

Baking the full stack into every instance must not mean every subsystem runs hot everywhere. That
would be waste (a personal-notes user with no repo gains nothing from forced code indexing), would
bake in immaturity (the coding graph is deliberately incomplete — it "shows exact resource lineage
and explicit gaps, never a fabricated knowledge graph", `EntityIntelligence.tsx:409`), and would bake
in instability (the autonomous substrate fails open and can oscillate — see the autonomy matrix
stability review).

The resolution is the gate + autonomy matrix already designed:

- **Present in every instance's capability surface**, ambiently offered.
- **Gated** — activates only where it has substrate; dormant otherwise (a personal user with no repo
  sees code intelligence present but idle).
- **Tiered** — the autonomy matrix caps what it may do; fail-closed, cited, honest about its gaps.
- **Kernel preserved** — `ace/core` stays pure and **still boots alone as a CI-tested configuration**,
  so the minimal core does not rot even though the default distribution is the full OS.

## 4. New version scope — two workstreams

**Workstream A — Adoption (make it get used).** The A0 ambient trigger over the Code Intelligence
engine: gated runtime middleware that queries the code-intel surface on relevant events and injects
grounded, cited context — or an honest no-answer — into the builder's turn, without the agent having
to call a tool. Fixes the arm-C non-adoption; unblocks the PI12 measurement. **This is the first
slice to build and ship.**

**Workstream B — The coding graph: smart, functional, stable.** Surfacing a graph everywhere is only
safe if the graph is trustworthy. This workstream owns: *functional* (the build → query path works
end to end), *smart* (closing the "still required from architecture" gaps — typed semantic
relationships, first-class event projections, authoritative conflict/uncertainty coverage), and
*stable* (the Sentinel-coupling and fail-open prerequisites from the autonomy-matrix review). A0's
fail-closed/cited discipline means it is safe to surface an *incomplete* graph — as long as the graph
is *honest and stable* — so A and B proceed in parallel, with B's stability prerequisites gating any
auto-*action* (as opposed to auto-*surfacing*).

**Governance spine.** The self-improving loop and the autonomy matrix (companion notes) are this
version's governance spine, sequenced behind their stability prerequisites; initial envelope stays
A0 / propose-only plus the one cleared A1 cell.

## 5. What stays in 1.2 — on rails

1.2 Personal Intelligence ships unchanged as the **first concrete proof** of the OS thesis at small,
safe scope: point ACE at your notes → cited Brief → correction → continuity → export/deletion. For
personal users, Code Intelligence is present but **gated dormant** (no repo, nothing to index).
Decision 14's operative 1.2 content — code intelligence not required for J1–J10 — holds; the
amendment is a forward statement realized in the new version, not a 1.2 re-scope.

## 6. Sequencing and the discipline

1. Record this north star + Decision 14 amendment (this doc).
2. Keep 1.2 on rails; ship it as proof #1.
3. Build **one** slice next — the A0 code-intel ambient trigger — and ship it before starting another.
4. In parallel, assess and harden the coding graph (Workstream B): functional, smart, stable.
5. The self-improving loop + full baked-in-active Code Intelligence land across the new version behind
   the stability prerequisites.

The failure mode to avoid is grandeur without shipping. "Build it all" is the sequenced roadmap above,
not one undivided push — each slice ships before the next begins.

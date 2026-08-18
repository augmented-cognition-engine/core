# ACE Intelligence OS deferred kernel subsystems

Status: **planning catalog only.** This document schedules no work, declares no outcomes or
gates, and makes no capability claims. It records kernel-scale subsystems that the Intelligence
OS direction implies but no current release plans, so that scheduled 1.x work preserves the seams
a later implementation needs. Per the roadmap guardrails, nothing here grants architecture,
merge, or activation authority.

## Purpose and origin

An operating system framing runs through the roadmap: 0.8.0 shipped the Intelligence OS
realignment and resource plane, 1.0 is the Personal Intelligence Operating System, and the
roadmap carries an explicit Intelligence Operating System architecture sequence. Read against
that framing, ACE today has a process model (agent shells composed, dispatched, and dissolved), a
filesystem (the Living Product Graph and State Engine), a security model (authority, activations,
receipts), and — unusually for the metaphor — a governed loop by which running work makes the
substrate smarter.

Auditing the metaphor against the codebase (2026-08-17) surfaced five subsystems a mature
operating system has that ACE has only partially, plus a ranking of which are hostile to
retrofit. Each entry below states what exists (verified against `origin/main`), what is missing,
which scheduled lane owns the nearest work, and the seam current work must not pave over.

This catalog is the kernel-infrastructure counterpart to the positioning claim tested by the
ACE-Builds-ACE three-arm harness (`docs/design/ace-builds-ace-harness-v1.md`): durable substrate,
not model scale, is the compounding asset. The subsystems here are what let that substrate stay
trustworthy as concurrency, tenancy, and autonomy grow.

## 1. Execution governor — arbitration of inference spend under scarcity

**Not the 0.8 resource plane.** The unified Intelligence resource plane
(`docs/design/intelligence-resource-plane-v0.8.0-work-packet-v1.md`) is a governed *read model*
over Intelligence resource nouns. This gap concerns compute arbitration: tokens, wall-clock, and
provider rate limits as the scarce resources every running agent, sentinel engine, and
deliberation competes for.

**What exists.** Per-call and per-component limits are declared where each caller lives
(`core/engine/core/config.py` and call sites); orchestration assigns work and file ownership
before execution (`core/engine/orchestration/airspace.py`, `dispatch_planner.py`) but does not
meter spend; the sentinel fleet (30+ background engines under `core/engine/sentinel/engines/`)
runs on schedules with no shared budget. The PI12 harness pins per-arm token and wall-clock
budgets, proving budgets are already the native cost vocabulary.

**The gap.** No single component can answer "what is everything running costing right now, and
what gets throttled first?" There is no global accounting, no priority or fairness policy between
foreground work and background maintenance, and no backpressure. This is cooperative
multitasking: each process brings its own rationing. The classic failure mode is priority
inversion — background daemons starving the foreground work the user is watching.

**Nearest scheduled lane.** 1.6 Governed Self-Improving Agents. Autonomous
proposal/evaluation/rollout loops multiply background inference spend; 1.6 should not ship
without at least a shared ledger of spend by principal-and-purpose, even if arbitration policy
comes later.

**Seam to preserve.** Route new inference calls through the existing provider runtime seam
(`core/engine/core/provider_runtime.py`) rather than adding direct provider calls, so a governor
can later interpose at one choke point. Express budgets in tokens and wall-clock with currency as
labeled accounting only, as the PI12 harness already does.

## 2. Context working-set management — virtual memory for running cognition

**What exists.** Recall and context planning are owned by the Agent Memory roadmap
(`docs/design/agent-memory-roadmap.md`, AM3 Recall and Context Planner; AM4 lifecycle and
retention). The 0.8C resource plane already projects **Context Manifests** and **Memory Use** as
first-class resource families — the accounting nouns for "what was resident when this was
produced" exist and are receipt-linked.

**The gap.** AM3 plans context *at composition time*: what to recall before work starts. A
working-set manager operates *during* the life of a running process: paging knowledge in on
demand (the page-fault analogue of retrieval), evicting by policy as the context window fills,
sharing hot read-only knowledge across concurrent agents, and emitting the Context Manifest as a
byproduct of management rather than a separate report. Today, context degradation mid-session
(compaction, truncation) is handled ad hoc by each harness, and what an agent lost at compaction
is not accounted anywhere.

**Nearest scheduled lane.** AM3/AM4 in the Agent Memory roadmap; the Context Manifest and Memory
Use families in the resource plane.

**Seam to preserve.** Whatever AM3 ships, keep the manifest of resident context an *input-output
contract of the runtime*, not a courtesy log — the working-set manager's correctness will be
audited through exactly that record. Avoid letting individual shells own bespoke
compaction-survival logic that the kernel cannot observe.

## 3. Unified boundary enforcement — making ring 0 a checked property

**What exists.** Two real guards, independently grown:
`tests/intelligence/test_contract_boundaries.py` pins exactly which modules
`ace/intelligence/__init__.py` may import and deliberately excludes `ace.intelligence.packs`
(it has rejected over-broad patches in practice); `tests/test_kernel_boundary.py` protects the
kernel seam. The architecture document distinguishes **verified** statements from **direction**
statements — the honest vocabulary this gap closes.

**The gap.** The dependency-direction rules (contracts and services never depend on hosts; Core
never imports an extension package; effects always traverse authority and produce receipts) are
mostly *direction*: enforced by review and convention, checked by two partial mechanisms. An
operating system's security model is real only when unprivileged code physically cannot cause an
effect without kernel mediation. The falsifiable test: can any shell, engine, or extension reach
an adapter and cause an effect without traversing authority? Anywhere the answer is yes, the ring
boundary is convention, not architecture.

**Nearest work.** A unification of the two existing guards into one import-boundary enforcement
story, extended to the effect/authority choke point, is under consideration in a parallel session
(not scheduled, not owned by this document). The requirement recorded here: **one** mechanism,
extending the existing guards, not a third parallel checker.

**Seam to preserve.** Do not add new host→service or service→adapter imports that the current
guards would miss; when in doubt, route through the registry/contract facade the guards already
model.

## 4. Multi-principal read paths — tenancy as a preserved seam, not a 1.x feature

**What exists.** Single-user is the deliberate 1.0 scope (Personal Intelligence Operating
System), and 2.0 Collaborative Organizational Intelligence is where multiple principals arrive.
The resource plane C1 contract is already principal-aware: every page preserves the exact
authenticated principal, product, grant, and authority-use receipt, and readers fail closed on
boundary widening. Organization Overlays exist as declarative data.

**The gap.** Principal-awareness stops at the resource-plane boundary. Graph reads, belief
retrieval, recall, and search below that plane do not ask "may *this* principal see *this*
node/belief?" — correctly, for a single-user product. But per-principal visibility is the classic
retrofit-hostile subsystem: it touches every read path, and adding it late means auditing every
query in the codebase.

**Nearest scheduled lane.** 2.0. Nothing in 1.x should build it.

**Seam to preserve.** Keep all durable reads flowing through the small number of retrieval
facades that exist today (graph context, grounded-state retrieval, search) rather than letting
new features query stores directly. The facades are where visibility predicates will one day
attach; every direct store query created now is a future audit item. Product-scoped identity
(already universal in Core) is the anchor tenancy will hang from — never bypass it.

## 5. Cross-store crash consistency — journaling above the single-write level

**What exists.** The capture write path is genuinely atomic at the single-substrate level:
`core/engine/capture/atomic_write.py` folds what were three fire-and-forget writes plus an
embedding write into one SurrealDB transaction, with embedding backfill
(`core/engine/sentinel/engines/embedding_reconciler.py`) as the single retained best-effort
component. Reconciler engines (`provenance_reconciler.py` and peers) repair drift after the
fact, fsck-style. Belief changes deploy through staged promotion/rollout/transition contracts
(`core/engine/grounded_state/`). 1.3 owns backup, rollback, migration receipts, and recovery.

**The gap.** Atomicity ends at one store's transaction boundary. A multi-step transition that
spans stores — graph edge plus belief plus receipt, SurrealDB plus vector index plus a JSONL
ledger — has no write-ahead intent record; a crash mid-sequence leaves the compensating
reconcilers, not a journal, holding correctness. "Eventually reconciled" is acceptable for
derived data (embeddings, provenance backfill) and not acceptable for authority-bearing state
(receipts, activations, promotions), whose consumers assume it is never inconsistent.

**Nearest scheduled lane.** 1.3 Intelligence Operations and Safe Evolution — recovery and
migration receipts are journaling's product face.

**Seam to preserve.** Classify each store write as *authoritative* or *derived* at the seam where
it happens (the atomic capture write already models this split). New multi-store sequences should
name their authoritative write first and treat everything after it as reconcilable; that
discipline is what a later intent journal can be slotted under without rewriting call sites.

## Retrofit-hostility ranking

| Subsystem | Defer cost | Why |
|---|---|---|
| Multi-principal read paths | **Highest** | Touches every read path; late addition means whole-codebase query audit |
| Cross-store journaling | High | Every unclassified multi-store write site added now is a future migration item |
| Execution governor | Medium | Interposable later *if* calls stay behind the provider runtime seam |
| Boundary enforcement | Medium | Cheap to add, but every convention-only month accretes violations to unwind |
| Context working-set manager | Lower | Composes over AM3/AM4 contracts if manifests stay first-class |

## Reconciliation rule

If a release plans work that closes or reshapes any entry above, amend this catalog in the same
change, or state in the release packet why the entry stands. An entry closed by evidence moves to
the roadmap's outcome ledger vocabulary (`passed` with its evidence link), not to silent
deletion.

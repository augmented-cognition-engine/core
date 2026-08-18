# ACE 1.2 Personal Intelligence work packet v1

- Date: 2026-08-17
- Public contract: [issue #195 — Roadmap: ACE 1.2 — Personal Intelligence](https://github.com/augmented-cognition-engine/core/issues/195)
- Baseline: `origin/main` commit `eab2aa211fbee18d8aa1b828522830e3d9b95396` — published `ace-core` 1.1.0,
  schema head v179, exactly eleven public MCP tools, ACE 1.1 Code Intelligence closed and reconciled
- Packet status: **frozen for owner review; PI2–PI5 merged** (amendment 2026-08-17: decisions
  15–16, the issue #199 dependency debt in §3, and the PI12 harness-freeze prerequisite added for
  owner review; decision 16 extended same-day with intelligence-curve capture — retrieval
  shortcuts, per-slice points, prior-slice provenance, retrospective labeling. No previously
  frozen scope was narrowed)
- Predecessor rule: ACE 1.1 is closed and immutable. An urgent defect ships as a narrowly scoped
  1.1.x patch under the published promise; it never reopens 1.1 scope or borrows 1.2 scope. Normal
  development proceeds on this packet.

## 1. Outcome

A person connects their own authorized, read-only local knowledge — a Markdown/Obsidian folder,
PDF, CSV, and JSON files — and receives a cited first Brief about what currently matters in it.
When a source changes, ACE produces an append-only "what changed and why" revision. The person asks
grounded questions and gets cited answers or an honest no-answer, corrects a wrong answer through a
governed proposal, restarts without losing anything, and can export or delete their owned
intelligence through the supported ownership journey.

The deliverable is the first-party **Personal Intelligence Solution Bundle** over the unchanged ACE
substrate. Personal meaning arrives through selected packs and overlays; the bundle binds exact
versions of independently released local-source adapters. Nothing personal enters Core ontology.

## 2. Frozen public acceptance journey

From public artifacts only, on a clean machine, a user who is not an ACE maintainer completes:

| Step | Journey requirement | Fails closed on |
|---|---|---|
| J1 — Install | Install the public bundle and its pinned adapters; on a genuinely unconfigured host answer one question — Personal, Shared server, or Dedicated appliance — with Personal the 1.2 journey path; configured or administrator-fixed hosts bypass the prompt; launch Atrium with honest, nonblocking runtime-readiness states | source checkout required; unpinned adapter resolution; blocking on model download; fabricated readiness |
| J2 — Choose | Choose Personal Intelligence beside the existing catalog entries | Personal branch or noun inside Core/Intelligence |
| J3 — Connect | Authorize one local Markdown/Obsidian folder plus PDF, CSV, and JSON files; exact folder scope, read-only access mode, and expected contribution shown before any read | any read before approval; write access requested; credential capture |
| J4 — Inventory | Atrium shows per-source inventory, permission, readiness, processing, freshness, health, partial coverage, retry, and failure states | source shown healthy on mere presence; hidden partial coverage |
| J5 — First Brief | A cited first Brief over the personal corpus; every material claim cites an exact source locator or is explicit inference with stated uncertainty | uncited material claim; citation that does not resolve to its span; unused citation |
| J6 — Change | Edit one source file; ACE detects the change and produces an append-only revision stating what changed and why, with a semantic diff from the prior Brief; the prior revision remains readable | history rewrite; silent re-synthesis; undetected change without a degraded/pending state |
| J7 — Ask | Ask ACE answers from the authorized personal corpus with claim-level citations, or returns an honest no-answer naming what is missing | unauthorized retrieval; generic uncited answer; fabricated coverage |
| J8 — Correct | Correct one wrong answer; the correction binds to the exact claim and citation identities, is attributable, and produces a governed re-derivation proposal — never a silent mutation | silent reweighting; correction lost after restart |
| J9 — Restart | Stop and restart the runtime; sources, Briefs, revisions, corrections, and receipts reopen with identical identities | re-ingestion required; identity drift; lost correction |
| J10 — Own | Export owned intelligence with checksums; preview deletion with exact counts and disclosed exclusions; confirm deletion; deleted derived intelligence does not reappear | partial deletion presented as complete; export omitting records silently; deletion preview hiding surviving derived artifacts |

The journey passes only when executed end to end in one session by a clean user from public
artifacts, with the evidence record listing every deviation, intervention, and known limitation.

ACE 1.2 carries a second acceptance track: the `ACE Builds ACE` reference program (decision 13,
PI12), whose evidence is required for release closeout but whose comparative result — better,
worse, or mixed — is reported honestly and does not gate J1–J10.

## 3. Entry conditions and 1.1 carryovers

The 1.2 freeze audit (roadmap files plus GitHub records, 2026-08-17) found the following. The full
item-by-item register lives in the companion
[ACE 1.1 carryover disposition register v1](ace-1.1-carryover-disposition-register-v1.md); PI1
turns it into issue updates.

**Record-keeping debts PI1 must clear before any 1.2 code lands:**

- Issue #194 was closed by PR #205 with no closeout comment. The required final disposition — tag,
  run, digests, evidence link, and explicit deferral dispositions for the World-to-Code
  demonstration, improvement loops, and concurrent-work reconciliation — must be recorded on the
  issue, including the owner decision (2026-08-17) that the `ACE Builds ACE` reference program is
  re-scoped from the 1.1 narrative into ACE 1.2 (see decision 13 and PI12).
- `ROADMAP.md` line 248 and `README.md` line 148 promise "cloud drives, databases, warehouses, and
  object stores" for 1.2, contradicting issue #195 and `ROADMAP.md` §1.2 (local-only first). The
  issue is the canonical contract; the table row and README get corrected.
- `ROADMAP.md` §1.2 says adapters are not "part of the Personal Solution Bundle", while
  `MANIFESTO.md` defines a Solution Bundle as linking adapters. Reword to the shared meaning: the
  bundle **binds exact adapter versions** without owning adapter implementations.
- Stale status lines corrected or re-dated: `docs/extension-invocation-contract.md` ("E1 remains
  not ready" vs E1 passed), `docs/capability-maturity.md` 1.0-line/0.3.x fragments,
  `docs/README.md` "active 1.1 milestone", the `agent-memory-roadmap.md` AM1 status header, and
  `ROADMAP.md`'s "complete by 1.0.0" target for continuous situational intelligence.
- Issue #199 (ACE 1.6) declares its dependency as issue #198 (ACE 1.5). Its substantive
  prerequisites are the 1.3 operations substrate — run event spine, matched evaluation, rollback —
  plus the experience corpus PI12 begins capturing under decision 16; the organizational scope of
  #198 is not required for a workspace-of-one proof and contradicts the scale-invariant rule that
  every capability proves first in a minimally administered scope. PI1 records the corrected
  dependency (#196, with #198 required only for organizational extension) on issue #199.

**Hard preconditions inherited by 1.2:**

- **Adapter compatibility envelope.** The only published first-party adapter pins
  `ace-core>=0.8.0,<1.2`; releasing Core 1.2.0 breaks it. A new adapter distribution with a widened
  envelope ships before or with the 1.2 release (PI2/PI11).
- **Issue #49 F3 (atomic mutable registration).** F3 containment was accepted on the argument that
  the extension surface does not expand. PI10's bundle/adapter activation expands exactly that
  surface, so F3's staged, atomic, ceiling-enforced registration work — or an explicit re-argued
  containment — is a prerequisite for PI10, not an optional patch. F4 and F7 remain ordinary 1.1.x
  patches.
- **SI1 bounded slice.** Issue #47's SI1 owns the as-of orientation, append-only revision, and
  no-future-leakage contract that J6 requires. 1.2 implements a bounded personal slice of those SI1
  controls (as-of isolation, append-only revision, leakage refusal for personal Briefs) and says so
  on issue #47; it does not claim SI1's two-external-pack gate.
- **Source Health.** The 0.8C record leaves Source Health "explicitly unsupported" and the 1.1
  journey has no watcher. J4/J6 make Source Health and change detection supported claims for local
  sources; PI6/PI7 must lift that recorded limitation explicitly rather than around it.
- **Atrium UX worktree carryover.** The frozen, never-merged Atrium UX contributor packet
  (2026-08-16: host first-run candidate with Personal / Shared server / Dedicated appliance modes,
  bypass behavior, honest readiness states, accessibility and responsive closure, 424/424 Canvas
  tests) targeted the now-closed 1.1 candidate. 1.2 adopts the Personal-mode first-run experience
  into J1/PI6 under the packet's seven control-tower contract assumptions (canonical host
  projection, durable owned mode persistence, admin-fixed immutability, local-only default,
  independent readiness truths, Settings changeability, appliance conversion separate). The design
  docs and candidate component must land in the repository before the worktree is cleaned up.
  Shared-server remote exposure and appliance conversion stay 1.7; the resumable model-download
  service may defer to 1.3 because the readiness lane is nonblocking by design.

## 4. Canonical decisions

1. **Bundle, not ontology.** Personal Intelligence is a Solution Bundle composing packs, overlays,
   adapters, Atrium modules, and policy. `ace/core` and `ace/intelligence` gain no Personal noun,
   table, or branch.
2. **Local read-only first.** Exactly four source kinds: Markdown/Obsidian folder, PDF, CSV, JSON.
   The Obsidian adapter is the Markdown-folder adapter with declared vault conventions (frontmatter,
   wikilinks, attachments) as adapter capabilities, not a separate ontology. At most one remote
   knowledge source (for example Notion or OneDrive) may follow **only after** the local journey
   passes; it is outside this packet.
3. **Adapters are independent artifacts.** Each adapter is separately versioned with its own
   manifest, permissions, conformance, health, and failure semantics. The bundle consumes exact
   version bindings. No universal connector catalog is promised, and adapter availability never
   defines Personal Intelligence.
4. **Local acquisition is its own labeled mode.** Local authorized file reads are admitted under an
   explicit local acquisition mode with canonical content digests, starting from the existing
   recorded-source admission boundary (`ace/application/recorded_source_admission.py`) rather than a
   new ingress path. They are never presented as live HTTPS captures and never hidden inside
   unlabeled recorded material. Briefs disclose the mode of every citation. The public mode
   documentation (`docs/intelligence-os.md` documents only PREPARED and LIVE today) is corrected to
   name every supported mode.
5. **Citations resolve to spans.** The citation locator gains a documented grammar for local
   sources: workspace-relative path plus a stable anchor — heading path for Markdown, page for PDF,
   row range for CSV, JSON Pointer for JSON — so every citation resolves to an exact span.
6. **Documents map as typed structure, not flattened prose.** A document mapping contract joins the
   existing JSON Pointer mapping: sections, headings, rows, and records become typed observations
   with provenance and source policy. CSV and JSON reuse the JSON Pointer path.
7. **Ask ACE is a governed service.** Answers are assembled server-side as grounded claims with
   citations under the ordinary authorization, budget, and receipt path. An honest no-answer names
   the missing coverage. The existing client-side ranker is not the acceptance surface.
8. **Corrections bind to answers.** A correction references exact claim and citation identities and
   yields a governed re-derivation proposal. Approval and activation remain human; historical
   evidence and prior Briefs are never mutated.
9. **Deletion is truthful about depth.** The ownership deletion journey covers, or explicitly
   enumerates as surviving, every derived artifact of bundle sources — embeddings, graph rows,
   caches, and indexes included. A preview may disclose exclusions; it may not hide them.
10. **Topics stay bounded but scale-invariant.** The 1.2 Topic experience is the person's named
    bounded question rendered in Atrium over Builder sessions. Per the scale-invariant product
    architecture, its durable records are private by default and share-ready by construction —
    identity, provenance, and receipt semantics must survive a later personal-to-shared promotion
    unchanged — but promotion UX and the full Topic pack grammar remain ACE 1.4; this packet must
    not preempt them.
11. **The public MCP surface stays at eleven tools.** The journey ships through HTTP, CLI, and
    Atrium. Any MCP projection is additive inside existing tools; a twelfth tool requires its own
    later decision.
12. **Progressive disclosure with receipts.** The roadmap ledger assigns progressive capability and
    context disclosure to 1.2: the personal journey starts from a compact authorized index and
    loads full source material only when a stage needs it, recording selection, omission, and
    material-use evidence. Deferred loading never hides active policy, authority, omissions, or
    provenance.
13. **ACE builds ACE 1.2.** By owner decision (2026-08-17), the `ACE Builds ACE` matched reference
    program carried over from the 1.1 narrative is executed inside this milestone, with bounded
    1.2 implementation work as its subject: real frozen packet Decisions are implemented through
    the shipped 1.1 Code Intelligence journey and compared, under equivalent tools, task, and
    authority, against coding-agent-only baselines across the decision 15 model-tier ladder — a
    like-for-like bare run on the same mid-tier model and a bare top-tier reference run, so the
    program tests both within-tier lift and the tier-jump claim. The program uses shipped 1.1 capabilities only —
    it pulls no unreleased Code Intelligence expansion into 1.2 — and grants ACE no approval,
    merge, release, deploy, or promotion authority over itself. Its evidence ships with the 1.2
    release; an honest negative or mixed result is a valid outcome and does not block the J1–J10
    gate. Within the program, "linked repair" means the frozen 1.1 contract objects only: ACE
    records the propagation finding, the governing Decision, and the bounded repair lineage, while
    a human or the coding-agent participant performs the repair itself under ordinary review.
    Active ACE-executed linked repair remains ACE 1.3 scope and is not pulled forward by this
    program.
14. **Code Intelligence composes; it is not embedded in Core and not required.** By owner
    direction (2026-08-17), Code Intelligence is treated as a composable System capability any
    bundle or Topic may co-activate over the shared graph, while remaining a standalone Solution
    Bundle for use on non-ACE products. One pack, many compositions — no embedded/standalone fork.
    PI12 exercises the composition concretely: its Topics co-activate the released 1.1 Code
    Intelligence bundle beside the Personal bundle over one workspace, where the 1.2 packet
    documents are Personal sources and the 1.2 implementation is the repository. Personal
    Intelligence must never *require* Code Intelligence for its J1–J10 journey, and typed
    cross-pack relation grammar beyond what 1.1 shipped remains ACE 1.5.
15. **The PI12 comparison harness is preregistered.** The baseline comparison is measured by a
    versioned harness frozen before the first subject Decision run, following the L1 v7 rule that
    controls freeze before collection. The harness pins the coding agent and its exact version,
    the model-tier ladder, the tool allowlist, workspace and repository heads, token/time budgets, the
    metric definitions from the PI12 report list, subject-Decision eligibility, and the analysis
    rules for declaring better, worse, or mixed. A run collected before the harness freeze, or
    under a drifted configuration, is reported as exploratory and excluded from the comparative
    result. The frozen harness configuration and its digest are bound into the `ACE Builds ACE`
    evidence record.
16. **PI12 experience is captured for ACE 1.6, proposal-only.** Before PI12's first subject run,
    the minimal experience-capture record shape is frozen so every preserved improvement proposal
    binds the exact subject Decision, run and participant identities, Context Manifests,
    corrections, failures, rework, verification results, costs, and later Outcome linkage that
    ACE 1.6 requires for matched evaluation. Capture is append-only and proposal-only: nothing in
    1.2 evaluates, approves, activates, or retires such a proposal, and a justified no-learning
    result is a valid capture. The shape additionally serves the intelligence-curve evidence
    outcome: each subject contributes a per-slice comparison point carrying retrieval-shortcut
    events and provenance links to earlier-slice material use, so the program yields a time
    series, not only a closeout verdict. Slices merged before the freeze may be annotated only as
    clearly-labeled retrospective records excluded from the preregistered comparative result;
    silent backfill is not an available action.

## 5. Reuse map (already on the 1.1.0 baseline)

| Journey need | Existing capability | Pointer |
|---|---|---|
| Cited Brief with fail-closed claim grounding | `BriefV1Alpha1`, `CitationV1Alpha1`, `GroundedClaimV1Alpha1` validators | `ace/intelligence/contracts/resources.py` |
| First Brief creation | `CoreIntelligenceBuildFirstBriefService` | `ace/application/intelligence_build_first_brief.py` |
| Connect/map/watch state machine, resume, block reasons | `IntelligenceBuilderSessionService`, `ConnectionAgent` | `ace/application/intelligence_builder.py` |
| Source readiness, permission, freshness, health vocabulary | system projection contracts and `_source_health()` | `ace/intelligence/contracts/system_projection.py`, `ace/application/intelligence_system_projection.py` |
| Append-only revisions, supersession impact, semantic diff | `LineageRelation.SUPERSEDES`, supersession projection, immutable-record ledger | `ace/intelligence/supersession.py`, `core/schema/v174_immutable_record_ledger.surql` |
| Shift detection engines (numeric, categorical) | detection modules producing `ShiftV1Alpha1` | `ace/intelligence/detection/` |
| Correction admission, proposal-only feedback | resource feedback contracts and service | `ace/intelligence/contracts/resource_feedback.py`, `core/engine/core/intelligence_resource_feedback.py` |
| Restart continuity and replay | Builder/Brief/ledger/ingress replay, durable host composer, restart fixture | `ace/application/*`, `ace/testing/watch_brief.py` |
| Export, delete preview, delete confirm | Personal ownership contracts, service, HTTP, CLI | `ace/core/personal_intelligence_ownership.py`, `core/engine/cli/commands/ownership.py` |
| Pack manifest, compiler, activation, conformance | Domain Pack machinery and published JSON Schemas | `ace/intelligence/packs/`, `ace/intelligence/schemas/` |

These are the substrate. The packet reuses them unchanged wherever the contract already fits.

## 6. Build map and release slices

| Slice | Required result | Primary owner |
|---|---|---|
| PI1 — packet, contract, and record freeze | This packet reconciled with issue #195, `ROADMAP.md`, `README.md`, and the Project; the §3 record-keeping debts cleared (issue #194 closeout comment, roadmap/README scope correction, stale-doc corrections); carryover dispositions recorded on issues #194, #47, and #49; sub-issues opened per slice | Core |
| PI2 — local source adapter family | Independently versioned read-only adapters for Markdown/Obsidian folder, PDF, CSV, JSON: folder walking, parsing, canonical digests, bounded samples, declared permissions, conformance fixtures; the reference workspace-action adapter re-released with a widened `ace-core` envelope | Adapter lane |
| PI3 — local acquisition admission | Explicit local acquisition mode through governed ingress; no `file://` masquerading as HTTPS; per-file provenance and content digests; Brief citation validators accept and disclose the mode | Core + Intelligence |
| PI4 — document mapping and locator grammar | Typed document/section mapping contract; citation locator grammar for path + heading/page/row/pointer anchors resolving to exact spans | Intelligence |
| PI5 — Personal pack and overlays | Declarative pack(s) and overlay templates modeling notes, documents, concepts, people, projects, decisions, commitments, relationships, revisions, provenance, and source policy through the existing pack compiler; conformance fixtures; zero Personal nouns in Core or Intelligence | Pack lane |
| PI6 — install and inventory experience | Production mounting of the frozen host first-run candidate for the Personal path: canonical host projection, durable mode persistence, Settings mutation, detection wiring, browser tests against real APIs; Atrium renders J4's inventory, permission, readiness, processing, freshness, health, partial coverage, retry, and failure states for local sources from the existing projection vocabulary | Application + Atrium |
| PI7 — change detection and revision | Content-digest change detection wired from a file watcher through re-ingest to a document-shaped Shift; append-only Brief revision with a user-readable "what changed and why" and semantic diff; explicitly lifts the recorded 0.8C "Source Health remains unsupported" limitation for local sources; implements the bounded SI1 slice (as-of isolation, no future leakage) | Application + Intelligence |
| PI8 — grounded Ask and correction | Server-side Ask service returning grounded claims with citations and honest no-answer; corrections bound to claim/citation identities producing governed re-derivation proposals | Application + Core |
| PI9 — ownership depth | Export and deletion truthfully covering bundle-derived artifacts; restart continuity across the whole journey; write-quiescence during confirmed deletion documented or implemented | Core |
| PI10 — Solution Bundle machinery | Bundle manifest with exact pack, overlay, adapter, Atrium-module, and policy bindings; preview before activation; deterministic resolution receipt; atomic activate/deactivate; the Personal and Code Intelligence bundles co-install and co-activate on one workspace without conflict, leakage, or either requiring the other | Core + Application |
| PI11 — public release proof | Clean-machine public-artifact run of J1–J10 by a clean user; evidence record; four-record release reconciliation | Core |
| PI12 — `ACE Builds ACE` reference program | The preregistered comparison harness of decision 15 and the experience-capture record shape of decision 16 frozen, versioned, and digest-bound **before** the first subject run; then at least two bounded PI-slice Decisions implemented through the shipped 1.1 Code Intelligence journey with ≥2 concurrent participants, ≥1 stale-context event, propagation verification, linked repair (recorded against the frozen 1.1 contracts with human or coding-agent execution per decision 13) or explicit complete coverage, and architecture-opportunity review or justified no-opportunity; compared through the frozen harness against coding-agent-only baselines across the decision 15 model-tier ladder (bare mid-tier floor, bare top-tier reference) under equivalent tools, task, and authority; reports orientation time, context, coverage, unsupported claims, acceptance criteria, review findings, rework, verification, latency, tokens, cost, failures, degraded states, and later material use; proves ACE cannot approve, merge, release, deploy, or promote itself | Core |

Sequencing: PI1 clears the record debts first; PI2–PI5 unblock J3/J5; PI6–PI7 unblock J4/J6; PI8
unblocks J7/J8; PI9 unblocks J9/J10; PI10 packages (gated on issue #49 F3 per §3); PI11 proves.
PI12 runs *through* the other slices — it selects its subject Decisions from PI2–PI10 work and
closes after its comparison evidence is complete. Because PI2–PI5 are already merged, PI12's
eligible preregistered subjects are the remaining PI6–PI10 slices; the decision 15 harness and
decision 16 capture shape must therefore freeze before the next slice implementation begins, or
those subjects too are spent as unpreregistered runs. PI2–PI5 may be annotated retrospectively
under decision 16's labeling rule only. Slices may land in parallel where contracts are frozen
first.

## 7. Explicitly out of scope

- Any remote or cloud knowledge source, including the "one remote source" successor step.
- A Personal ontology, table, or branch in `ace/core` or `ace/intelligence`.
- A raw transcript warehouse, silent persona inference, or any requirement to upload private
  material off the machine.
- A universal adapter catalog or any promise over Notion, OneDrive, Snowflake, or cloud services.
- Collaboration, sharing, invitations, organizations, tenancy, and managed hosting.
- The ACE 1.4 Topic pack grammar and Pack Kit.
- A twelfth public MCP tool or any change to the eleven-tool contract.
- Write access to any connected source. All 1.2 sources are read-only.
- Hostile-adapter isolation claims. Bundle adapters are trusted, separately installed artifacts
  with declared permissions, matching the 1.1 trust model.
- A restore/import service for the export artifact, backup enumeration/purge, and new
  backup/rollback/recovery UX — ACE 1.3 scope. J9 restart continuity and J10 export reuse the
  released 1.0 backup/restore and ownership claims without extending them.
- The public Adapter Kit and open adapter contract — ACE 1.4 scope. 1.2 consumes first-party
  adapters through exact bindings without publishing a kit.
- The SI1–SI4 general acceptance gate (two materially different external packs). 1.2 ships only
  the bounded personal SI1 slice declared in §3.

## 8. Evidence plan and closeout

- Each slice lands with its own conformance or acceptance evidence under `docs/evidence/`,
  following the 1.1 naming pattern (`personal-intelligence-*-v1.md`).
- The J1–J10 journey produces one public acceptance record
  (`docs/evidence/personal-intelligence-v1.2-public-acceptance-v1.md`) binding artifact digests,
  environment, deviations, and limitations.
- PI12 produces the `ACE Builds ACE` evidence record (`docs/evidence/ace-builds-ace-v1.md`)
  binding the frozen harness configuration and digest (decision 15), the subject Decisions,
  baseline and ACE-assisted run identities, the full comparison measures, any excluded exploratory
  runs with the exclusion reason, and the no-self-authority proof. Improvement *proposals* the
  program surfaces are preserved as decision 16 experience-capture records — inputs to ACE 1.6
  matched evaluation; none activates in 1.2, and a justified no-learning result is recorded rather
  than discarded.
- Release closeout requires the four-record reconciliation: `ROADMAP.md`, issue #195, the ACE
  Public Roadmap Project, and the release evidence/published release must agree before ACE 1.2 is
  declared passed and 1.3 becomes **Now**.
- Known limitations carried into the release notes truthfully: no runnable restore from export;
  deletion non-reappearance proven only in the primary immutable-record store unless PI9 extends
  it; deletion never presented as universal erasure across backups, exports, or third-party
  copies; single-node topology.

## 9. Rollback

The bundle and adapters are separate artifacts over the released 1.1.0 substrate. Deactivating the
bundle and uninstalling its adapters must return the installation to the supported 1.1 contract
with no orphaned registrations, schema damage, or stranded authority. Core and Intelligence changes
in PI3/PI4/PI8 are additive contracts guarded by their own conformance tests; each slice's packet
records its specific rollback path before activation.

# ACE Atrium product UX comparison packet v1

Status: **Living Brief + Command Atlas selected — full brief-aligned v1 interface verified at the current contract ceiling**  
Controlling input: `ACE_Product_Interface_Direction_v1.docx` (11/11 pages rendered and reviewed)  
Current-state evidence: draft PR [#201](https://github.com/augmented-cognition-engine/core/pull/201), head `6064c225`  
Visual artifacts: [interactive comparison](mockups.html)

Brief-to-product control: [complete requirement, decision, and release ledger](brief-completion-ledger.md)
Runtime continuation: [P0 activation/health/correction → Pack lifecycle → consumer delivery roadmap](runtime-completion-roadmap.md)
Authoritative host-first-run extension: [Personal / Shared server / Dedicated appliance](../ace-host-first-run-onboarding-v1.md)

Rendered frames:

- A — Living Brief: [Overview](artifacts/a-living-brief-overview-1440x960.png), [onboarding](artifacts/a-living-brief-onboarding-1440x960.png), [Explore + Why?](artifacts/a-living-brief-explore-why-1440x960.png), [390×844 narrow](artifacts/a-living-brief-narrow-390x844.png)
- B — Evidence Ledger: [Overview](artifacts/b-evidence-ledger-overview-1440x960.png), [onboarding](artifacts/b-evidence-ledger-onboarding-1440x960.png), [Explore + Why?](artifacts/b-evidence-ledger-explore-why-1440x960.png)
- C — Command Atlas: [Overview](artifacts/c-command-atlas-overview-1440x960.png), [onboarding](artifacts/c-command-atlas-onboarding-1440x960.png), [Explore + Why?](artifacts/c-command-atlas-explore-why-1440x960.png)

## Selection

**Living Brief + Command Atlas was selected on 2026-08-14.** Living Brief owns the atmosphere, answer hierarchy, and restrained sense of continuous maintenance. Command Atlas owns the working shell, analyst density, evidence rails, and traversal speed. This is a role-bounded synthesis, not a visual average.

Production UI work follows this frozen role boundary. This document controls the selected direction’s visual and interaction roles.

### Frozen Living Brief + Command Atlas implementation lock

- **Primary foundation — Living Brief:** `#050506` canvas, `#F5F4F0` primary text, strong neutral hierarchy, one unmistakable current answer, and a restrained peripheral maintenance weave.
- **Structural layer — Command Atlas:** stable five-surface rail, compact command/search band, denser evidence and health rails, keyboard-fast traversal, and precise graphite panel divisions.
- **Surface hierarchy:** `#0D0E10` reading surface, `#121416` working panel, `#1A1D20` active/raised state, and `#2A2E31` 1px rules. Tonal depth replaces decorative shadow.
- **Accent role:** `#8A6CFF` is action/focus only. It never represents health, confidence, category, or severity.
- **Rejected C token:** Command Atlas orange is not carried forward because it competes with warning/degraded semantics. C contributes structure, not a second accent system.
- **Semantic color:** green means literal healthy/complete; amber means literal warning/degraded; danger red is reserved for blocked/error; informational color appears only for genuinely informational state.
- **Typography and density:** retain Living Brief’s regular-weight editorial authority, but cap the desktop lead at roughly 48–52px rather than a marketing-scale hero. Follow it immediately with Command Atlas’s compact movement, evidence, and health structure.
- **Home composition:** one lead current Brief in a roughly 72/28 reading-to-rail composition; the right rail holds Domain Health and attention context. Ranked material movement, signals, and unknowns follow without becoming an equal-weight dashboard mosaic.
- **Living quality:** the peripheral maintenance weave may react only to admitted update/maintenance state. It is removed under reduced motion and never becomes a brain silhouette, hero graph, or navigation object.
- **Explore relationship:** use Command Atlas’s stable result-tree / answer / evidence-basis structure. Explore deepens a selected Brief statement, entity, signal, event, or unknown; answer and evidence still precede a depth-limited relationship view.
- **Onboarding relationship:** Living Brief owns the focused question and generated-system reveal; Command Atlas owns the persistent blueprint, source-readiness, predicted-coverage, and change-review rails.
- **Host-first-run relationship:** a genuinely unconfigured host first asks one operating-boundary question, persists the result, and lands directly in Atrium. Configured or administrator-fixed hosts bypass that prompt. Runtime/model preparation continues as a truthful nonblocking status lane; it does not become a second tour.
- **Why?:** observation → resolved entities → material event → signal → assessment, with supporting/conflicting evidence, support state, and recalculation state. Raw trace remains in Operate.
- **Components:** existing shadcn/Radix primitives and Lucide only within the slice; no bespoke near-duplicates or second icon family.
- **Truth boundary:** unsupported coverage, confidence, conflict, resolution, historical-depth, or readiness data is labeled unsupported/pending dependency; it is never inferred from counts, timers, or presentation state.

## Product contract preserved

> Give ACE a domain. ACE builds and maintains the intelligence model. Humans, applications, and agents consume the resulting intelligence through the experience appropriate to them.

Atrium should ask **“What should ACE understand?”**, propose the intelligence system, explain every material change, obtain the required authority, and maintain the result. It should not make users assemble agents, ontologies, graphs, or connector pipelines as a prerequisite to value.

### MVP priority lock from the brief

| Priority | Preserved outcome |
|---|---|
| **P0** | Domain prompt and blueprint review; source plan, connection/readiness state, and coverage estimate; Overview state/changes/signals/unknowns; entity page and evidence; Why?/lineage; Domain Health. |
| **P1** | Explore search, timeline, and focused graph; ACE Architect explicit diffs; Domain Pack install/customize; Consumers. |
| **P2** | Agent topology/workforce and advanced source-pipeline tooling. These stay out of the first slice and never become the home. |

### Anti-pattern lock from the brief

- no agent-canvas-first experience;
- no graph home screen;
- no connector-count vanity;
- no chat-only shell;
- no technical observability language on every surface;
- no silent schema or blueprint changes;
- no bespoke application per domain; and
- no fake certainty.

## Current-state audit

### What PR #201 gets right

- It is briefing-first rather than connector-first.
- It keeps evidence one interaction away and treats Custom Intelligence as Preview.
- It preserves truthful proposal/activation boundaries in onboarding.
- It uses the existing resource plane and does not invent a second framework.
- It is already converging on shadcn/Radix primitives and Lucide within Atrium.

### Verified UI stack and component decision

The inspected canvas is React 18 + TypeScript + Vite + Tailwind 4 with shadcn and Radix primitives. Both Lucide and Phosphor are installed, but the current Atrium files use Lucide. The first slice should standardize Atrium on **Lucide**, reuse existing shadcn/Radix `Sidebar`, `Dialog`, `Tabs`, and related primitives, and avoid new bespoke near-duplicates. `tldraw` exists in the repository but is not justified for the brief’s focused depth-one relationship insert.

### Where it conflicts with the brief

1. The primary navigation reflects resource classes and downstream work more than the five domain surfaces.
2. The current home gives a large decorative `Cognitive Field` equal billing with the Brief, even though the answer must be primary.
3. Every resource is projected through the same four-part story grammar—`what changed / why it matters / how we know / when it changed`—which falsely equalizes evidence, interpretation, time, and uncertainty.
4. Cyan, blue, violet, and semantic status hues compete for attention. Accent is not sufficiently separated from status.
5. The procedural brain/graph signals “AI” but does not reveal a useful intelligence relationship.
6. The coverage strip emphasizes counts; the brief requires quality dimensions and honest unknown states.

### Naming and placement conflicts

| Today | Brief-aligned placement | Conflict and disposition |
|---|---|---|
| **Intelligence** | **Overview** | Today’s label is too broad; almost everything in ACE is intelligence. Rename the primary domain surface to Overview and make the current answer unmistakably dominant. |
| **Opportunities** | Overview attention lens; Explore saved view | An opportunity is a possible conclusion or decision opening, not a peer operating surface. Rank it in Attention and let analysts open a filtered Explore lens. |
| **Agents** | Build → Maintenance; Operate → Maintenance health | Agent configuration is an implementation detail. Expose proposed maintenance behavior in Build and runtime health/receipts in Operate. No agent canvas. |
| **Connections** | Global Connections; Build → Sources; Operate → Source health | The current peer route conflates connector administration, domain source binding, and health. Keep provider-neutral connector management global; show exact bindings and coverage in-domain. |
| **Strategy** | Consumers / downstream interface; selected outcomes reflected in Overview | Strategy work belongs in systems of action. ACE may expose an intelligence-to-decision contract and receive outcomes, but must not become a replacement execution engine. |
| **Investigation Board** | Consumers → downstream work | Retain as an explicit handoff target outside the five domain surfaces. Do not introduce a second handoff or investigation framework. |

### Proposed shell IA

```text
Domain switcher: World Intelligence | Market Intelligence | Custom Intelligence (Preview)

Domain surfaces
  Overview     current answer, material movement, signals, unknowns, attention, watchlist
  Explore      ask/search, entities, events, timeline, focused relationships, evidence
  Build        blueprint, model, source bindings, rules, maintenance proposals, Domain Pack
  Operate      Domain Health, conflicts, lineage, source/maintenance health, activity, evals/cost when supported
  Consumers    API, MCP, SDK, webhooks, subscriptions, streams, contracts, downstream handoff

Global
  Domain Packs | Connections | Workspace | Admin
```

World and Market are release-ready domain experiences. Custom Intelligence remains a proposal-only Preview in v1.

## Primary v1 journey reconciliation

The accepted UI already has five visible chapters—**Choose → Intent → Evidence → Review → Activate**. Keep those chapters to avoid a silent journey replacement. The source brief’s eight steps become explicit internal states and review gates inside them.

| Accepted chapter | Brief state(s) inside it | User-visible outcome | Truth boundary |
|---|---|---|---|
| **Choose** | Domain starter | Select World or Market; Custom remains Preview | Selection proposes vocabulary only; it grants no authority. |
| **Intent** | 1. Define intelligence goal; 2. generate blueprint | Answer “What should ACE understand?” and receive a proposed entity/event/signal/question/update/consumer blueprint | Every generated element carries rationale and confidence or an explicit `not scored` state. |
| **Evidence** | 4. source plan; 5. predicted coverage | Review exact source inventory/binding, evidence roles, permissions, readiness, missing access, and predicted coverage by entity/event/signal | A source is `proposed`, `access needed`, `ready`, or `unavailable`; provider/API credentials are described truthfully. |
| **Review** | 3. review/refine plus final authority gate | Inspect a change ledger: additions, removals, assumption changes, coverage effects, unknowns, and consumer effects | Material changes require explicit acceptance. Unequal information is not forced into equal cards. |
| **Activate** | 6. initialize; 7. validate first model; 8. continuous maintenance | Watch evidence admission → entity resolution → relationship mapping → events/signals → first cited intelligence state → maintenance activation | Completion comes from durable stages, not elapsed time. Blocked/retry states remain resumable. |

### End-to-end handoff

```text
What should ACE understand?
  → generated blueprint
  → reviewable change ledger
  → exact source plan + predicted coverage
  → permission and readiness gates
  → initialization with durable stages
  → first cited intelligence state in Overview
  → Why? / evidence / conflicts / unknowns
  → continuous maintenance with visible Domain Health
```

The first cited Brief lands directly in Overview. There is no blank success dashboard and no second tour.

### Host first run before the domain journey

The [authoritative host-first-run extension](../ace-host-first-run-onboarding-v1.md) adds a thin gate before the table above, not another intelligence-onboarding sequence. It asks only **“How should ACE run on this computer?”** with Personal, Shared server, and Dedicated appliance choices when no durable or administrator-fixed mode exists. A detected model plan reads as status, local-only is the safe default, and a large model download never blocks entry to Atrium. Dedicated appliance conversion and every destructive or remote-exposure mutation remain separate operator flows.

Current visual lock: [desktop choice](implementation/atrium-host-first-run-1440x960.png), [390×844 choice](implementation/atrium-host-first-run-390x844.png), and [nonblocking Atrium arrival](implementation/atrium-host-runtime-arrival-1440x960.png). These are candidate artifacts, not evidence of an implemented host API or accepted integrated release.

## Shared interaction contract across all directions

### Overview

- One current intelligence state is primary.
- Material movement, signals, unknowns, and attention are ranked by importance, not placed in equal KPI cards.
- Domain Health is compact but opens to the eight required dimensions.
- Counts never substitute for predicted or observed coverage.

### Explore

- Search/question-first entry.
- Results are answer + evidence + unknowns before graph.
- Relationships appear only around the selected entity, claim, or event with a visible depth control.
- Timeline is a peer focused view; no giant graph or graph home.

### Why?

The interaction reads in human order:

1. observation;
2. resolved entities;
3. material event;
4. signal;
5. assessment.

Supporting and conflicting evidence, confidence state, and last recalculation are visible. Raw trace, receipts, and operator diagnostics remain an Operate-level disclosure.

### Domain Health

All eight dimensions are present, but the UI must distinguish `measured`, `derived`, `observed`, and `not currently supported`:

- coverage;
- freshness;
- confidence;
- conflicts;
- resolution;
- source health;
- maintenance health; and
- historical depth.

The mockups use only the current PR fixture contract: one admitted provider-release source, one public-web connection, one analyst maintenance resource, a Shift, a Signal, a Case, a Brief, and linked evidence. Where the contract lacks a numeric measure, the artifact says `not scored` or uses a categorical state. It does not fabricate percentages.

## Live Refero reference board

These are the concrete visual and interaction patterns locked before mockup work. They are reference roles, not components to copy wholesale.

- **A primary mood — [Dala style](https://styles.refero.design/style/e5f5f8cf-e68d-4ed1-bbf5-6b67569af648):** breathing black field, editorial scale, sparse intelligence constellation.

  ![Dala black-velvet constellation style](https://images.refero.design/styles/dala.craftedbygc.com/ba81bf2a-a5ad-4234-92a4-1d6d47742785/preview_0.jpg)

- **A structure — [AgentQL style](https://styles.refero.design/style/d5307f56-76de-4d13-9741-f969c42e9aa5):** hairline graphite layering, achromatic hierarchy, white primary actions.

  ![AgentQL midnight technical style](https://images.refero.design/styles/www.agentql.com/ef0dd27d-d6e1-4bb9-9148-7ae40282a3f8/preview_0.jpg)

- **B primary mood — [Operate style](https://styles.refero.design/style/a0f473eb-0310-4df5-b5f6-5bc124ad5954):** pale technical ledger, faint grid, quiet plotted intelligence.

  ![Operate pale technical ledger style](https://images.refero.design/styles/operate.so/a0f473eb-0310-4df5-b5f6-5bc124ad5954/preview_0.jpg)

- **C primary mood — [Linear style](https://styles.refero.design/style/554b801c-3b31-4086-a7e5-ae613cdd618b):** layered graphite, compact command-center rhythm, disciplined accent.

  ![Linear dark command-center style](https://images.refero.design/styles/linear.app/554b801c-3b31-4086-a7e5-ae613cdd618b/preview_0.jpg)

- **Answer → evidence — [Parallel Deep Research](https://refero.design/pages/6ed820a6-666b-4eb9-84bf-45f35d45b021):** readable answer/tree with a persistent evidence-basis rail.

  ![Parallel answer and evidence-basis layout](https://images.refero.design/screenshots/parallel.ai/desktop/22adfac8-7a8f-48ec-8e87-4912381b7fc1_preview.jpg)

- **Focused graph — [Memotron depth-one graph](https://refero.design/pages/e652e15c-d27b-44d3-bb96-bdc16a0118a5):** user-controlled depth and one selected entity context; rejected as a home screen.

  ![Memotron focused entity graph](https://images.refero.design/screenshots/memotron.app/desktop/43b806c3-e97c-48a8-a897-1543d35d8507_preview.jpg)

- **Generated plan review — [Rox configuration review](https://refero.design/pages/8e214393-0d45-4abc-b986-746185d5c3ab):** prompt → generated model → editable steps and source plan before running.

  ![Rox generated research configuration review](https://images.refero.design/screenshots/rox.com/desktop/8e214393-0d45-4abc-b986-746185d5c3ab_thumb.jpg)

- **Initialization — [Spyglass connection progress](https://refero.design/pages/e6463a04-49e7-4942-ba4c-668328771ed0):** compact, durable setup outcomes while the workspace remains usable.

  ![Spyglass progressive data-connection setup](https://images.refero.design/screenshots/spyglass.so/desktop/e6463a04-49e7-4942-ba4c-668328771ed0_thumb.jpg)

## Direction A — Living Brief (selected visual foundation)

### Thesis

ACE is a calm, breathing field of maintained intelligence. The interface opens like a front page whose lead answer is being continuously revised, not like a dashboard of modules. A sparse “maintenance weave” sits at the periphery and responds only to real update state; it is never a brain silhouette or a navigation object.

### Reference lock

- **Primary style:** [Dala — “Your workplace has the answer. Just ask Dala for it.”](https://styles.refero.design/style/e5f5f8cf-e68d-4ed1-bbf5-6b67569af648)
- **Preserve:** black-velvet field, oversized regular-weight type, large breathing intervals, near absence of card chrome, intelligence visualized as a sparse constellation.
- **Borrow:** [AgentQL — “Aurora glow over a midnight terminal”](https://styles.refero.design/style/d5307f56-76de-4d13-9741-f969c42e9aa5) for graphite hairlines, achromatic text hierarchy, white primary actions, and code/provenance typography.
- **Product patterns:** [Parallel Deep Research](https://refero.design/pages/e794e9a1-0af9-44f5-8456-e6b678c8b05f) for a readable answer with durable source context; [Memotron focused graph](https://refero.design/pages/e652e15c-d27b-44d3-bb96-bdc16a0118a5) only for one-hop depth control; [Spyglass setup](https://refero.design/flows/13471) for visible initialization progress.
- **Token commitments:** `#050506` canvas; `#111214` elevated ink; `#F5F4F0` primary text; neutral grays for hierarchy; `#8A6CFF` action/focus only; amber for literal warning; green for literal healthy/complete; 1px graphite rules; 8–12px controls; 24px large editorial corners only.
- **Media:** code-native sparse nodes and threads driven by actual update states; no generated hero art.
- **Reject:** giant brain, aurora on every panel, violet status badges, generic chat home, equal card grid, ultra-light small body text.

### Shell + onboarding + Overview/Explore relationship

- Shell is narrow and quiet; the domain name and five surfaces are the main orientation.
- Onboarding is a focused, full-canvas conversation with a persistent blueprint/change ledger at right—one question at a time, not chat bubbles.
- Overview is the maintained answer. Explore opens as an evidence aperture from a sentence, entity, signal, or unknown, keeping the originating claim in context.

### Decision ledger

| Decision | Chosen | Rejected |
|---|---|---|
| Home composition | One lead Brief + ranked movement + unknowns | Mosaic dashboard |
| “Brain” feeling | Peripheral maintenance weave tied to update state | Literal brain silhouette or ambient particle wallpaper |
| Accent | Violet action/focus only | Violet/pink/blue category and status system |
| Explore | Contextual aperture from the answer | Full-screen graph as default |
| Health | Quiet language plus one literal status mark | Eight colorful gauges |

## Direction B — Evidence Ledger

### Thesis

ACE feels like an exceptionally clear intelligence publication with an audit ledger underneath. The experience is bright, architectural, and exact: conclusions read like a maintained document; evidence and model changes read like a controlled record.

### Reference lock

- **Primary style:** [Operate — pale technical ledger](https://styles.refero.design/style/a0f473eb-0310-4df5-b5f6-5bc124ad5954)
- **Preserve:** light field, fine technical rules, diagram/ledger character, purposeful charting, generous but disciplined whitespace.
- **Borrow:** [OpenAI Developers](https://styles.refero.design/style/44317718-37ff-4771-802c-f1408734ad79) for architectural spacing and neutral information design; [Rox generated configuration flow](https://refero.design/flows/10802) for prompt → generated plan → editable steps → source review.
- **Product patterns:** [Parallel research basis panel](https://refero.design/pages/6ed820a6-666b-4eb9-84bf-45f35d45b021) for an evidence basis rail; [Memotron focused graph](https://refero.design/pages/733b81ed-fb9c-499b-b90c-4b66ee996e39) for a restrained entity relationship insert.
- **Token commitments:** `#F4F6F1` canvas; `#FEFFFC` paper; `#161917` ink; `#69706B` secondary; `#D9DED8` rules; `#206552` action/focus only; semantic status colors remain literal; 0–6px corners; no shadows beyond floating inspection layers.
- **Media:** vector evidence chains, timelines, and source-role diagrams; no photography or generated illustration.
- **Reject:** dark developer-tool shell, faux-terminal chrome, soft SaaS cards, green wash on every surface, spreadsheet-first exploration.

### Shell + onboarding + Overview/Explore relationship

- Shell behaves like an intelligence publication index with a persistent domain folio.
- Onboarding is a controlled dossier: the question, blueprint, source plan, and change ledger remain visible as sequential sections rather than modal steps.
- Overview is a concise daily edition. Explore changes the same page into annotated evidence and entity columns; context is preserved by typographic anchors and side notes.

### Decision ledger

| Decision | Chosen | Rejected |
|---|---|---|
| Home composition | Editorial lead + ruled change ledger | Card dashboard |
| Evidence | Margin notes and basis rail | Tooltip-only citations |
| Onboarding | Reviewable dossier | Wizard that hides prior decisions |
| Graph | Small evidence figure embedded in context | Free-roaming canvas |
| Health | Typed ledger rows with support level | Decorative radial scores |

## Direction C — Command Atlas

### Thesis

ACE is an always-on command atlas for analysts: denser, darker, and more operational than the other directions, but still answer-first. It emphasizes fast traversal among a Brief, entity state, evidence basis, and maintenance health through a stable three-pane shell.

### Reference lock

- **Primary style:** [Linear dark command center](https://styles.refero.design/style/554b801c-3b31-4086-a7e5-ae613cdd618b)
- **Preserve:** layered graphite surfaces, compact typography, fast keyboard-oriented navigation, precise dividers, minimal rounding.
- **Borrow:** AgentQL’s white primary action and IBM Plex Mono provenance treatment; [Axiom](https://styles.refero.design/style/6e9baa82-2f2f-4e77-8b0d-566325635dbe) for a single precision accent.
- **Product patterns:** [Parallel three-pane research](https://refero.design/pages/6ed820a6-666b-4eb9-84bf-45f35d45b021) for answer/tree/basis structure; [Rox generated plan review](https://refero.design/pages/8e214393-0d45-4abc-b986-746185d5c3ab) for editable generated configuration.
- **Token commitments:** `#0B0C0D` canvas; `#121416` panel; `#1A1D20` raised panel; `#E7E9E7` primary text; `#9AA09D` secondary; `#2A2E31` rules; `#FF7849` action/focus only; literal semantic colors only; 6–8px controls and panels.
- **Media:** no ambient hero media. Focused relation maps, sparklines, and evidence trees are code-native and functional.
- **Reject:** visual spectacle, floating gradient blobs, excessive panel nesting, “mission control” cosplay, graph as primary workspace, orange warning confusion.

### Shell + onboarding + Overview/Explore relationship

- Shell has stable navigation, a command/search band, a primary reading pane, and an optional evidence/health rail.
- Onboarding uses the same shell: intent and generated blueprint in the center, change/readiness inspection in the right rail.
- Overview and Explore are modes in one stable workspace. Explore swaps the center into entity/timeline/focused-graph views while the selected Brief statement remains pinned.

### Decision ledger

| Decision | Chosen | Rejected |
|---|---|---|
| Home composition | Dense lead Brief + attention queue + health rail | Giant hero or empty canvas |
| Navigation | Stable five-surface rail + command search | Resource-type peer navigation |
| Explore | Answer + tree + basis | Infinite canvas |
| Accent | Orange focus/action only | Orange as degraded/warning |
| Density | Analyst-fast, adjustable rail | Executive-facing default density for every role |

## Comparison and recommendation

| Criterion | A — Living Brief | B — Evidence Ledger | C — Command Atlas |
|---|---:|---:|---:|
| North-star clarity | **Excellent** | Excellent | Good |
| “Continuously working / brain-like” without AI noise | **Excellent** | Good | Good |
| Overview answer hierarchy | **Excellent** | Excellent | Good |
| Explore/evidence depth | Good | **Excellent** | **Excellent** |
| Executive readability | **Excellent** | **Excellent** | Fair |
| Analyst speed | Good | Good | **Excellent** |
| Distance from generic SaaS | **High** | High | Medium-high |
| Risk in v1 | Medium | Low-medium | Medium-high |

### Why the A + C synthesis was selected

Direction A gives the strongest product meaning to “ACE is continuously maintaining a model” without exposing the machinery as the product. Direction C prevents that idea from becoming too editorial for sustained analyst work: it adds a stable shell, compact evidence structure, Domain Health rail, and faster traversal between answer, entity, lineage, and operations. A remains visually dominant; C contributes bounded workspace mechanics. The result stays close to the explicit Dala × AgentQL target while correcting PR #201’s literal brain, weak hierarchy, and color drift.

Use B if auditability, accessibility in bright environments, and executive print/read behavior should dominate the brand expression. Use C if the primary launch audience is analysts who will accept higher density and if the team can support the interaction/state complexity.

## Customer-visible v1 limitations

- World and Market are release-ready; Custom Intelligence is proposal-only Preview.
- v1 does not promise a universal connector catalog. Exact available source types and bindings must come from admitted capabilities.
- A consumer subscription is not an API credential. Provider/API credential setup must name the actual credential and permission boundary.
- Predicted coverage is an estimate until evidence is admitted; observed coverage must remain distinct.
- Numeric confidence, conflict detection, resolution quality, historical depth, evals, and cost appear only when current contracts support them. Otherwise the UI says `not scored`, `not evaluated`, or `insufficient history`.
- Existing RAG/search behavior is release-critical and remains unchanged by this design task.
- Consumers exposes interfaces and downstream contracts; it does not promise execution inside ACE.

## Decisions still unresolved from the brief

1. What is the smallest user-correctable intelligence object: observation, entity fact, event, signal, assessment, or conclusion?
2. Which Domain Health dimensions are computable now, which are derived, and which must launch as categorical/unsupported?
3. Should blueprint editing default to a structured form, table, or generated change ledger? Graph remains inspection-only.
4. Does Explore default to ask/search, timeline, entity index, or domain-configured lens for World versus Market?
5. How does a user correction affect source trust, entity resolution, signal strength, and future brief ranking without changing authority?
6. Which proposed model changes may auto-apply, and which always require explicit acceptance?
7. How are Domain Pack upgrades, local overrides, rollback, and history represented?
8. What provenance contract must downstream consumers preserve and return with outcomes?

## Smallest coherent implementation slice after selection

No implementation should begin until a direction is selected. The first slice should be narrow enough to verify the product thesis without requiring unsupported backend work:

1. Replace the current domain peer navigation with a domain switcher plus Overview / Explore / Build / Operate / Consumers labels, retaining safe redirects for existing routes.
2. Recompose the current fixture-backed Overview: lead Brief, one ranked Shift, one Signal, one Unknown/insufficient-evidence state, Attention, and compact honest Domain Health.
3. Replace the decorative `CognitiveField` with the selected direction’s functional treatment; in A, this is a reduced-motion maintenance weave driven only by existing resource/update state.
4. Add one focused entity/evidence inspection path and the human-readable Why? chain over existing lineage. Do not change RAG/search.
5. Restyle the current accepted onboarding shell and add the visible blueprint/source/change-ledger concepts only where current proposal contracts support them. Unsupported readiness/coverage fields remain explicit dependencies.
6. Standardize Atrium on existing shadcn/Radix primitives and Lucide; remove bespoke near-duplicates within the slice only.

### Explicit backend dependencies

- blueprint rationale/confidence fields;
- predicted versus observed coverage by entity/event/signal;
- permission/readiness status per exact binding;
- typed conflict and resolution state;
- last recalculation and maintenance-stage events;
- supported Domain Health measurements and provenance.

The UI must not synthesize these from timers, resource counts, or presentation-only state.

### Accessibility and verification

- WCAG 2.2 AA text contrast; no status conveyed by color alone.
- Complete keyboard path through domain switcher, five surfaces, ranked Brief items, Why? disclosure, evidence rail, and onboarding review.
- Visible focus using the direction’s action/focus token; accent never doubles as status.
- Semantic headings and landmarks; evidence steps use an ordered list; health uses text labels and support states.
- Reduced-motion mode removes constellation/weave movement without hiding update state.
- Narrow state preserves the lead answer first, collapses navigation and evidence rails, and never forces horizontal graph panning.
- Visual regression screenshots at 1440×960, 1280×800, 768×1024, and 390×844.
- Focused component tests for ranking order, unsupported health states, semantic status labels, and Why? lineage disclosure.
- Focused journey test from accepted onboarding proposal through first cited Brief using durable stage fixtures.

## Selection disposition

**Living Brief + Command Atlas is selected.** The bounded source roles and combined token lock are frozen above. The full brief-aligned v1 interface now applies this direction across the shell, onboarding, Overview, Explore, Build, Operate, Consumers, trust, Pack lifecycle, and responsive states while keeping unsupported runtime contracts explicit.

## Completion and dependency ledger

The source DOCX remains the controlling product-direction input. This ledger tracks delivery after the selected A+C shell slice; a task may not mark a capability complete when it has only added presentation fixtures or inferred data.

| Workstream | Priority | Status | Contract gate / completion test |
|---|---:|---|---|
| Projection contract closure | P0 | **Integrated proposal path · authoritative resource enrichment complete backend-side** | The canonical projection covers blueprint, exact review changes, bindings, separate permission/readiness, predicted versus observed coverage, eight initialization stages, derivation shape, and eight Domain Health dimensions. A complete authorized resource read can now derive literal observed target coverage through exact Pack/binding lineage and observe exact per-binding source state. Atrium is not yet live-wired: host composition plus an accepted-plan/session-to-activation association remain required. Predicted coverage and the other six health measurements remain explicit architecture dependencies. |
| World + Market onboarding | P0 | **Integrated through governed start · runtime-gated** | The accepted Choose → Intent → Evidence → Review → Activate shell consumes the canonical projection and durable session state, then uses the existing prepare → exact bind → governed start path only when the host supplies a reviewed approval receipt and exact capability/authority bindings. Custom remains proposal-only Preview. Production approval resolution, binding-specific readiness, executor availability, and a supported retry command remain runtime dependencies. |
| Entity intelligence + Explore | P0/P1 | **Integrated at supported depth** | Explore remains Ask-first and now adds current entity state, directional movement, an admitted timeline, evidence, conflicts/unknowns, supported confidence, and exact depth-zero/depth-one resource lineage. Typed semantic relationships and first-class event projections remain architecture dependencies. Existing RAG/search semantics are unchanged. |
| Why? + Domain Health trust layer | P0 | **Integrated for current contracts** | Why? follows exact product/kind/id/revision/digest closure, includes exact Shift→Signal descendants and revision evidence, and separates supporting/conflicting evidence and unknowns. The challenge path records one of four correction intents, a note, and exact evidence references through authenticated `derive_propose` authority, returning an immutable attributed no-effect receipt and projecting the result as Feedback. All eight health dimensions show contracted values or explicit unavailability; no count, page time, or resource presence becomes a proxy score. |
| Domain Packs + Consumers | P1 | **Integrated UI; lifecycle reads complete backend-side** | Build separates World/Market release readiness from Custom proposal-only Preview and local installation, then reports install/customize/upgrade/history/rollback availability literally. The backend now reads the exact governed Pack/overlay and bounded append-only history by explicit activation key with plan, approval, and commit provenance; Atrium wiring remains. Consumers shows interface availability, permission, delivery, provenance, and provider-credential truth. No Pack mutation or unsupported delivery is fabricated. |
| Integration + release verification | P0 | **Combined verification passing** | Compatible slices are merged into the selected A+C shell. All 372 Canvas unit/component tests, the production build, eight integrated Atrium browser journeys, 46 focused backend contracts/boundaries, visual captures, and the combined non-extension backend suite (8,073 passed; 50 skipped; 263 deselected, plus 4 kernel-boundary tests) pass. |

### Dependency order

1. Projection contracts define the truthful ceiling for every experience.
2. World/Market onboarding, entity exploration, and trust-layer work may advance in parallel where existing contracts already suffice.
3. Integration follows only for coherent slices with explicit fixtures versus durable runtime data.
4. Domain Packs and Consumers follow the P0 MVP proof; they must reuse the same maintained intelligence model and provenance boundary.
5. P2 agent-topology and advanced source-pipeline detail are present as subordinate truthful disclosures. Editable topology/pipeline visualization remains deliberately deferred until authoritative runtime projections exist.

### Product decisions closed; runtime contracts still required

The eight open product questions are resolved in the [brief completion ledger](brief-completion-ledger.md): exact-record correction targets, support-aware health, ledger-first blueprint editing, Ask-first Explore, governed correction effects, explicit material-change review, layered Pack upgrades/overrides/history, and exact downstream provenance.

Implementation remains deliberately gated on real architecture for: exact customer binding/credential/readiness projection; authoritative predicted-coverage estimators; cadence freshness, domain-confidence, typed conflict/resolution, maintenance-outcome, and comparable-history contracts; accepted-blueprint history; governed decisions and effect/recalculation receipts after recorded corrections; reviewed Pack overlay mutation, upgrade discovery/compatibility planning, and customer rollback actions; stream/webhook delivery; and a required downstream provenance-return envelope. Exact observed target coverage, literal binding source state, and exact Pack/overlay history now derive from governed material without proxy scoring.

### Implementation checkpoint — 2026-08-14

Verified captures: [Overview · 1440×960](implementation/atrium-living-brief-overview.png), [Explore answer · 1440×960](implementation/atrium-explore-answer.png), [Explore + Why?/challenge · 1440×960](implementation/atrium-explore-why.png), [Entity intelligence · desktop](implementation/atrium-entity-intelligence.png), [Entity intelligence · narrow](implementation/atrium-entity-intelligence-narrow.png), [Build + Pack lifecycle · desktop/full page](implementation/atrium-build.png), [Operate · 1440×960](implementation/atrium-operate.png), [Consumers · 1440×960](implementation/atrium-consumers.png), [loading picture · 1440×960](implementation/atrium-loading.png), [degraded Overview · 1440×960](implementation/atrium-degraded-overview.png), [degraded Operate · 1440×960](implementation/atrium-degraded-operate.png), [unavailable picture · 1440×960](implementation/atrium-unavailable.png), [retained picture after refresh failure · 1440×960](implementation/atrium-refresh-failed.png), [onboarding choice · 1440×960](implementation/atrium-custom-preview-choice.png), [onboarding review · 1440×960](implementation/atrium-exact-plan-review.png), [canonical system projection · 1440×960](implementation/atrium-canonical-system-projection.png), [exact effects · 1440×960](implementation/atrium-exact-plan-effects.png), [activation/readiness · 1440×960](implementation/atrium-activation-readiness.png), [Custom review · 1440×960](implementation/atrium-custom-preview-review.png), [Custom review · 390×844](implementation/atrium-custom-preview-review-narrow.png), [Custom proposal complete · 1440×960](implementation/atrium-custom-preview-complete.png), [durable first Brief ready · 1440×960](implementation/atrium-live-builder-ready.png), [Overview · 1280×800](implementation/atrium-living-brief-1280x800.png), [Overview · 768×1024](implementation/atrium-living-brief-768x1024.png), [Overview · 390×844](implementation/atrium-living-brief-narrow.png), and [Explore answer · 390×844](implementation/atrium-explore-answer-narrow.png).

- Visible IA is now Overview / Explore / Build / Operate / Consumers; earlier Intelligence, Opportunities, Agents, Connections, and Strategy deep links canonically redirect to their brief-aligned placement rather than preserving stale peer-surface URLs.
- Overview now renders the current Brief, one ranked Shift, Signal, explicit Unknown, Attention, and the eight honest Domain Health dimensions in a 72/28 reading-to-rail composition.
- Explore preserves the existing Ask ACE search behavior and adds answer/evidence/result-tree structure, a depth-one relationship insert, and a human-readable Why? derivation.
- Ask ACE now uses a neutral command surface: the conclusion and rationale lead, timing is metadata, evidence is a ledger, and accent remains confined to the question action/focus path rather than masquerading as answer or governance status.
- Explore’s record counts are a non-interactive result summary, not fake filter controls; the only graph-like treatment remains the selected record’s truthful depth-one evidence closure.
- The portaled Why? sheet carries the same scoped Atrium tokens as the shell; browser coverage locks its foreground/background contrast before capturing the evidence derivation.
- Why? labels the contract’s `available_at` honestly as record availability, routes to the existing trust layer without promising an unbuilt lineage view, and accepts confidence only when the record projects a value from 0 to 1.
- Build, Operate, and Consumers use a shared compact record ledger—type/revision, title/summary, literal availability, and evidence basis—instead of rounded resource-card mosaics. Consumers no longer forces decision records into the equal “what changed / why / how / when” grid.
- The decorative node-link “brain” treatment is replaced by resource-driven organic maintenance contours with no graph affordance, colored status nodes, or AI-network cliché; reduced motion freezes the contours without hiding state.
- The accepted Choose → Intent → Evidence → Review → Activate sequence remains intact; the intent question is aligned to “What should ACE understand?” and unsupported Custom execution remains Preview-only. Intent, Evidence, and Review now retain a compact contract-backed rail for domain, intent, blueprint, source plan, cadence, change set, authority, and unsupported coverage/readiness.
- Exact and Custom reviews use Command Atlas ledgers rather than equal card mosaics. Proposed effects foreground the change, subordinate its rationale, move method/timing to operational metadata, and isolate unknowns instead of treating “what / why / how / when” as equivalent content.
- Exact World/Market review now requests the additive canonical system projection after plan preparation and renders the generated blueprint, exact source bindings, permission/readiness separately, predicted and observed coverage separately, eight initialization stages, and eight proposal-time Domain Health dimensions. A projection failure leaves the exact plan reviewable but makes the missing canonical layer explicit.
- Configured World/Market activation now follows the existing v1alpha3 prepare → bind → start contract and validates exact capability/authority bindings plus a reviewed approval receipt. Missing, denied, stale, or unavailable authority leaves the exact review intact and cannot be presented as readiness.
- Explore now retains the existing Ask ACE answer/basis structure and adds a focused entity intelligence layer below it: admitted current state, directional movement, timeline, evidence, conflicts/unknowns, supported confidence, and user-controlled exact resource lineage at depth zero or one. It does not invent semantic entity relationships or relabel generic resources as events.
- Build now exposes Pack installation, declared customization, upgrade discovery, history, rollback, and release posture as separate literal states; Consumers exposes authenticated interface contracts and their provenance, permission, and delivery boundaries without introducing a second handoff framework.
- Why? exposes exact revision and Shift→Signal derivation, the four challenge/correction intents, and existing linked Feedback proposals. It now submits an authenticated proposal against the exact resource and returns its attributed immutable receipt, while refusing to claim any trust, ranking, resolution, authority, or recalculation effect.
- Atrium uses the established shadcn/Radix primitives and Lucide in this slice. Accent is action/focus; semantic status remains literal and text-labeled.
- Icons follow a centralized semantic taxonomy rather than a generic “secure AI” motif: shields are reserved for Operate’s trust boundary and explicit risk; current state, governed evidence, questions, sources, signals, Briefs, agents, and decisions use distinct Lucide glyphs.
- Focused unit coverage verifies the eight Domain Health labels, unsupported scores, and Why? derivation. The fixture-backed browser journey verifies Overview → Explore → Why? → Operate, onboarding plan review, Custom Preview, durable first-Brief landing, and the collapsed narrow shell.
- Current implementation captures cover all four locked responsive baselines. At 768px the navigation defaults to a user-toggleable icon rail, preserving reading width without shrinking the Brief into a dashboard tile.
- Stacked Overview health, Build review boundaries, and Consumers handoff context switch from desktop side rails to top-separated sections; all five surfaces are regression-checked at 390px for horizontal overflow.
- Degraded pages preserve the current cited Brief, count explicitly degraded records, surface the affected record as an Unknown, retain literal degraded status in Operate, and never collapse the experience into a generic error dashboard.
- A failed resource request is distinct from an empty domain: Atrium shows an unavailable-picture truth boundary, never opens or advertises onboarding, substitutes no inferred content, and recovers through the existing retry path.
- A failed refresh with a previously loaded page preserves that cited picture but labels it **Last loaded picture**, explains the continuity boundary, and returns to **Picture current** only after a successful retry.
- Loading mirrors the Living Brief’s answer → movement → signals/unknowns/attention → health hierarchy instead of reverting to a generic hero rectangle and equal dashboard cards.
- Domain Health no longer treats the presence of a source-health record as proof of a healthy source, maintenance-resource presence as maintenance health, or multiple unrelated Briefs as revision history. Those dimensions remain explicitly unscored unless the current records support them.
- Initialization progress is described as ACE-owned governed maintenance work; the UI does not invent a parade of Connection, Ontology, Intelligence, and Briefing agent personas.
- Keyboard structure now includes a first-focus skip route into the named intelligence region, trapped and restored focus for portaled reviews, explicit current-step semantics, pressed states for selectable plans, and non-color progress labels.

Remaining architecture dependencies are explicit: supported blueprint confidence, governed predicted-coverage estimators, per-binding permission/readiness adapters, cadence freshness, domain-confidence, typed conflict/resolution quality, authoritative maintenance outcomes, and comparable-history depth. Exact observed target coverage and per-binding source state are available from a closed authorized resource read; the UI still does not synthesize unsupported values.

### Integrated verification checkpoint — 2026-08-15

- Canvas: **372 passed** across 51 unit/component test files; production TypeScript/Vite build passed.
- Browser journeys: **8 passed** for the A+C Overview/Explore/Why?/Operate/onboarding/entity paths, including desktop and 390px states. The separate external-domain resource test remains backend-seed-dependent and was skipped when that backend was unavailable.
- Backend focused contracts: **46 passed** across projection, build/activation, Pack/catalog, API, and public/kernel-boundary suites; Ruff passed.
- Combined backend: **8,073 passed, 50 skipped, 263 deselected**, followed by **4 passed** kernel-boundary tests.
- Visual QA: Pack lifecycle, correction/Why?, activation/readiness, canonical onboarding projection, focused Entity Explore desktop/narrow, and the 1440/1280/768/390 shell baselines are stored in `implementation/` above.

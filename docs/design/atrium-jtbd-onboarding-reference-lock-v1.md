# Atrium JTBD onboarding and AI command-center reference lock v1

## Product outcome

Atrium helps a person keep a trustworthy, continuously updated picture of a subject that changes
faster than they can follow it. The first flagship experience is World Intelligence focused on AI,
but the shell and onboarding contract remain domain-neutral.

The primary job is:

> When AI changes faster than I can follow, help me understand what materially changed, why it
> matters to me, what deserves attention, and what I can trust so I can decide without reading
> everything.

The user does not install agents, author an ontology, or choose reasoning machinery. They state the
decision context; ACE proposes the evidence, concepts, watches, and briefing system required to
serve it.

## Jobs to be done

| Job | Question Atrium must answer | Product response |
|---|---|---|
| Orient | What changed since I last looked? | A short `Since your last visit` narrative and the three to five most material Shifts. |
| Prioritize | What deserves my attention now? | An attention rail ordered by materiality, relevance, recency, and evidence quality. |
| Explain | Why does this matter to my role or decision? | Each Shift carries a plain-language implication and affected watch or decision. |
| Compare | How did providers, models, costs, reliability, and adoption move relative to each other? | Domain-configured intelligence products such as capability-per-dollar and claim-versus-reality. |
| Verify | Is this fact, a first-party claim, an inference, disputed, or unknown? | Evidence roles, corroboration, conflicts, uncertainty, citations, and exact lineage remain inspectable. |
| Track | What entities, topics, commitments, and thresholds am I watching? | A concise watchlist with status, next catalyst, and editable relevance. |
| Anticipate | What weak signals may precede an announcement or constraint? | Leading-indicator Cases that remain visibly distinct from established Shifts. |
| Decide | What opportunity, risk, or investigation follows? | A bounded next step into Opportunities, Strategy, or downstream investigation. |
| Learn | Can this become more useful without silently changing truth or authority? | Useful/not-useful feedback reweights relevance; authority, evidence, and policy do not self-widen. |

## First-run journey

The magic moment is `choose a job -> accept a recommended watch system -> see the first cited
briefing`. Public evidence can produce first value before the user connects private data.

### 1. Choose the outcome

The first screen asks one question: **What do you need to stay ahead of?** A Domain Pack supplies a
small set of outcome choices. The World AI pack starts with:

- choose or buy AI;
- set strategy or evaluate investments;
- track frontier research and products;
- manage policy, safety, and operational risk;
- understand the competitive landscape; and
- build a custom picture.

These are decision contexts, not personas, agent names, or feature categories.

### 2. Tune the picture

ACE recommends topics, entities, and a delivery cadence for the selected outcome. The user may edit
the recommendation, but the default is complete enough to continue. AI topics include models and
capabilities, independent evaluations, economics, reliability, open research, security, policy,
capital, compute, talent, adoption, and executive narratives.

The UI asks only for information ACE cannot safely infer:

- named entities or technologies the user specifically cares about;
- desired cadence: urgent only, daily pulse, or weekly briefing; and
- optional private sources the user is authorized to connect.

### 3. Review what ACE will build

The review is plain language:

- sources ACE recommends and why each evidence role is needed;
- concepts and relationships ACE proposes to map;
- watches and materiality rules ACE proposes to activate;
- expected first intelligence products; and
- permissions, gaps, and sources that remain proposed rather than connected.

One primary action—**Start watching**—admits the reviewed plan through the existing governed
onboarding and activation lifecycle.

The current repository-delivered slice intentionally does not add a second mutable Atrium API.
Atrium reads profiles and session revisions through the existing authenticated resource plane. A
product host that accepts the reviewed plan must invoke the public Builder services and Core
approval boundary; clicking through a proposal in Atrium alone grants nothing.

### 4. Watch the system assemble

Agent work appears as one compact progress story, not as five configuration screens:

1. finding and validating sources;
2. mapping entities and concepts;
3. building watches;
4. checking coverage and contradictions; and
5. assembling the first cited Brief.

Progress is expressed as outcomes such as `18 sources ready`, `42 entities mapped`, `6 watches
active`, and `first Brief ready`. Agent identity, receipts, permissions, and failures remain
available in an inspection drawer.

Atrium must never infer these outcomes from elapsed time or a client-only checklist. `Complete`
requires the corresponding durable session stage; blocked and retrying revisions remain visible;
and the first-Brief action appears only after `first_briefing_ready`.

### 5. Land in a populated Atrium

The completion action opens the first Brief inside the normal command center. There is no separate
tour and no blank dashboard. Onboarding remains resumable from Connections and editable from
Agents, but it stops interrupting normal use.

## AI command-center information architecture

### Above the fold

1. **Since your last visit** — a concise orientation narrative scoped to the selected job.
2. **Material movement** — three to five ranked Shifts with `why it matters to you`.
3. **Attention** — conflicts, weakly supported claims, expiring evidence, material Cases, and
   upcoming catalysts.
4. **Ask ACE** — grounded search over the current governed picture, with cited revisions and an
   explicit insufficient-evidence response.
5. **Picture health** — a single compact strip for active watches, admitted evidence, freshness,
   conflicts, and unknowns.

### Intelligence modules

The World AI Domain Pack configures modules; Core renders them as projections over canonical
resources:

- capability-per-dollar frontier;
- claim versus independent reality;
- research-to-product diffusion;
- capital-to-capability conversion;
- infrastructure bottlenecks;
- regulation-to-implementation gap;
- strategy before announcement;
- executive promise tracker; and
- adoption-versus-trust gap.

Supporting views include a watchlist, an evidence timeline, upcoming catalysts, entity comparison,
and a source/provenance drawer. Atrium never turns a source catalog into a feed wall. Sources are
visible through coverage, citations, disagreements, and health.

## Agent experience model

| User-facing role | Responsibility | What the user sees |
|---|---|---|
| Setup Guide | Elicits the job and drafts the complete onboarding plan. | One recommendation and the questions ACE could not infer. |
| Source Scout | Proposes public and authorized private sources; tests access and coverage. | Recommended source roles, permission requests, gaps, and connection state. |
| Ontology Mapper | Resolves entities, concepts, aliases, and relationships. | Proposed mappings and only the ambiguities that need review. |
| Watch Builder | Converts the job into monitors, materiality rules, and cadence. | Watches in plain language with editable scope. |
| Briefing Agent | Synthesizes supported Shifts and Cases into a cited Brief. | The first Brief and its exact supporting revisions. |
| Quality Challenger | Tests corroboration, contradiction, uncertainty, and unsupported conclusions. | Warnings, competing evidence, and honest insufficient-evidence states. |
| Learning Agent | Uses explicit feedback and outcomes to reweight relevance. | Better ranking and a visible explanation of what changed; no authority widening. |

These roles are governed compositions over ACE capabilities. They are not autonomous personalities,
new sources of truth, or separate products.

## Domain onboarding-profile boundary

Core owns a versioned, domain-neutral presentation contract for a Domain Pack to declare:

- outcome choices;
- selectable topics and entity classes;
- cadence choices;
- recommended source roles;
- proposed watches and intelligence products; and
- user-facing labels and descriptions.

The profile is declarative and non-authorizing. Selecting it creates an onboarding proposal; the
existing Connect, Map, Watch, Brief, and Activate lifecycle remains the only path to live authority.
Domain Packs cannot provide imperative UI code, bypass consent, claim proposed sources are
connected, or change Core navigation.

## Research synthesis and reference lock

The design direction was researched before implementation:

- Linear Changelog provides the midnight surface hierarchy, compact editorial rhythm, precise
  dividers, restrained radii, and calm typography.
- Oxide contributes the technical credibility of sharp graphite surfaces and a single disciplined
  live-state accent rather than decorative gradients.
- Checkly contributes operational status language and dense monitoring panels that remain legible.
- Rox contributes a connection checklist, recommended integrations, clear permission explanation,
  and visible connected/connecting state.
- Fingerprint contributes grouped, expandable setup progress with durable status language rather
  than decorative agent animation.
- Reclaim contributes the sequence `connect -> confirm -> personalize -> provision`, with setup
  status retained after the user leaves the first-run flow.
- Macaw contributes the immediate handoff from inspected source understanding to a populated
  generated result rather than a blank success screen.
- Gemini contributes the centered readable answer with a dedicated source panel one interaction
  away.
- Spyglass contributes one dominant orientation view with a narrow contextual rail instead of an
  equal-weight dashboard grid.
- Nextdoor and Product Hunt onboarding demonstrate outcome/topic selection followed immediately by
  a populated personalized feed.

Primary direction: Linear's compact midnight command center. Borrowed details: Rox's recommended
connection/status pattern and Gemini's source side sheet. Preserve ACE mint only for live,
confirmed, or selected state. Use mono typography only for time, count, status, and provenance.

Explicit rejections:

- a 70-source integration wall;
- a parade of named agent personalities;
- architecture, ontology, or prompt configuration during first use;
- a seven-step coach-mark tour after setup;
- a blank dashboard while connectors run;
- rainbow category and severity systems;
- unsourced AI answers; and
- domain-specific UI branches inside Core.

Implementation lock: the primary direction remains Linear's compact midnight shell. Rox owns the
connection-card behavior, Fingerprint the progressive status disclosure, Reclaim the confirmed
setup sequence, and Macaw the populated-result handoff. ACE retains its existing mint accent only
for selected, live, or proven state. Proposal, working, blocked, retrying, and complete are semantic
states; the interface must not average them into a single optimistic progress treatment.

## Acceptance journey

1. A clean install opens with no live intelligence and offers one outcome-led start action.
2. A user selects an AI decision context, accepts recommended topics and cadence, and sees proposed
   public evidence before granting authority.
3. ACE explains every requested permission and keeps failed or skipped connections resumable.
4. The governed agents produce an inspectable Connect -> Map -> Watch -> Brief -> Activate trace.
5. The first cited Brief appears without hand-authored ontology work or knowledge of ACE internals.
6. The user can ask a grounded question, inspect exact evidence, mark relevance, and see that
   feedback changes ranking without changing evidence or authority.
7. Restart/reopen returns to the same active watches, latest Brief, onboarding history, and user
   preferences.
8. The same Core shell reproduces a materially different Market Intelligence profile without code
   changes.

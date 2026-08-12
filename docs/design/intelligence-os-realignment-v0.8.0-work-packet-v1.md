# ACE 0.8.0 Intelligence OS Realignment work packet

Status: **active architecture and compatibility packet**  
Public milestone: [issue #40](https://github.com/augmented-cognition-engine/core/issues/40)  
Release input: `main@11b44e84d92e0674fa433103779f4050eeca2725` (`ace-core==0.7.0`)  
Target: `ace-core==0.8.0`

## Outcome

ACE 0.8.0 must make the product and the implementation tell the same story:

> ACE is an open, provider-neutral Intelligence Operating System. The Intelligence Builder is its
> first guided experience. Reasoning, memory, planning, learning, graph state, authority, and
> optional models are governed substrate inside the system rather than separate product arms.

The user-visible builder journey shipped in 0.7 remains intact:

```text
Connect → Map → Watch → Brief → Activate
```

0.8 makes the complete operating loop coherent and inspectable:

```text
authorized evidence
→ Observation
→ temporal Entity state
→ Signal / Shift
→ Case / Brief
→ Decision / authorized Action
→ observed Outcome
→ governed Feedback proposal
→ explicit review and later use
```

This is a realignment release, not a rename-only release and not permission for a mass rewrite.
Existing supported contracts remain available through declared compatibility adapters,
deprecations, and migrations until their removal policy permits otherwise.

## Release truth and preserved inputs

The 0.8 line begins only from the published 0.7.0 source and evidence closeout. A local dirty
checkout, an unmerged branch, or a later Agent Memory or Agent Composition candidate is not an
implicit release dependency. In particular, AM4 and AM6 may be evaluated as bounded inputs, but
they enter 0.8 only through an explicit compatibility review and ordinary public review authority.

The following 0.7 capabilities are released inputs rather than work to rebuild:

- separate Connection, Ontology, Intelligence, and Briefing Agent application services;
- exact governed Domain Activation plan admission for the Activate stage;
- the restart-safe Connect → Map → Watch → Brief → Activate acceptance path;
- inert generated Domain Pack schema, compiler, compatibility, conformance, and activation;
- governed Agent Composition through AC7;
- authorized Agent Memory and Context Manifest lineage through AM3;
- independent World and private Market activation consumers; and
- the exact eleven-tool thin MCP boundary.

0.8 turns those capabilities into one supported experience. It does not pretend they were absent,
nor does it treat provider-free reference strategies and test fixtures as production connectors or
a finished UI.

## Constitutional ownership

### Core owns governed mechanics

Core owns product-scoped identity, temporal and immutable state, graph mechanics, transactions,
provenance, authority, planning, execution admission, assurance receipts, decisions, actions,
outcomes, feedback governance, provider-neutral cognition, and restart/failure semantics. Core
must not know that an opaque reasoning request is producing a Brief or what a domain entity means.

### Intelligence owns the evidence-to-orientation lifecycle

Intelligence owns Observation, Entity projection, Signal, Shift, Case, Brief, Monitor,
Subscription, attention, resolution, delta detection, synthesis policy enforcement, Domain Pack
compilation, activation bindings, feedback proposals, and rebuildable projections over Core state.
Those projections are derived caches, never a second authoritative persistence engine.

### Domain Packs own declarative meaning and policy

Packs own ontology, aliases, source mappings, watched attributes, detector configuration,
materiality, personas, routing, analytical policy, templates, permitted action parameters,
evaluation fixtures, compatibility ranges, and limitations. Packs contain no network access,
secrets, imports, imperative control flow, or executable templates.

### Adapters and strategy plugins own executable specialization

Connectors acquire and translate authorized sources. Action and delivery adapters perform bounded
external effects. Strategy plugins may supply specialized algorithms that cannot be expressed
declaratively. They are separately versioned, explicitly enabled, least-authorized, and do not
become Core or Domain Pack code.

### Applications own the experience

Atrium, domain applications, APIs, agents, workflows, and mature downstream products render and
operate the same public intelligence resources. An application does not gain authority by
rendering a control and does not become another source of truth.

## Compatibility map

| Existing surface | 0.8 canonical interpretation | 0.8 treatment |
|---|---|---|
| `ace.core` | governed mechanics and control plane | preserve and strengthen inward dependency boundaries |
| `ace.intelligence` | evidence-to-orientation domain-neutral lifecycle | preserve; complete the stable resource/API facade |
| `ace.application` | orchestration across Core and Intelligence | preserve as application services; prevent transport and domain nouns from leaking inward |
| `core/engine/orchestration`, `orchestrator`, `cognition` | provider-neutral reasoning and composition substrate | retain behind Core-facing services; stop presenting it as the product category |
| `core/engine/arms` MAKE implementations | downstream artifact-production strategies | freeze as experimental compatibility implementations; migrate behind explicit adapter or strategy contracts |
| SHIP arm and gates | assurance, verification, delivery, and promotion | separate the assurance contract from delivery effects; preserve compatibility while canonical vocabulary changes |
| Living Product Graph | historical name for a bounded product-state projection | retain compatible reads; introduce canonical intelligence/entity-state views without rewriting historical evidence names |
| broad engine MCP | experimental host and compatibility surface | do not confuse with the exact eleven-tool public boundary; route new product work through supported APIs |
| Atrium / Canvas | optional permission-aware intelligence dashboard and control plane | rebuild as a public-API consumer; no direct authority or independent state |
| extension registry | explicitly enabled executable capabilities | preserve compatibility while separating declarative packs, connectors, strategy plugins, and action adapters |

Historical evidence titles and immutable receipts are not rewritten. Canonical current documents,
onboarding, diagrams, runtime labels, and product surfaces must stop teaching the octopus,
partner-team, committee-first, product-manager-toolbox, Living Product Graph as the system category,
or MAKE/SHIP arms as the architecture.

## Bounded delivery sequence

### 0.8A — architecture, compatibility, and release control

- Reconcile the public roadmap and milestone issue to Intelligence OS Realignment.
- Freeze this ownership map, lifecycle, compatibility policy, and release acceptance journey.
- Inventory old canonical vocabulary and every runtime boundary it currently names.
- Define additive migration seams before moving or renaming implementation.
- Keep the eleven-tool public MCP surface unchanged unless a separate contract decision passes.

Exit: maintainers can place every current capability and planned change on one side of a declared
boundary, with an owner, compatibility treatment, landing order, and rollback.

### 0.8B — runtime boundary realignment

- Put generic planning, authorization, execution admission, assurance receipts, and outcome
  governance behind Core services.
- Put Observation-to-Feedback lifecycle behavior behind Intelligence services.
- Move artifact creation and external effects behind explicit adapters or strategy plugins.
- Remove inward imports and duplicate persistence/authority implementations before removing names.
- Add compatibility tests for retained public paths and migrations.

Exit: the dependency graph enforces the constitutional ownership without a domain-specific branch
in Core or Intelligence and without breaking the 0.7 builder journey.

### 0.8C — unified intelligence resource plane

- Publish one supported resource/query facade for Sources, source health, Entities, Observations,
  Signals, Shifts, Cases, Briefs, Monitors, Subscriptions, Decisions, Actions, Outcomes, Feedback,
  evidence lineage, uncertainty, conflicts, semantic revisions, Context Manifests, and memory use.
- Give every resource stable product-scoped identity, authorization, as-of semantics, pagination,
  degraded state, revision lineage, and exact provenance.
- Serve Atrium and at least one machine interface from the same contracts.

Exit: UI-specific state is disposable and can be rebuilt entirely from supported public resource
queries and commands.

### 0.8D — Atrium intelligence experience

- Build an intelligence-review inbox and a briefing-first home.
- Make Intelligence, Opportunities, Agents, Connections, and Strategy first-class navigation;
  treat Work as downstream execution.
- Add source health, entity exploration, Signals/Shifts, Cases, Briefs, evidence lineage,
  uncertainty/conflict, semantic revision diff, Context Manifest and memory lineage, Decisions,
  Actions, Outcomes, Subscriptions, and degraded-state views.
- Make Ask ACE a governed intelligence query over the same resources and citations.
- Retain whiteboard investigation as a Case workspace, never a second source of truth.
- Meet keyboard, screen-reader, contrast, responsive, loading, empty, error, and denied-state gates.

Exit: a user can understand, review, correct, approve, and trace the complete loop without learning
ACE package boundaries or hand-authoring a Domain Pack.

### 0.8E — live cross-domain product proof

- World Intelligence provides the public AI Command Center journey using changing authorized
  sources: model/capability releases, token economics, cybersecurity, regulation/geopolitics,
  investment, market response, and attributable executive commitments.
- Market Intelligence provides the parallel commercial intelligence command-center journey. The
  public pack remains generic; HPE-specific sources, vocabulary, and policy remain a private
  organization overlay/deployment.
- Both applications use unchanged Core + Intelligence APIs and materially different ontology,
  sources, detectors, personas, epistemic policy, and cadence.

Exit: each domain connects sources, maps concepts, activates monitoring, emits or suppresses a
material Shift, produces a cited Brief, records a Decision or bounded Action, admits a later
Outcome, proposes governed Feedback, and reproduces the state after restart.

### 0.8F — release acceptance and publication

- Run focused, full, package, schema, migration, naked-kernel, exact-eleven, restart, installed-
  artifact, accessibility, entitlement, degraded-state, and cross-domain gates.
- Reproduce Atrium and a machine consumer against the same public package and durable state.
- Publish exact artifacts, hashes, workflows, limitations, compatibility, rollback, and consumer
  evidence before marking the milestone passed.

Exit: public `ace-core==0.8.0`, its GitHub release, independent World and Market evidence, and the
reconciled roadmap tell one verifiable story.

## Golden acceptance journey

The signature public demonstration is an AI-focused World Intelligence command center because it
uses changing public evidence and is independently reproducible:

1. Install the public ACE and World packages.
2. Choose the AI Command Center goal and inspect the exact source capabilities requested.
3. Connect at least three materially different authorized sources.
4. Review and edit the cited AI concept model.
5. Review monitors, materiality, audiences, cadence, and source limitations.
6. Receive a cited executive Brief that exposes uncertainty, disagreement, missing evidence, and
   why each item matters.
7. Approve the exact activation and receive an immutable receipt.
8. Admit later evidence and show either a material Shift or an explicit no-material-change result.
9. Ask ACE a follow-up and receive an answer grounded in the same durable evidence and citations.
10. Record a Decision or authorized Action, later Outcome, and governed Feedback proposal.
11. Restart the runtime and reproduce identities, revisions, authority, lineage, and current views.

The Market journey must reproduce the same platform lifecycle without sharing World ontology or
fixtures. A prerecorded or fixture-only UI walkthrough is useful development evidence but cannot
close the release.

## Non-goals and stop conditions

0.8 does not promise multi-tenant collaboration, arbitrary hostile-code sandboxing, marketplace,
managed operation, universal source coverage, unrestricted autonomy, omniscience, or general
real-world causal accuracy. Those claims do not enter through UI language or a domain demo.

Stop and return to review if a change:

- embeds World, Market, HPE, competitor, model, campaign, or another domain noun in Core or
  Intelligence;
- adds a second persistence, authorization, scheduler, secret, or model-routing system;
- lets a UI render, pack, model, or agent grant itself authority;
- requires hand-authored pack files for first value;
- removes a supported contract without a declared compatibility and migration path;
- expands the exact eleven-tool public MCP surface incidentally; or
- folds an unmerged candidate branch into the release without an explicit compatibility gate.

## Landing and rollback order

Each packet lands independently in A → B → C → D → E → F order. Domain work may develop in
parallel after A, but Core accepts only domain-neutral requirements. Every packet must preserve a
reversible compatibility seam and name its rollback before the next packet depends on it. The 0.8
tag is created only after both external consumer gates and public installed-artifact reproduction
pass.

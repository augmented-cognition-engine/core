# ACE vision and manifesto

**ACE, the Intelligence Builder. Build intelligence, not infrastructure.**

Install ACE, connect the sources that matter, and ACE proposes a cited concept model and what to
watch. A source-grounded first briefing appears for review. Explicit approval activates continuous
intelligence, and later evidence and governed feedback improve relevance without silently changing
authority or rewriting history.

ACE supplies both that guided Intelligence Builder experience and the provider-neutral runtime
beneath it. It is becoming an open **Intelligence Operating System**: a user-owned foundation for
building living intelligence and operational applications over shared evidence, ontology,
decisions, actions, and outcomes. Cognition—memory, learning, planning, and reasoning—is essential
substrate, not ACE's public product category. Models and LLMs are optional inference providers;
they are neither the system of record nor the center of the architecture.

The product experience comes first:

```text
Connect → Map → Watch → Brief → Activate
```

The platform beneath that experience preserves authority, provenance, and durable state:

```text
ACE application and onboarding orchestration
                       ↓
        Core + Intelligence bounded contexts
```

Generated, portable domain programs configure the platform without becoming part of either
bounded context:

```text
Domain Pack + Organization Overlay + Capability Bindings
                         ↓
          validate → compile → preview → approve
                         ↓
               Versioned Domain Activation
```

Domain Packs are governed portable programs produced beneath the guided experience, not files a
normal user must hand-author. World Intelligence and Market Intelligence are independent current
falsifiers of the shared platform boundary. Corporate and strategy intelligence, and materially
different future domains, are examples of where the platform may go rather than claims about what
the current release ships. An application, API, agent, workflow, or embedded component may present
the result, but it does not become another source of truth.

## Release and evidence status

This manifesto states principles and architecture, not shipping status. Any past claim — here or
in local working documents — that a given capability, milestone, or version has "shipped" is
historical narrative, not evidence. Public release status of ACE is determined exclusively by the
repository's published git tags, its GitHub releases, and the packages actually available on
PyPI. Local branches, checkouts, changelogs, closeout notes, and this document are not release
evidence and must not be cited as such. Where this manifesto describes behavior in the present
tense, read it as the design contract the codebase is held to, verified against the current
tagged release rather than assumed.

## The constitutional boundary

Core owns the governed machinery. Intelligence owns the canonical semantics and lifecycle of
derived orientation. Domain packs own declarative domain meaning and analytical policy. Explicitly
enabled adapters and strategy plugins own executable specialization.

The boundary is accepted only when a materially different intelligence vertical can be installed,
run, evaluated, upgraded, rolled back, and removed without changing Core or Intelligence.

### Core owns

- product-scoped identity, typed graph mechanics, temporal versions, traversal, persistence, and
  transactions;
- immutable evidence, provenance, lineage, source-time semantics, access labels, and bounded state
  projection;
- opaque freezing and revalidation of caller-selected context, provider-neutral reasoning
  composition, authorized result delivery, domain-neutral grounding primitives and evaluation,
  and inspectable receipts for selection, injection, and provider-declared output reference;
- durable task, decision, action, outcome, correction, memory, and learning lifecycles;
- principals, authorization, policy enforcement, human-review boundaries, idempotency, replay,
  failure semantics, and audit;
- ports for models, storage, events, scheduling, actions, and external capabilities; and
- generic runtime lifecycle, public contracts, and opaque reasoning and execution receipts.

Core is domain-neutral. It must not define intelligence-product lanes or what a competitor,
supplier, malware family, clinical trial, campaign, price move, narrative pivot, or
domain-specific material change means. Core does not know that a generic reasoning request will
become a Brief.

Core keeps full actor, authenticated-session, capability-use, authority-use, grant, and governed
operation material in its private receipt space. A trusted caller receives only an opaque receipt
reference, the authorization time, and the exact governed-head coordinates needed by the atomic
transaction. Such an authorization is a durably accepted command for one exact opaque operation
and subject: later wall-clock expiry does not rewrite that historical acceptance, while a governed
head change prevents its consumption. It is not a continuously current database-commit check.
For the bounded PREPARED synthesis path, that subject is the exact two-record append intent and its
head preconditions must still match when the append transaction consumes the authorization.

### Intelligence owns

- the canonical `Observation`, `Entity`, `Signal`, `Shift`, `Brief`, `Case`, `Monitor`,
  `Subscription`, `PersonaBinding`, and `FeedbackProposal` intelligence contracts and their
  lifecycle projections onto Core;
- the Intelligence Ontology subsystem: pack language, compiler, deterministic intermediate
  representation, catalog, organization overlays, activations, migrations, generated bindings,
  compatibility, and conformance;
- entity-resolution orchestration, pack-scoped facets, rebuildable projections, versioned
  baselines, and numeric, categorical, semantic, and structural detection strategies;
- generic scoring, grouping, suppression, routing, subscription, and attention mechanics;
- grounded Brief assembly over Core reasoning, including typed evidence-closure selection,
  domain claim/support validation, citation construction, alternatives, uncertainty,
  recommendation structure, canonical rendering, and derivation lineage;
- mappings from dispositions and outcomes into governed Core decisions, corrections, evaluations,
  and learning proposals; and
- the stable intelligence resource API and optional reusable analyst-workspace components.

Intelligence owns the signal-to-shift-to-brief machinery. It is domain-neutral but
intelligence-specific: it may know what a Signal, Shift, Brief, baseline, detector, monitor,
subscriber, pack, or activation is. It must not know which entities or changes matter in
marketing, threat, supply chain, science, or any other vertical. It must not own its own database
engine, model router, authorization system, scheduler, secret store, or action executor.

### Declarative domain packs own

- entity, facet, relationship, event, Signal, Shift, decision, action, and outcome type
  declarations;
- attributes, constraints, aliases, identity-resolution exemplars, and adjudication policy;
- source-type declarations, source mappings, and required adapter capabilities;
- watched attributes, baseline definitions, materiality rules, and detector configuration;
- analytical policies, prompts, exemplars, personas, routing preferences, and Brief templates;
- permitted action parameters, eligibility rules, approval requirements, destinations, and outcome
  measures;
- domain evaluation fixtures, expected behavior, and known limitations; and
- explicit schema, compiler, runtime, and capability compatibility ranges.

A pack is immutable declarative content — vocabulary and policy only. It contains no Python or
native code, network or secret access, arbitrary imperative control flow, executable templates, or
mutable remote references. It references versioned capabilities; it never imports their
implementations.

The Intelligence Builder normally generates and revises this content from approved source,
concept-model, monitoring, and briefing proposals. Expert tooling may expose the format directly,
but hand-authored JSON or YAML is never a prerequisite for reaching first intelligence value. A
generated pack receives no special trust: it must pass the same schema, compatibility,
conformance, authority, preview, approval, and activation boundaries as any other pack.

Template ordering semantics are part of the declared schema identity. The legacy
`ace.intelligence.synthesis/v1alpha1` contract retains its historical lexical canonicalization of
required sections; packs that require declaration-order enforcement opt into
`ace.intelligence.synthesis/v1alpha2`. A runtime must never silently reinterpret one contract as
the other.

### Executable adapters and strategy plugins own

- source acquisition, external normalization, delivery, and system writeback;
- specialized resolver or detector algorithms that cannot be expressed safely in pack
  configuration; and
- implementation-specific clients, credentials, compute, and failure handling behind published
  ports.

Executable components are separately versioned, explicitly enabled, least-authorized, observable,
and independently replaceable. Installing a pack never silently enables executable code.

## Ontology language, engine, and toolchain

ACE treats an operational ontology as more than a taxonomy or graph schema. It carries entities,
relations, temporal state, provenance, metrics, signals and shifts, permissions, decisions,
actions, and outcomes:

- **Language:** the universal Intelligence grammar plus pack-declared nouns, relationships, verbs,
  policy, security requirements, and evaluation expectations.
- **Engine:** Core state, graph, authority, execution, and receipt mechanics combined with
  Intelligence resolution, detection, synthesis, and operations.
- **Toolchain:** schema authoring, validation, deterministic compilation, preview, activation,
  migration, conformance, generated SDKs, and lifecycle management.

The ontology is therefore deliberately distributed across responsibilities. It is not the Core
`graph` package, the Intelligence compiler, or the Domain Pack alone.

## Pack, overlay, activation, and solution bundle

These are distinct artifacts:

- A **Domain Pack** is portable, reusable domain meaning and policy.
- An **Organization Overlay** supplies deployment-specific aliases, subjects, thresholds,
  sources, personas, and private policy without forking the pack.
- A **Domain Activation** is the immutable compiled pack plus overlay, adapter and authority
  bindings, compiler version, compatibility result, and revision lock used by a runtime.
- A **Solution Bundle** is an installable product manifest that links one or more packs, overlay
  templates, adapters, strategy plugins, applications, SDKs, and evaluation fixtures. A bundle may
  contain executable dependencies; a Domain Pack may not.

Pack installation and activation are different. Compilation performs no network request, model
call, credential lookup, or silent coercion. Activation is atomic, previewable, authority-checked,
reversible, and version-pinned. Old intelligence remains reproducible against archived activation
revisions.

## The universal intelligence derivation graph

Signal, Shift, and Brief are the three primary user-facing product lanes, not a mandatory conveyor:

```text
evidence → observation → entity state
              │              ├──→ shift ──┐
              └──→ signal ───┴────────────┼──→ case / brief
                                          ↓
                              decision → action → outcome
                                                   ↓
                                      governed feedback proposal
```

- An **observation** says what an attributable source reported or what a measurement recorded.
- A **signal** says something may deserve attention.
- A **shift** says a material change from an explicit baseline has been established.
- A **brief** explains what the current evidence means, what remains uncertain, and which decision
  or action should be considered.

A weak Signal may never establish a Shift. A deterministic delta may establish a Shift before it
is routed as a Signal. A scheduled Brief may summarize current state without a new Shift. A Brief
may synthesize multiple Signals, Shifts, and Cases.

An observation is not a signal. A signal is not a shift. A brief is not an approved decision. A
decision is not an action. An action is not an outcome. Feedback creates proposals and new
revisions; it never rewrites the evidence, intelligence, policy, or receipts that justified an
earlier state.

## Shared-boundary rules

- Core canonicalizes and persists evidence; Intelligence owns typed Observation projections; packs
  declare mappings; adapters capture sources.
- Core owns temporal graph identity, transactions, access, and merge/split mechanics;
  Intelligence owns resolution workflows and rebuildable projections; packs own ontology meaning.
- Core owns durable scheduling primitives, leases, retries, and receipts; Intelligence owns Monitor
  semantics and run orchestration; packs own watch policy; adapters perform I/O.
- Core freezes and revalidates opaque selected context, performs generic reasoning, authorizes
  delivery, and returns inspectable opaque execution receipts; Intelligence selects typed evidence,
  validates claim/support and citation semantics, and owns Brief identity, structure, lineage, and
  canonical rendering; packs own analytical policy and templates.
- Core owns principals and entitlements; packs declare persona archetypes; Intelligence owns the
  versioned binding from a principal or group to a persona, subscription, and attention policy.
- Core owns the exact Decision and Outcome records, named principal, authenticated window,
  action-versus-explicit-no-action distinction, authorization, immutable history, and receipts;
  Intelligence maps those opaque records into an intelligence feedback proposal; packs declare
  eligible personas, routes, dispositions, outcome measures, and bounded adjustments.
- Intelligence proposes scoring, baseline, template, or cognition changes; packs scope which
  parameters are eligible; Core governs approval, persistence, activation, and rollback. A
  proposal has no effect until that separate Core-governed transition commits, and PREPARED
  feedback can never imply a LIVE policy effect.

Authorization is monotonic: a derivative can never be less restricted than its inputs. Persona
ranking may narrow attention but never broaden access. Every delivery rechecks current authority.

## Cognition is governed substrate

Intelligence invokes Core reasoning; Domain Packs teach it vocabulary, policy, examples, and
expected behavior. Core owns how reasoning is composed and bounded, how selected context is
opaquely frozen and revalidated, how results are authorized for delivery, and how domain-neutral
grounding primitives, attribution, evaluation, execution, and receipts connect to later decisions
and outcomes. Intelligence, packs, adapters, and applications must not recreate a parallel
reasoning plane, memory system, provider router, provenance system, decision lifecycle, or outcome
engine.

Memory, learning, planning, and reasoning remain internal platform capabilities. This separation
makes cognition improvable once for every domain while keeping domain meaning with the pack and
domain authority with the organization activating it. It does not position ACE as a reasoning
engine or make any inference provider the product boundary.

## Open-platform principles

1. **One ACE runtime, many domain programs.** Core and Intelligence ship together while preserving
   an executable inward dependency boundary.
2. **Evidence before interpretation.** Preserve exact source identity and provenance before
   deriving intelligence.
3. **Typed meaning, stable mechanics.** Packs declare meaning; Intelligence supplies the shared
   intelligence lifecycle; Core supplies governed state, cognition, and execution.
4. **Nouns and verbs.** A domain model becomes operational only when its entities, decisions,
   actions, outcomes, and authority are explicit.
5. **Human and machine on one governed state model.** People, deterministic logic, statistical
   models, and AI agents use the same contracts and receipts.
6. **Security travels with the object.** Authorization is enforced across evidence, properties,
   derived intelligence, actions, and delivery.
7. **Receipts over claims.** Durability, provenance, model use, review, delivery, and learning are
   true only when inspectable receipts prove them. The same discipline applies to the project
   itself: release claims are true only when tags, releases, and published packages prove them.
8. **Provider and deployment neutrality.** No model, database, compute runtime, cloud, or hosted
   service becomes the product boundary.
9. **Governed learning, never silent self-modification.** Outcomes may propose revisions; authority
   and history remain explicit. Accepting intelligence does not authorize an external action, and
   recording an outcome does not promote its proposed revision.
10. **Open contracts create the ecosystem.** Packs, adapters, bundles, applications, and agents use
    versioned APIs and conformance suites.

## The boundary test

Every Core or Intelligence milestone that changes their shared contract must preserve this
acceptance journey:

1. install ACE, a separately packaged declarative Domain Pack, and explicitly selected adapters;
2. combine the pack with an organization overlay and capability and authority bindings;
3. compile deterministic Pack IR, preview it, approve it, and atomically activate an exact revision;
4. ingest mixed source observations and resolve domain entities;
5. detect, score, route, or deliberately suppress at least one Signal and one material Shift;
6. create an evidence-grounded Brief with alternatives, uncertainty, citations, and limitations;
7. record a human decision, an authorized action or explicit no-action, and an outcome;
8. use governed feedback in a fresh invocation without rewriting prior history;
9. restart the runtime and reproduce identities, versions, access, derivations, and receipts;
10. upgrade and roll back the activation without silently reinterpreting older intelligence;
11. run the same journey with materially different semantic, quantitative, and event-driven packs;
    and
12. prove a zero-line domain-specific diff in Core and Intelligence.

If the final condition fails, the abstraction is incomplete. If the journey passes only because a
lower layer knows the domain's nouns, thresholds, prompts, sources, or action semantics, the
abstraction is false.

Success has a simpler user-facing test: a fresh user reaches a cited first briefing from two
authorized sources without hand-authored configuration; later evidence updates it; corrections
survive restart; and a materially different domain reproduces the journey through unchanged Core
and Intelligence APIs.

## What ACE is becoming

ACE is becoming the open Intelligence Operating System for intelligence products that share one
governed state and cognition runtime, one operational ontology toolchain, one
continuous-intelligence grammar, and one decision/action/outcome loop while remaining owned by
their users and builders.

Its broader trajectory is deliberately staged rather than claimed as shipped:

```text
sources + connectors
    → operational ontology + entity graph
    → continuous intelligence
    → decision + action + outcome loop
    → shared workspace
    → collaboration + tenancy
    → ecosystem + SDK + marketplace + managed options
```

The current release and public roadmap determine how far along that trajectory ACE actually is.
Workspace, collaboration, tenancy, marketplace, ecosystem, and managed-service capabilities do
not become part of an earlier milestone merely because they appear in the vision.

The first domain proves the product. The second proves the abstraction. The ecosystem proves the
platform.

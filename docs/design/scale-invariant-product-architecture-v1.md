# ACE scale-invariant product architecture v1

Status: **current 1.x target contract; subordinate to the public roadmap, product vision, and Core
manifesto**

This document defines how ACE remains one product from a workspace of one principal to a federated
deployment serving many organizations. It adds no current capability claim. Release maturity and
dispatch remain owned by the [public roadmap](../../ROADMAP.md).

## Decision

ACE adopts **single-player useful, multiplayer compounding** as a cross-release architecture
constraint.

The system will not implement separate personal and enterprise cognition models. It will use the
same durable objects, lifecycle transitions, authority semantics, provenance, and receipts at every
scale. Scale changes the number of principals, scopes, policies, participants, and operating cells;
it does not change what a Topic, Decision, Run, Action, Outcome, or memory assertion means.

> **Cardinality changes. Semantics do not.**

The complete product promise is defined in [VISION.md](../../VISION.md). This document freezes the
technical and product constraints needed to keep that promise.

## Why this must be designed before collaboration

If personal operation omits scope, identity, authority, export, or lineage, collaboration later
requires migration into a different data model. If enterprise operation centralizes personal or
team intelligence into one global prompt or graph projection, it destroys least privilege,
ownership, and attributable disagreement.

Therefore 2.0 may deliver the full collaborative organizational experience, but the primitives
that make collaboration safe cannot first appear in 2.0. Every 1.x feature must work inside an
explicit workspace, actor, authority, and lifecycle scope from its first personal implementation.

## Canonical invariant objects

These objects keep the same meaning at every scale:

| Object | Scale-invariant meaning |
|---|---|
| Principal | Attributable human, service, agent, or organization identity |
| Workspace | Governed ownership and administration boundary; a personal workspace is a workspace, not a special schema |
| Topic | Bounded runtime workspace for a question, objective, watch, investigation, or decision |
| Evidence / Observation | Attributable source material and its governed interpretation |
| Intelligence resource | Signal, Shift, Case, Brief, Monitor, or Subscription with exact scope and lineage |
| Decision | Named disposition with reasons, authority, evidence coordinates, and revision history |
| Action | Authorized operation or explicit no-action distinct from the Decision that proposed it |
| Outcome | Observed result under product-owned measures without automatic causal or benefit claims |
| Participant | Human, model, deterministic worker, internal agent, or external agent admitted to bounded work |
| Run | Durable event spine for a unit of work, including status, budgets, recovery, lineage, and typed result |
| Context Manifest | Exact authorized context selected or omitted for one stage or participant |
| Capability / Authority Grant | Narrow permission to use a capability against a scope, subject, destination, budget, and time window |
| Handoff | Typed transfer of bounded context or work between participants or systems |
| Receipt | Immutable evidence that a governed transition, use, delivery, denial, or effect occurred |
| Memory assertion | Governed, source-grounded retained experience that remains separate from authority and policy |

Enterprise capability must extend these contracts through additional policy and topology. It must
not introduce enterprise-only substitutes with different identity or lifecycle semantics.

## Scope model

Every object is owned by an exact product and workspace scope even when only one user exists. Where
applicable it also carries Topic, source, participant, run, and resource-policy coordinates.

The target scope model supports:

```text
deployment
└── tenant / organization boundary
    └── workspace
        └── Topic
            └── run / participant / handoff / artifact
```

This tree expresses default containment, not universal visibility. Cross-workspace and
cross-organization relationships require explicit governed references, policy, and delivery or
federation contracts. A database edge alone never grants visibility or authority.

The same principal may have different roles in different scopes. Group membership, employment,
agent transport, or ownership of a downstream account does not automatically grant ACE authority.

### Tenant of one

The personal default provisions:

- one explicit personal workspace;
- one named owner principal;
- local owner, operator, and decision roles bound to that principal;
- conservative default capability and action policy;
- export, backup, deletion, and later invitation coordinates; and
- ordinary receipts for consequential operations.

The interface may hide this setup. The runtime may not omit it.

### Promotion without migration

Moving from personal to shared operation must add explicit participants, roles, grants, policies,
and administration while preserving object identity and lineage. The supported promotion flow is:

1. inspect the personal workspace and target collaboration boundary;
2. preview participants, role bindings, source visibility, requested capabilities, policies, and
   any changed administration or retention terms;
3. reject incompatible or unauthorized relationships;
4. commit the new sharing and governance revision atomically;
5. preserve all existing Topic, evidence, Decision, Run, memory, and receipt identifiers; and
6. support rollback of the sharing revision without rewriting personal history.

A promotion that requires export/re-ingestion, regenerated identities, or reclassification of
historical authority is not conformant.

## Progressive governance

Review burden is derived from the operation, not only the deployment edition or number of users.

The authority resolver considers at least:

- active principal and role;
- workspace, Topic, resource, and destination scope;
- capability and requested parameters;
- sensitivity and access labels;
- reversibility and expected consequence;
- financial, privacy, security, legal, and production-impact policy;
- time, cost, token, concurrency, and depth budgets;
- required approvals, separation of duties, and conflict-of-interest rules; and
- current activation, definition, policy, and grant revisions.

Low-risk, reversible work may proceed under a standing grant. Higher-consequence work may require a
fresh confirmation, named approval, multiple approvers, verification, or prohibition. Enterprise
policy may narrow this result. No policy may treat installation, connectivity, model output,
participant selection, or transport negotiation as authority.

## Progressive disclosure

The default product surface exposes the smallest useful mental model:

```text
Attention → Topic → bottom line → evidence and reasoning → decision → work → outcome
```

Additional layers appear by need:

| User need | Revealed controls |
|---|---|
| Individual orientation | sources, freshness, uncertainty, next decision, active work |
| Collaboration | ownership, participants, roles, disagreement, handoffs, decisions, outcomes |
| Consequential action | authority, destination, parameters, reversibility, review, verification |
| Builder inspection | Packs, overlays, manifests, context selection, capabilities, conformance |
| Administration | tenants, identity federation, policies, retention, data boundaries, audit, recovery |

Hiding infrastructure must not hide material policy, missing evidence, omitted context,
uncertainty, degraded state, active authority, or consequential effects.

## Federated cognition

ACE does not require one universally readable organizational graph. A large deployment is composed
of governed operating cells that can maintain local state and collaborate through bounded Topics,
references, projections, and handoffs.

Federated operation requires:

- authorization before retrieval ranking or context relevance;
- monotonic restriction across derivation, summary, memory, handoff, and export;
- exact source, workspace, organization, and policy lineage;
- explicit relationship and disclosure contracts across scopes;
- redaction and omission receipts that survive projection and export;
- local ownership of vocabulary, overlay policy, decisions, and retained experience;
- preservation of conflicting claims, dissent, and minority views;
- scoped search and aggregation that cannot infer prohibited detail through counts or metadata;
- no ambient authority inherited across agent, team, tenant, or transport boundaries; and
- portable inspection and recovery without surrendering canonical ownership to a hosted control
  plane.

Cross-scope composition should bring the smallest authorized information to the Topic. It should
not copy each contributing workspace into a new ungoverned memory store.

## Runtime topology

Scale profiles change operational topology while preserving semantic behavior:

| Profile | Expected topology | Required semantic guarantees |
|---|---|---|
| Local individual | Single-user host and local or user-controlled storage | Explicit workspace/principal scope, durable identity, export, restart, receipts |
| Managed individual | Managed host with private workspace | Equivalent ownership and portability, declared provider/data boundaries, recovery |
| Team | Shared managed or self-hosted deployment | Role-aware Topics, concurrent participants, sharing revisions, isolation, handoff recovery |
| Enterprise | Dedicated or managed multi-cell deployment | Identity federation, policy, audit, HA, backup/restore, data residency, workload isolation |
| Federation | Multiple independently administered deployments | Signed exchange, minimized projections, policy negotiation, revocation, no assumed global authority |

The reference implementation may add distributed stores, queues, caches, and observability
systems only behind stable ports. A projection, index, cache, analytics export, or hosted control
plane never becomes a second source of truth.

## Experience at representative scales

### One developer

1. Create or open a Code Intelligence Topic.
2. ACE resolves repository, issue, architecture, test, incident, and prior-decision context.
3. ACE explains the bottom line, uncertainty, and likely blast radius.
4. The developer decides and authorizes a bounded coding handoff.
5. An external coding agent receives a narrowed workspace, context, tools, and budget.
6. Changes, tests, review, cost, failures, and result return through typed receipts.
7. The developer accepts, corrects, or rejects the work; later product evidence records the
   Outcome.

### One business owner

1. A standing Topic watches selected customer, financial, operational, and external sources.
2. ACE surfaces a material change and explains why it matters to the owner's business.
3. It frames alternatives, constraints, uncertainty, and the decision required.
4. The owner records a disposition and authorizes bounded handoffs to existing business tools.
5. ACE tracks acknowledgments, commitments, measures, and later Outcome.
6. Verified experience may create a proposal to improve future routing, procedure, or memory.

### Ten-person team

The same flow adds shared ownership, participant roles, visible disagreement, task and handoff
coordination, team-level memory, approval rules, and onboarding. It does not replace personal
Topics or force every source into team visibility.

### Ten-thousand-person organization

The same flow spans federated organizational, product, design, code, data, and operational scopes.
Organization policy constrains access and authority; Topics connect the affected slices. Leaders
may inspect the bottom line and decision lineage while detailed evidence remains governed by its
owning teams. Cross-team action and outcome attribution use the same participant, handoff, Action,
Outcome, and receipt contracts used by the individual.

## Product packaging constraints

Packaging may add managed operation; it may not fork semantics or user ownership.

- ACE Core must remain genuinely useful for a self-hosting individual.
- Reasoning quality, durable object identity, export, and inspectability are not enterprise-only.
- Team packaging adds collaboration, shared operation, and managed convenience.
- Enterprise packaging adds identity, policy, isolation, reliability, recovery, federation, and
  support.
- A hosted service must disclose capability differences and support tested portability.
- Connectors, Packs, models, and external agents remain replaceable contributions rather than
  edition-specific sources of truth.

## Cross-release requirements

### 1.1 — Code Intelligence and bounded external work

- external agents are explicit principals and never inherit the caller's ambient authority;
- Code Intelligence proves an individual developer journey, concurrent human/agent work,
  propagation verification, linked repair, reusable-architecture review, and `ACE Builds ACE`;
- repair, architecture, and future-work improvement retain distinct lifecycle and authority
  semantics at personal, team, enterprise, and federated scale; and
- every downstream handoff is safe to use unchanged inside a later team or organization Topic.

### 1.2 — personal proof and collaboration-ready foundations

- Personal Intelligence proves useful operation for one without organization administration;
- every future Topic is share-ready by construction but private by default;
- personal-to-shared promotion remains previewable and identity-preserving; and
- progressive disclosure keeps Packs, manifests, and policy out of the default individual path.

### 1.3 — intelligence operations foundation

- canonical run and participant events include explicit principal, workspace, Topic, authority,
  budget, lineage, and settlement coordinates;
- one-person defaults use ordinary contracts rather than bypasses; and
- restart, cancellation, recovery, evaluation, upgrade, and export preserve those coordinates.

### 1.4 — Intelligence Pack Kit and Topic semantics

- Pack and Topic contracts preserve one-person usefulness and future collaboration coordinates;
- domain and focused Topic packs use the same governed activation and ownership model; and
- progressive disclosure prevents pack machinery from becoming the default product experience.

### 1.5 — organization and connected-product semantics

- organizational maps and overlays add roles, ownership, policy, and cross-system relationships
  without replacing personal or team objects;
- shared Topics preserve authorization, disagreement, and decision lineage; and
- the connected-product journey proves one decision across multiple governed scopes.

### 1.6 — experience-based improvement

- memory and improvement remain scoped to the exact principal, workspace, Topic, participant, and
  policy coordinates that permit later use;
- organizational aggregation cannot silently convert local experience into global policy; and
- matched evaluation covers at least individual and multi-participant compositions; and
- repeated Code Intelligence experience can propose agent, procedure, context, routing, framework,
  Pack-policy, or verification revisions only after current-change repair and architecture
  opportunities remain separately disposed.

### 1.7 — deployment and federation

- local, managed, dedicated, and federated profiles preserve equivalent durable semantics;
- export, restore, upgrade, revocation, and disaster recovery preserve identity and lineage; and
- cross-deployment exchange is bounded, policy-aware, and independently revocable.

### 2.0.0 — full collaborative organizational experience

- multiple teams complete a permission-sensitive Topic through Outcome and governed learning;
- identity, dissent, privacy, delegated authority, handoff, recovery, and portability remain
  intact; and
- organization-wide views aggregate only what each viewer is authorized to inspect.

## Conformance journey

A release family may claim scale-invariant operation only when the same frozen journey proves:

1. a new individual creates a useful Topic with no organization configuration;
2. the individual reaches a grounded Decision and completes one bounded handoff;
3. restart and export preserve the Topic, context-use, Decision, work, Outcome, and receipt chain;
4. a collaborator is invited through a previewable sharing revision with no re-ingestion or ID
   replacement;
5. one source remains private while authorized shared context materially contributes to later work;
6. a denied participant, capability, source, or destination fails closed without leaking metadata;
7. disagreement is preserved through Decision rather than summarized into false consensus;
8. a high-consequence action requires stronger review than a low-risk action independent of
   deployment size;
9. the Topic survives movement between two supported deployment profiles without losing ownership,
   lineage, or inspectability; and
10. a matched evaluation reports quality, outcome, latency, cost, failures, and degraded states at
    both individual and multi-participant cardinalities;
11. Code Intelligence distinguishes an incomplete current change from a reusable-architecture
    opportunity and from a proposal to improve future work;
12. concurrent participants receive explicit stale-context and overlapping-work dispositions, and
    linked repair is reverified without inheriting refactor or learning authority; and
13. the `ACE Builds ACE` journey proves self-application without self-approval, self-merge,
    self-release, self-promotion, or authority expansion.

Scale benchmarks remain separately required. Passing semantic conformance at two cardinalities
does not establish capacity, latency, availability, or distributed-consistency claims for 10,000
users.

## Deliberate non-goals

- one global organization prompt or universal readable graph;
- collaboration implemented as shared chat history;
- personal mode that bypasses identity, authority, provenance, or receipts;
- enterprise-only intelligence quality;
- automatic consensus or policy promotion from aggregate behavior;
- one generic improvement action that collapses repair, architecture and future-work learning;
- self-application as evidence of self-approval or elevated authority;
- participant count as evidence of reasoning quality;
- seat count as the authority or governance model; and
- a second enterprise runtime, database, memory plane, or object model.

## Decision test

Every proposed 1.x or 2.0 capability must answer:

> Can this create immediate value inside a private workspace of one, accept additional principals
> and policy without migration, and operate across federated scopes without changing its durable
> meaning or widening authority?

If not, it is either incomplete or belongs outside ACE.

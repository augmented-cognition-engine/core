# ACE 0.7 Intelligence Builder onboarding sequence (v1)

**Status:** cumulative product contract and dispatch plan. 0.7A is the stable
compiler/conformance candidate in draft PR #100. 0.7B Connect is the next implementation packet.
0.7C–0.7E remain planned until their own code and evidence pass. This document does not claim the
full onboarding journey is built.

## Product promise

**ACE, the Intelligence Builder. Build intelligence, not infrastructure.**

The visible journey is exactly:

```text
Connect → Map → Watch → Brief → Activate
```

A builder installs ACE, connects authorized sources, reviews the concept model ACE proposes,
chooses what to watch, sees a cited first briefing, and activates only after approving the exact
scope and effects. ACE keeps the intelligence current; feedback improves relevance without silently
changing authority.

Users do not need to understand Core, Intelligence, Domain Packs, compilers, schemas, JSON/YAML, or
agent plumbing to reach first value. Those implementation boundaries remain public and inspectable
for experts, but sit below the product journey. Domain Packs are generated, governed, inert
artifacts—not hand-authored customer setup.

## Bounded 0.7 sequence

| Packet | Visible stage | First-class agent | Bounded outcome |
|---|---|---|---|
| 0.7A | substrate | Activation dependency | Stable generated-pack schema, compiler compatibility, deterministic conformance, exact receipts, and fail-closed activation boundary. |
| 0.7B | Connect | Connection Agent | Supported source options, permission/scope and source-profile proposals, explicit access disposition, and resumable session state. |
| 0.7C | Map | Ontology Agent | Editable, cited concept-model proposal with entities, aliases, relations, attributes, terminology, exclusions, confidence, and disagreement. |
| 0.7D | Watch | Intelligence Agent | Watched attributes/relations, baselines, detectors, materiality, audiences, routing, cadence, and monitor proposals. |
| 0.7D | Brief | Briefing Agent | First grounded briefing preview with citations, uncertainty, disagreement, omissions, and why each item matters. |
| 0.7E | Activate | Activation Agent | Generated inert Domain Pack, exact permission/effect preview, human/Core approval, conformance, activation, restart/update/feedback proof, and independent consumer convergence. |

Each packet reuses the previous public contracts unchanged. A later packet may not inherit a pass,
widen authority, or collapse an earlier agent boundary merely because one product surface presents
the journey as one conversation.

## Shared onboarding session state machine

The durable primary states are:

```text
goal_selected
→ sources_connecting
→ sources_ready
→ concept_model_proposed
→ concept_model_approved
→ intelligence_model_proposed
→ intelligence_model_approved
→ first_briefing_ready
→ activation_pending
→ active
```

Any nonterminal step may enter `blocked` with exactly one resumable reason:

- `failed_connector`;
- `insufficient_permission`;
- `low_confidence_mapping`;
- `conflicting_sources`; or
- `no_material_shifts`.

A blocked session records the exact prior stage, failed proposal/handoff identity, safe diagnostic,
and retry eligibility. `blocked → retrying → prior stage` creates new append-only revisions; it never
rewrites an earlier proposal or implies an approval. Opaque session and correlation IDs, proposal
references, dispositions, and exact transition receipts persist through Core's public opaque-record
boundary. Agent-facing concepts never become fields in Core receipt contracts.

| Transition | May propose | Required disposition |
|---|---|---|
| create → `goal_selected` | product/user | Human-selected goal or explicitly supplied product policy. |
| `goal_selected` → `sources_connecting` | Connection Agent | None; proposal-only. |
| `sources_connecting` → `sources_ready` | Connection Agent | Human/Core approval of the exact source-scope proposal before test/sample effects. |
| `sources_ready` → `concept_model_proposed` | Ontology Agent | None; proposal-only. |
| `concept_model_proposed` → `concept_model_approved` | user/product | Human/Core disposition over the exact concept-model identity. |
| `concept_model_approved` → `intelligence_model_proposed` | Intelligence Agent | None; proposal-only. |
| `intelligence_model_proposed` → `intelligence_model_approved` | user/product | Human/Core disposition over the exact intelligence-model identity. |
| `intelligence_model_approved` → `first_briefing_ready` | Briefing Agent | None; effect-free preview over already approved bounded inputs. |
| `first_briefing_ready` → `activation_pending` | Activation Agent | None; exact activation-plan proposal only. |
| `activation_pending` → `active` | Activation Agent may request | Core admission after human approval, current authority/grant resolution, exact 0.7A conformance, and activation revalidation. |

## Agent contracts

All five agents are separate versioned domain-neutral services. They may share one orchestration
surface and session store, but each has its own input, proposal output, handoff identity, authority
boundary, and failure semantics.

### 1. Connection Agent — Connect

**0.7B versioned boundary:** `ConnectionAgent` with
`ace.application.source-option-catalog/v1alpha1`,
`ace.application.source-scope-proposal/v1alpha1`,
`ace.application.source-profile-proposal/v1alpha1`, and the shared
`ace.application.intelligence-builder-session-revision/v1alpha1` handoff contract.

**Inputs**

- opaque onboarding session/correlation and selected-goal references;
- connector-described source-option catalog from explicitly registered host connectors;
- user-selected source options, requested permission/scope, and bounded sample limits; and
- an external approval-receipt reference for any connection test or sample effect.

**Proposed outputs**

- versioned source-option catalog;
- exact source-scope proposal with requested permissions, scopes, allowed effects, and sample bound;
- redacted source-profile proposal containing field shape, source/sample digests, provenance,
  confidence, limitations, and no credential material; and
- handoff identity binding the source-scope and source-profile proposal digests.

**Allowed effects**

- enumerate options already exposed by a registered host provider;
- after exact approval, ask that provider to test one approved connection and return one bounded,
  redacted shape sample; and
- persist opaque proposal/session records through Core.

**Forbidden effects and authority boundary**

- never invent, read, return, log, or persist credentials;
- never discover connectors outside the explicit host registry;
- never widen permission, source, tenant, time, field, or sample scope;
- never persist authoritative connector configuration, schedule work, deliver output, or activate;
- resolve approval through Core for the exact source-scope proposal before any test/sample; and
- treat provider transport and credential handling as host-owned.

**Failure/retry and handoff**

- connector failure blocks as `failed_connector`;
- denied, expired, mismatched, or widened scope blocks as `insufficient_permission`;
- retry returns to `sources_connecting` with a new proposal identity; and
- successful handoff is the exact source-profile proposal consumed by the Ontology Agent.

0.7B owns this service and its provider-free reference fixtures.

### 2. Ontology Agent — Map

**0.7C dispatch contract:** a separate `OntologyAgent` service owns the planned
`ace.application.concept-model-proposal/v1alpha1` output and consumes source-profile references
without gaining connector authority. 0.7C must freeze and publish that schema before implementation
can be accepted.

**Inputs**

- approved source-profile handoff identities and admitted bounded samples;
- selected goal, product terminology preferences, and explicit exclusions; and
- optional provider/model output treated as untrusted proposal input.

**Proposed outputs**

- versioned, editable concept-model proposal;
- cited entities, aliases, relations, attributes, terminology, exclusions, unresolved mappings,
  confidence, and source disagreement; and
- candidate inert ontology and source-mapping modules plus a handoff digest.

**Allowed effects**

- deterministic/provider-free mapping from declared fixture shapes;
- optional provider-assisted proposal generation followed by exact validation; and
- opaque proposal/session persistence through Core.

**Forbidden effects and authority boundary**

- no source access, connector execution, silent ontology mutation, Domain Pack activation, or grant
  creation;
- no claim that a low-confidence or disputed mapping is approved fact; and
- only human/Core disposition may move `concept_model_proposed` to `concept_model_approved`.

**Failure/retry and handoff**

- inadequate mapping confidence blocks as `low_confidence_mapping`;
- incompatible evidence blocks as `conflicting_sources`;
- edits create new proposal identities and invalidate stale dispositions; and
- successful handoff is the exact approved concept-model proposal consumed by the Intelligence
  Agent.

0.7C owns this service.

### 3. Intelligence Agent — Watch

**0.7D dispatch contract:** a separate `IntelligenceAgent` service owns the planned
`ace.application.intelligence-model-proposal/v1alpha1` output and consumes the exact approved
concept-model handoff. It does not share the Briefing Agent output contract.

**Inputs**

- approved concept-model handoff;
- selected goal and admitted source profiles;
- bounded baseline/sample evidence; and
- user preferences for relevance, audience, and cadence.

**Proposed outputs**

- versioned, editable intelligence-model proposal;
- watched attributes and relationships, baselines, shift detectors, materiality thresholds,
  personas/audiences, routing, cadence, monitor definitions, and silence policy;
- explicit distinctions among observation, claim, inference, disagreement, and unknown; and
- candidate inert detection/persona/synthesis/overlay modules plus a handoff digest.

**Allowed effects**

- provider-free deterministic fixture policies;
- optional provider-assisted proposal generation followed by exact schema checks; and
- effect-free detector/routing previews over approved samples.

**Forbidden effects and authority boundary**

- no scheduling, source read, subscription binding, delivery, persistence of LIVE observations,
  activation, or self-approval; and
- only human/Core disposition may move `intelligence_model_proposed` to
  `intelligence_model_approved`.

**Failure/retry and handoff**

- no qualifying change is `no_material_shifts`, not fabricated alert content;
- conflicting baselines or evidence block as `conflicting_sources`;
- edits produce new identities; and
- successful handoff is the exact approved intelligence-model proposal consumed by the Briefing
  Agent.

0.7D owns this service.

### 4. Briefing Agent — Brief

**0.7D dispatch contract:** a separate `BriefingAgent` service owns the planned
`ace.application.first-briefing-preview/v1alpha1` output and delegates canonical Brief assembly to
the existing synthesis boundary. It consumes, but does not mutate, the Intelligence Agent handoff.

**Inputs**

- approved concept- and intelligence-model handoffs;
- approved source samples/Observations and exact provenance;
- selected audience/persona and routed synthesis policy; and
- deterministic fixture draft or optional model-generated structured draft.

**Proposed outputs**

- versioned first-briefing preview using the existing canonical Brief assembly;
- citations, source disagreement, uncertainty, unknowns, omissions, confidence, and why each item
  matters; and
- exact support, policy, Pack IR candidate, and preview handoff identities.

**Allowed effects**

- provider-free canonical synthesis over fixtures;
- optional provider inference constrained by existing structured Brief validation; and
- persistence of preview proposals only.

**Forbidden effects and authority boundary**

- no new source access, scheduling, subscription binding, delivery, LIVE persistence, activation,
  or suppression of disagreement/unknowns; and
- the first preview must work before optional delivery or model integrations are configured.

**Failure/retry and handoff**

- no material shifts produces an explicit cited/sourced silence result;
- missing supports or policy mismatch fails closed through existing synthesis diagnostics; and
- successful handoff binds the exact first-Brief preview consumed by the Activation Agent.

0.7D owns this separate service; it is not part of the Intelligence Agent.

### 5. Activation Agent — Activate

**0.7E dispatch contract:** a separate `ActivationAgent` service owns the planned
`ace.application.intelligence-activation-plan/v1alpha1` proposal and consumes the exact approved
handoffs from the other four agents. Existing 0.7A conformance and activation receipts remain the
authoritative terminal evidence; this service does not define replacement receipts.

**Inputs**

- exact approved source-profile, concept-model, intelligence-model, and first-Brief handoffs;
- current capability/authority bindings and host contract identities;
- human approval-receipt reference over the exact activation plan; and
- current 0.7A compiler/conformance boundary.

**Proposed outputs**

- generated inert Domain Pack/configuration and exact Pack IR;
- compatibility, compilation, conformance, permission/effect, monitor, subscription, and activation
  plan preview;
- activation request that binds the approved plan identity; and
- terminal activation/bootstrap receipts with restart coordinates.

**Allowed effects**

- generate inert pack bytes from approved proposals;
- call the unchanged 0.7A compiler and provider-free conformance helper;
- request human/Core disposition; and
- after exact approval and current grant resolution, call existing activation and monitoring
  admission services.

**Forbidden effects and authority boundary**

- cannot approve itself, create grants, widen scope, bypass conformance, execute connector
  transport, schedule/deliver without separate authority, or rewrite prior proposals/receipts;
- activation is Core-owned durable state; the agent only proposes and invokes the governed boundary;
  and
- a Domain Pack remains inert throughout.

**Failure/retry and handoff**

- any stale handoff, failed conformance, changed permission/effect scope, denied approval, expired
  grant, or activation conflict fails before live effect;
- retry creates a new activation-plan identity; and
- successful handoff is the exact Core activation revision/receipt used by monitors and
  subscriptions.

0.7E owns this service and the cumulative proof.

## Cumulative full-demo acceptance

A fresh installed artifact using provider-free fixtures must eventually:

1. select a goal/template;
2. connect at least two authorized fixture sources;
3. generate and edit a cited concept-model proposal;
4. generate and edit monitors, materiality, cadence, and persona/audience proposals;
5. produce a first briefing with provenance, uncertainty, disagreement, and why each item matters;
6. approve exact activation scope and activate through 0.7A;
7. restart and resume with stable identities;
8. admit a later Observation and show a resulting update or explicit no-material-shift result;
9. record user feedback without silently changing authority; and
10. reproduce through one supported public application/API surface with unchanged platform APIs
    across independent World and Market consumers.

The evidence reports time to first Brief, user edits, permission corrections, blocked/retry paths,
restart identity, citation coverage, disagreements/unknowns, activation scope, and limitations in
outcome language. Compiler knowledge is not an acceptance criterion.

## Cross-cutting invariants

- Core owns durable opaque state, provenance, authority, receipts, identity, restart, and failure
  semantics.
- Intelligence owns domain-neutral pack, detection, routing, monitor, and Brief contracts.
- Product/application orchestration owns the five-agent journey but cannot bypass Core or
  Intelligence.
- Connectors retain network, credential, transport, and source-translation effects.
- Scheduling and delivery remain host-owned and separately authorized.
- Provider use is optional; every packet has deterministic provider-free fixtures.
- Domain nouns never enter Core/Intelligence implementation or tests.
- No onboarding packet adds frontend code to Core.
- The thin MCP surface remains exactly eleven tools and naked-kernel startup remains valid.
- No packet closes issue #39, E2, SI3, or 0.7.0 without its own evidence and reconciliation.

## 0.7B Connect acceptance

The next stacked implementation packet passes only when:

1. a public application service returns deterministic options from an explicitly supplied host
   provider;
2. the Connection Agent produces a content-addressed permission/scope proposal with only connection
   test and bounded-sample effects;
3. provider transport is never called before Core resolves exact approval;
4. the returned source profile cannot widen approved permissions, scopes, sample size, connector,
   or source identity;
5. credentials and authoritative connector configuration cannot enter the public contracts;
6. denied access, scope widening, forbidden effects, and connector failure fail closed and persist
   resumable blocked state;
7. stale proposals cannot be used after a revised scope proposal;
8. a fresh service instance reloads and resumes the exact append-only session chain;
9. no UI, scheduling, delivery, pack activation, or model provider is required; and
10. focused tests, installed-wheel import, naked-kernel, and exact eleven-tool checks pass.

0.7B does not claim Map, Watch, Brief, Activate, the full demo, or consumer convergence.

## Rollback

Every onboarding packet is additive above 0.7A. Rollback disables its application entry points and
leaves stable pack contracts plus immutable proposal, disposition, and activation history intact.
No rollback silently activates, deletes, rewrites, or reinterprets a prior source scope, concept
model, intelligence model, Brief preview, grant, approval, pack, or activation revision.

# ACE 0.7D Intelligence Builder Watch + Brief work packet (v1)

**Status:** implementation candidate stacked on the 0.7C Map candidate in draft PR #103. This
packet implements Watch + Brief only. It does not claim Activate, independent consumer proof, Agent
Memory, Agent Composition, the cumulative onboarding demo, or 0.7.0.

## Outcome

An exact approved 0.7C concept model plus bounded observations from two authorized sources produces
an editable intelligence-model proposal covering what to watch, baselines, detectors, materiality,
audiences, routing, cadence, and suppression/grouping. A human/Core disposition approves one exact
immutable revision. A separate Briefing Agent then produces a deterministic cited first Brief that
shows material items, provenance, uncertainty, disagreement, unknowns, why each item matters, and
freshness. A fresh service reopens the exact evidence, proposal, disposition, Brief, receipts, and
session handoff.

Neither service creates an authoritative monitor, subscription, signal, shift, decision, action,
delivery, activation, or grant.

## Reuse audit

| Need | Reused owner and primitive | 0.7D responsibility |
|---|---|---|
| Durable artifacts/restart | Core `ImmutableRecordStore` through the generic onboarding artifact/session service | Persist opaque observation-set, proposal, disposition, and Brief-preview payloads with append-only receipts. |
| Human approval | Core `CoreAuthorityResolver` and `ResolvedApprovalReceiptV1` | Resolve the exact current intelligence-model proposal before `intelligence_model_approved`. |
| Evidence values | Intelligence `CanonicalJsonValueV1Alpha1` and existing immutable Observation patterns | Carry bounded, deeply immutable pre-activation observation bodies without pretending they are activated LIVE resources. |
| Monitor/detector semantics | Existing monitor, numeric-delta, categorical-transition, materiality, persona, routing, cadence, subscription, and suppression concepts | Emit inert pre-activation proposal declarations only. Existing activation-bound runtime contracts remain unchanged. |
| Brief grounding | Existing canonical Brief/citation/claim/epistemic closure patterns | Emit a separately versioned preview whose items bind exact approved statements and exact admitted citations. |
| Models | Host-supplied strategy ports | Optional proposal/synthesis providers; provider-free deterministic strategies remain the reference path. |

Existing runtime `ObservationV1Alpha1`, `MonitorV1Alpha1`, subscriptions, sensing windows, and
canonical `BriefV1Alpha1` are activation-bound. Reusing them directly before 0.7E would fabricate
an activation revision or authoritative runtime state, so 0.7D reuses their validation patterns
and value primitives but keeps onboarding outputs explicitly inert.

Core continues to see only generic record space/kind, payload contract string, opaque payload,
transaction receipt, and approval subject. No Intelligence Agent, Briefing Agent, monitor, signal,
shift, or Brief field was added to a Core receipt contract.

## Two separate versioned boundaries

### Intelligence Agent — Watch

- `ace.application.authorized-observation-set/v1alpha1` binds at least two sources, exact 0.7B
  profile/sample identities, bounded canonical evidence bodies, source disagreement, unknown
  fields, admission/as-of times, confidence, and content identity.
- `ace.application.intelligence-model-proposal/v1alpha1` binds the exact approved 0.7C handoff and
  observation set to watched attributes/relationships, baselines, supported detectors,
  materiality, audiences, routing/cadence, suppression/grouping, epistemic statements, citations,
  conflicts, unknowns, exclusions, confidence, revision lineage, computed semantic diff, and
  content identity.
- `ace.application.intelligence-model-disposition/v1alpha1` binds one human/Core approval to one
  exact proposal revision. Its identity is the exact Briefing Agent handoff.
- `IntelligenceAgent` separately owns observation admission, propose, revise, and approve.
  `IntelligenceModelStrategy` receives no connector, scheduler, delivery, activation, persistence,
  or authority capability.

### Briefing Agent — Brief

- `ace.application.briefing-derivation/v1alpha1` binds the exact concept proposal/disposition,
  intelligence proposal/disposition, observation set, session, and correlation identities.
- `ace.application.first-briefing-preview/v1alpha1` binds that derivation to an executive summary,
  material items, why-it-matters text, exact citations, epistemic classification, uncertainty,
  alternatives/counterevidence, attention/questions, as-of freshness, and content identity.
- `BriefingAgent` separately owns effect-free synthesis and preview persistence.
  `BriefingStrategy` receives no delivery, decision, action, activation, or authority capability.

## Authority, edits, and failure semantics

- Both agents are proposal-only. Only exact human/Core disposition advances
  `intelligence_model_proposed → intelligence_model_approved`.
- Intelligence-model edits create immutable identities, bind exact prior material, and carry the
  service-computed semantic diff. Silent materiality/threshold changes fail closed.
- Invalid/widened evidence, unsupported detector/effect fields, fabricated citations, stale
  revisions, self-approval, unapproved claims, citation gaps, and hidden disagreement fail before
  output persistence.
- Low-confidence intelligence proposals block as `low_confidence_intelligence_model`; blocking
  evidence conflicts use `conflicting_evidence`; incomplete closure uses
  `insufficient_evidence_closure`; stale handoffs use `stale_intelligence_input`; no material items
  use `no_material_shifts`; and strategy failure uses `synthesis_failure`.
- Every blocked path preserves the exact resume stage and uses append-only
  `blocked → retrying → prior stage` revisions without implying approval.

## Acceptance

The candidate passes only when:

1. the exact approved 0.7C handoff and two authorized neutral sources produce a useful provider-free
   Watch proposal with explicit disagreement and unknowns;
2. a human edit changes one materiality threshold through exact lineage and computed diff;
3. exact Core-resolved approval advances only the edited revision;
4. a separate provider-free Briefing Agent produces one first Brief with materiality, provenance,
   uncertainty, disagreement, counterevidence, unknowns, why-it-matters, and freshness;
5. restart reopens exact evidence, intelligence model/disposition, Brief, receipts, and session;
6. two installed-wheel directories reproduce the same exact identities;
7. focused negative controls and unchanged 0.7A–0.7C, naked-kernel, package, and eleven-tool MCP
   boundaries pass; and
8. the full non-e2e gate passes in the linked worktree without deselecting the historical TP0
   baseline assertions.

## Ancillary test-harness portability repair

The frozen TP0 baseline hashes its adapter source, so that historical module remains byte-for-byte
unchanged. A read-only test-harness helper resolves `.git` directories, linked-worktree `.git`
files, `commondir`, loose refs, packed refs, and detached HEAD. The baseline tests inject that
resolver and retain every original assertion and frozen hash. A synthetic regression exercises
both ordinary and linked layouts.

## Downstream handoff — not implemented here

- **0.7E Activation** consumes the exact approved concept-model and intelligence-model
  dispositions plus the exact first-Brief identity. It may translate approved inert proposals into
  generated Domain Pack/config material, but must re-enter the 0.7A compiler/conformance and Core
  activation/authority boundaries without trusting 0.7D receipts as activation evidence. It owns
  a sibling activation-plan-bound admission contract: Core approval targets that plan's immutable
  ID and digest, admission separately revalidates embedded spec/effect material and persists all
  coordinates, and upgrade/rollback/reactivation require separate plans and authority. The 0.7D
  session retains exact source scope/profile, concept, observation, intelligence, disposition, and
  Brief references/bodies so 0.7E can construct that plan without widening this packet. Only after
  validating an exact committed activation may 0.7E construct
  `ace.application.domain-activation-commit-reference/v1alpha2`, permanently marked
  `historical_reference` and `live_authority=false`; 0.7D proposal/preview identities remain
  activation-neutral and never emit that reference.
- **0.7F Agent Memory** may observe the opaque session/artifact identities and user dispositions,
  but must not mutate 0.7D proposal bodies, thresholds, citations, authority, or Core receipt
  schemas. Memory use requires its own versioned provenance and disposition contracts.
- **0.7G Agent Composition** may orchestrate the public proposal services and handoff identities,
  but must preserve the separate agent boundaries, exact state transitions, human dispositions,
  and host-owned effects. Composition cannot become implicit approval or authority delegation.

## Rollback

Stop composing the additive Watch/Brief services and exports. Existing opaque Core records remain
immutable history. Rollback performs no source read, scheduler/delivery action, monitor binding,
decision/action, grant, pack activation, or record deletion, and leaves 0.7A–0.7C behavior intact.

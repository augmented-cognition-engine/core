# ACE 0.7C Intelligence Builder Map work packet (v1)

**Status:** implementation candidate stacked on the 0.7B Connect candidate in draft PR #102.
This packet implements Map only. It does not claim Watch, Brief, Activate, independent consumer
proof, or the cumulative 0.7 onboarding demo.

## Outcome

Two approved 0.7B source profiles plus a user goal and intent produce an editable, cited concept
model. An edit creates a new immutable proposal revision with exact lineage and semantic diff. A
human/Core approval over the exact current revision advances the session to
`concept_model_approved`, and a fresh service reopens the same approved proposal, disposition, and
handoff identities.

Normal users never author ontology JSON or learn compiler mechanics. The concept model is a
proposal beneath the guided **Map** stage. It is not authoritative ontology state or a Domain Pack
activation.

## Reuse audit

| Need | Reused owner and primitive | 0.7C responsibility |
|---|---|---|
| Source handoff | 0.7B `SourceProfileProposalV1` plus exact session artifact reference | Consume and revalidate the exact persisted source-profile body without changing source scope. |
| Durable proposals and restart | Core `ImmutableRecordStore` through the 0.7B generic onboarding artifact/session service | Persist opaque concept proposal/disposition payloads and exact append-only handoffs. |
| Human approval | Core `CoreAuthorityResolver` and `ResolvedApprovalReceiptV1` | Resolve approval for the exact current proposal revision before advancing state. |
| Domain Pack compiler/activation | 0.7A stable boundary | No use in 0.7C; reserved unchanged for the Activation Agent. |
| Models | Host-supplied `ConceptModelStrategy` port | Optional untrusted proposal generation; deterministic provider-free strategy is the public fixture. |

Core continues to see only its generic record space, record kinds, payload contract string, opaque
payload, transaction receipt, and approval subject. It does not learn Ontology Agent, entity,
relationship, citation, terminology, conflict, or concept-model fields.

## Public contract and service

- `ace.application.concept-model-proposal/v1alpha1` carries exact source-profile identity, goal,
  user intent, citations, entity types, attributes, relationship types, aliases, terminology,
  exclusions, conflicts, unknowns, confidence, revision lineage, semantic diff, and content
  identity.
- `ace.application.concept-model-disposition/v1alpha1` records one exact approved proposal,
  actor, Core approval receipt reference, and content identity.
- `OntologyAgent` separately owns propose, revise, and approve. It is not collapsed into the shared
  session service or Connection Agent.
- `ConceptModelStrategy` is a host port. It receives already admitted source-profile material and
  cannot receive connector or persistence capabilities through the protocol.
- `FixtureConceptModelStrategy` deterministically maps the two neutral 0.7B source profiles without
  a model, network, credential, or clock.

## Authority and effects

The Ontology Agent may validate source handoffs, ask a strategy for an effect-free proposal,
persist immutable proposal/disposition artifacts through Core's opaque record port, and request
exact human/Core disposition.

It may not read a new source, widen source scope, access credentials, configure a connector,
persist authoritative ontology state, schedule or deliver work, activate a pack, create a grant,
self-approve, silently mutate a proposal, or reinterpret an earlier revision.

## Acceptance and failure controls

The candidate passes only when:

1. two exact approved source profiles produce a useful cited provider-free concept model;
2. every concept citation binds the exact profile, sample, source, evidence digest, and field path;
3. organization terminology remains optional host input and cannot grant authority;
4. edits produce a new immutable identity, increment revision, bind the exact prior proposal, and
   carry a deterministic semantic diff that exactly matches the changed material;
5. exact human/Core approval is required for `concept_model_approved`;
6. a fresh service reopens the exact approved proposal and disposition bodies and session handoff;
7. missing, stale, or widened source-profile material fails before proposal persistence;
8. invented/unattributed concepts, invalid citations, duplicate/colliding type IDs, imperative
   fields, silent mutation, stale approval, and self-approval fail closed;
9. low confidence and blocking source disagreement persist resumable `blocked` state with the
   declared reason; and
10. installed-wheel two-directory identity, unchanged 0.7A/0.7B behavior, naked-kernel startup,
    and exact eleven-tool MCP checks pass.

## Evidence plan

The candidate record binds exact proposal/disposition/session identities, changed files, focused
and platform regression results, wheel hash, two-directory installed-artifact reproduction,
limitations, and rollback. It advances only 0.7C Map.

## Rollback

Stop composing the additive Ontology Agent and Map exports. Existing opaque Core records remain
immutable history. Rollback performs no connector action, deletes no proposal or disposition,
changes no grant, activates no pack, and leaves 0.7A/0.7B contracts untouched.

# ACE documentation

**ACE, the Intelligence Builder. Build intelligence, not infrastructure.** These pages describe
the current product, supported interfaces, builder journeys, and contributor-facing contracts.
Point-in-time release and acceptance records live in the
[evidence archive](evidence/README.md) so they do not obscure the durable documentation.

## Start here

- [ACE vision and manifesto](../MANIFESTO.md) — the Intelligence Builder promise, constitutional
  boundaries, and open Intelligence Operating System direction.
- [Project quickstart](../README.md) — install ACE and reach a first useful result.
- [Capability maturity](capability-maturity.md) — what the current release supports and what remains
  experimental.
- [Architecture](architecture.md) — the as-built system map and responsibility boundaries.
- [Frequently asked questions](faq.md) — failure behavior, provenance, confidence, and operating
  boundaries.

## Use ACE

- [Model providers](providers.md) — configure model access and understand routing behavior.
- [Product-builder golden path](product-builder-golden-path.md) — reproduce an evidence-backed
  decision, correction, restart, and later reuse.
- [State Engine product-builder journey](state-engine-product-builder.md) — install an independent
  product extension and reproduce the bounded K1-K3 evidence, rollout, restart, and correction path.
- [Clean-user onboarding trial](onboarding-trials.md) — evaluate setup, first value, and recovery.
- [Productized State](productized-state.md) — install an extension, ingest product context, reason,
  correct, restart, and inspect the complete receipt chain.
- [Reliable observation worker operations](worker-operations.md) — supervised startup, shutdown,
  restart, lease recovery, and queue health.
- [State Engine operations and recovery](state-engine-operations.md) — scale limits, bounded
  ingestion, interruption/replay, migration, backup/restore, lifecycle, and escalation.

## Product contracts

- [Living Product Graph](living-product-graph.md) — the supported read-only product projection.
- [Decision and correction receipts](decision-correction-receipts.md) — structured decisions,
  dispositions, corrections, and restart behavior.
- [Graph-grounded calibrated foresight](foresight.md) — forecasts, observations, resolution,
  scoring, and current maturity.
- [Experimental extension invocation](extension-invocation-contract.md) — the authenticated
  extension runtime boundary and its limitations.

## Build extensions

- [Build your first extension](build-your-first-extension.md) — scaffold, run, and package an
  extension.
- [Extension API](extension-api.md) — stable and experimental extension-author contracts.
- [Governed cognition builder journey](governed-cognition-builder.md) — teach, inspect, approve,
  use, attribute, and retire reusable cognition through supported interfaces.

## Project

- [Governance and support](governance.md)
- [Versioned public roadmap](../ROADMAP.md)
- [Changelog](../CHANGELOG.md)
- [Security policy](../SECURITY.md)

Detailed architecture and historical implementation sequences live under design notes. They
support the public roadmap but do not compete with it for outcome state or dispatch:

- [Governed cognition](design/capability-evolution.md) — teach, govern, and measure reusable
  cognition.
- [ACE State Engine design and implementation record](design/state-engine-roadmap.md) — reason over
  high-volume temporal evidence, inspectable dynamics, and bounded consequences while preserving
  sparse durable memory.
- [State Engine v0.2 Core boundary](design/state-engine-core-boundary-v1.md) — stable contracts,
  adapter portability, experimental capabilities, deployment limits, and deferred work.
- [State Engine Core-boundary readiness addendum](design/state-engine-core-boundary-readiness-v1.md)
  — K2/K3 bounded readiness delta while preserving the frozen TP8 boundary input.
- [Intelligence Builder onboarding sequence](design/guided-intelligence-bootstrap-v0.7.0-work-packet-v1.md)
  — the cumulative 0.7A–0.7E Connect → Map → Watch → Brief → Activate contracts, authority
  boundaries, state machine, and full-demo acceptance.
- [Intelligence OS Realignment](design/intelligence-os-realignment-v0.8.0-work-packet-v1.md) — the
  0.8A–0.8F canonical lifecycle, ownership and compatibility map, Atrium and public-resource
  sequence, World AI Command Center demonstration, Market falsifier, release gates, and stop
  conditions.
- [Intelligence OS runtime-boundary realignment](design/intelligence-os-runtime-boundary-v0.8.0-work-packet-v1.md)
  — the active 0.8B packet, accepted AM4 input, default isolation of embedded product-intelligence
  engines, compatibility switch, remaining runtime convergence, and rollback.
- [Legacy host compatibility disposition](design/core-engine-compatibility-disposition-v0.8.0.json)
  — the machine-checked 0.8 owner and migration treatment for every top-level `core.engine`
  package; the canonical public roots remain `ace.core`, `ace.intelligence`, and `ace.application`.
- [Intelligence Builder Connect work packet](design/intelligence-builder-connect-v0.7.0-work-packet-v1.md)
  — the bounded 0.7B Connection Agent implementation, reuse audit, failure controls, and evidence
  plan.
- [Intelligence Builder Map work packet](design/intelligence-builder-map-v0.7.0-work-packet-v1.md)
  — the bounded 0.7C Ontology Agent proposal, immutable edit, exact approval, restart, and evidence
  plan.
- [Intelligence Builder Watch + Brief work packet](design/intelligence-builder-watch-brief-v0.7.0-work-packet-v1.md)
  — the bounded 0.7D Intelligence Agent and Briefing Agent proposals, exact approval, first-Brief,
  restart, failure controls, and downstream handoff.
- [Domain Packs + Activation work packet](design/domain-packs-activation-v0.7.0-work-packet-v1.md)
  — the bounded 0.7E audit, additive exact-plan authority seam, accepted inert 0.7D handoff,
  compatibility and rollback threat model, and external consumer packet boundary.
- [Domain Packs + Activation Core candidate evidence](evidence/domain-packs-activation-v0.7.0-core-candidate-v1.md)
  — exact activation/reference identities, negative controls, full verification, installed-wheel
  reproduction, and the remaining World/Market consumer handoff.
- [AC7 composition-policy admission work packet](design/composition-policy-admission-ac7-work-packet-v1.md)
  — the finite AC6 closeout for exact review, Core authority, CAS policy-head lifecycle, bounded
  runtime resolution, and the post-AC7 composition freeze pending integrated 0.7 acceptance.
- [AC7 composition-policy admission candidate evidence](evidence/composition-policy-admission-ac7-candidate-v1.md)
  — frozen provider-free coordinates, positive lifecycle, seventeen fail-closed cases, wheel proof,
  and release/integration entry gate.
- [Agent Memory roadmap](design/agent-memory-roadmap.md) — bounded AM0–AM8 sequence for durable,
  authorized, source-grounded agent memory.
- [Agent Memory AM3 work packet](design/agent-memory-am3-work-packet-v1.md) — authorized recall,
  frozen provider-neutral ranking, Context Planner and Manifest, composition/I3 lineage, matched
  materiality, durability, privacy, and AM4 stop boundary.

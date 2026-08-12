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
- [Intelligence Builder Connect work packet](design/intelligence-builder-connect-v0.7.0-work-packet-v1.md)
  — the bounded 0.7B Connection Agent implementation, reuse audit, failure controls, and evidence
  plan.

# AC5 delivery, export, and external-agent interoperability work packet v1

- Date: 2026-08-12
- Status: implementation candidate; not a supported product claim
- Exact AC3 parent: `da545b2e8a41d343e4d034a3e244861895cf95f9`
- Exact AC4 parent: `5536da71e37b153739a910f90f80737079ce9453`
- Combined-base merge: `37dd899c7a5b54c0f6a01f5691da95f992f31c4d`

## Outcome and hard separation

AC5 defines four operations that cannot substitute for one another:

1. AC3 prepared internal handoff: inert typed package; `external_send_occurred=false`.
2. Destination delivery: exact destination/recipient transfer under current `destination_delivery` authority.
3. Administrative export: portable checksum-bound artifact under current `administrative_export` authority, with no send or runtime authority.
4. External effect: consequential operation under current `external_effect` authority, separately admitted and revalidated.

Delivery acknowledgment proves only that the destination adapter reported receipt. It does not prove
truth, benefit, or downstream execution. Installation, protocol handshake, conformance, AC4
activation, compatibility replacement, delivery, and export do not grant execution or effect
authority.

## Convergence

The narrow `GovernedAgentPreExecutionResolver` reloads the exact durable AC4 activation and
compatibility-replacement transactions, validates the five current AC4 heads, re-resolves lifecycle
and requested grants, and then calls AC2 pre-execution for the exact new AC3 plan and manifest.
The replacement preserves the opaque compatibility participant reference while the new governed
participant binds exact governance, registration snapshot, definition, role binding, lifecycle, and
health material. The admission fixes `rewrites_history=false`, `carries_authority_forward=false`, and
`reusable_authority=false`. A pre-replacement AC3 plan cannot be silently promoted.

## Contract coordinates

Core contracts:

- `ace.core.destination-definition/v1alpha1`
- `ace.core.destination-revision/v1alpha1`
- `ace.core.destination-policy-coordinate/v1alpha1`
- `ace.core.external-operation-authority/v1alpha1`
- `ace.core.destination-delivery-intent/v1alpha1`
- `ace.core.destination-delivery-admission/v1alpha1`
- `ace.core.destination-delivery-attempt/v1alpha1`
- `ace.core.destination-acknowledgment/v1alpha1`
- `ace.core.destination-delivery-result/v1alpha1`
- `ace.core.destination-delivery-lookup/v1alpha1`
- `ace.core.administrative-export-manifest/v1alpha1`
- `ace.core.portability-receipt/v1alpha1`
- `ace.core.external-effect-intent/v1alpha1`
- `ace.core.external-effect-admission/v1alpha1`
- `ace.core.external-effect-attempt/v1alpha1`
- `ace.core.external-effect-result/v1alpha1`
- `ace.core.external-effect-lookup/v1alpha1`
- `ace.core.external-operation-cancellation/v1alpha1`

Application and Intelligence contracts:

- `ace.application.governed-agent-pre-execution-admission/v1alpha1`
- `ace.intelligence.external-agent-protocol-identity/v1alpha1`
- `ace.intelligence.external-agent-handshake/v1alpha1`

Host-private payload contracts:

- `ace.host.destination-revision-state/v1alpha1`
- `ace.host.destination-policy-state/v1alpha1`
- `ace.host.external-operation-configuration/v1alpha1`

## Authority and TOCTOU

The host resolver uses the existing authenticated runtime context and `RuntimeUseResolver`. Every
delivery/effect resolution includes the current operation configuration, adapter capability, grant,
destination revision, and six destination policy heads: capability, compatibility, entitlement,
consent, redaction, and data class. Product, actor, tenant, recipient, digest, lifecycle, effective
time, and expiry mismatch fail closed.

Delivery and effects resolve once after preparation and again immediately before the adapter call.
Admission and attempt are durably appended under exact head preconditions. An unknown effect result
sets lookup-before-retry; only a conclusive not-found lookup may permit a later separately admitted
retry. Stable idempotency keys and durable attempt lookup prevent duplicate effects across reopen.

## Export and external-agent boundaries

Administrative export manifests separately enumerate included, omitted, redacted, retention,
erasure-dependency, and data-class coordinates. Their checksum covers those exact fields. The
portability receipt carries no delivery/runtime authority and records no external send.

External-agent handshake binds current AC4 registration, definition, binding, lifecycle, health,
protocol, and capabilities. Compatible, unsupported-protocol, capability-mismatch, and ineligible
states are explicit. Every handshake authority flag is false. Runtime participation still requires
the separate AC2/AC4 pre-execution convergence admission.

## Adapter and exclusions

`ace.testing.ReferenceExternalDestinationAdapter` independently implements the public delivery, effect, lookup,
and export ports without a provider SDK or network I/O. It stores opaque digests only. A host-private
secret reference is constructor state and never appears in a public contract or receipt.

AC5 adds no MCP tool, public task field, endpoint, UI, marketplace, provider dependency, database
schema, Domain Pack noun, AM1 dependency, release, merge, tag, or acceptance-test network call.
The exact eleven-tool MCP and naked-kernel surfaces remain unchanged.

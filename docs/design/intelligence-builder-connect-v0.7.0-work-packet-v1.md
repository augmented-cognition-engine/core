# ACE 0.7B Intelligence Builder Connect work packet (v1)

**Status:** implementation candidate stacked on the 0.7A pack contract/compiler/conformance
candidate in draft PR #100. This packet implements Connect only. It does not claim Map, Watch,
Brief, Activate, the cumulative onboarding demo, or the 0.7.0 release.

## Outcome

A product can offer deterministic source options, show the exact requested permission and effect
scope, obtain approval for one bounded connection test/sample, persist the proposal-only handoff,
and resume the onboarding session after failure or restart. Network access, connector transport,
credentials, authoritative connector configuration, scheduling, and delivery remain host-owned.

## Reuse audit

0.7B adds application coordination above existing public seams rather than a parallel subsystem:

| Need | Reused owner and primitive | 0.7B responsibility |
|---|---|---|
| Durable state and replay | Core `ImmutableRecordStore` append-only transaction and receipt contracts | Store opaque content-addressed onboarding revisions and validate their exact chain. |
| Human authority | Core `CoreAuthorityResolver` and `ResolvedApprovalReceiptV1` | Resolve approval for the exact current source-scope proposal before any connector effect. |
| Connector capability | Host-supplied registered provider protocol | Enumerate declared options and perform only approved connection-test/bounded-sample effects. |
| Domain Pack activation | 0.7A compiler, conformance, and existing activation services | No use in 0.7B; reserved unchanged for the Activation Agent in 0.7E. |
| Source ingress, monitors, subscriptions, and Briefs | Existing application/Intelligence services | No use in 0.7B; Connect emits source-profile proposals only. |

Core receives its normal opaque record payload and never learns source-profile or onboarding-stage
fields. The application layer owns the journey state machine. Connector implementations never gain
persistence or approval authority through the Connection Agent contract.

## Public contracts and service

- `SourceOptionCatalogV1` describes explicitly registered host options, exact logical source
  identities, and their maximum safe permissions, scopes, effects, and sample bounds.
- `SourceScopeProposalV1` binds the selected options to the current session, goal, and exact catalog
  identity.
- `SourceSampleV1` carries a redacted, content-addressed shape result and structurally forbids
  authoritative configuration persistence, scheduling, and delivery.
- `SourceProfileProposalV1` binds one exact sample per approved option.
- `IntelligenceBuilderSessionRevisionV1` carries opaque session/correlation identity, append-only
  transition lineage, artifact handoffs, and blocked/retry state.
- `ConnectionAgent` discovers, proposes, validates approval, calls the host provider, refuses
  widening, and hands off a proposal. It cannot approve, configure, schedule, deliver, or activate.
- `IntelligenceBuilderSessionService` persists and reopens exact session revisions through Core's
  immutable record port.

All contracts are strict, frozen, content-addressed, and expose machine-readable JSON Schema
through their public Pydantic models. The public testing helper supplies two neutral sources and a
deterministic authority fixture without a model, network, or credential.

## Acceptance and failure controls

The candidate must prove:

1. two approved provider-free sources reach `sources_ready` through one public Python application
   surface;
2. an independent service instance reloads the exact session and handoff identities;
3. repeated fixture runs reproduce proposal, profile, and terminal revision identities;
4. denied approval invokes no provider effect and persists `insufficient_permission`;
5. connector failure persists `failed_connector` and resumes at `sources_connecting`;
6. returned permission, scope, connector, effect, or sample widening cannot reach `sources_ready`;
7. revised proposals invalidate stale handoffs before authority or connector use;
8. an agent cannot self-dispose a human/Core transition or fork a stale session chain;
9. credentials, unsupported effects, scheduling, delivery, and authoritative configuration fail
   structural validation; and
10. the built wheel imports and runs the provider-free helper while naked-kernel startup and the
    exact eleven-tool MCP surface remain unchanged.

## Evidence plan

The candidate evidence record binds the branch/commit, changed files, focused tests, deterministic
identities, wheel hash and clean installed-wheel run, naked-kernel regression, exact MCP tool count,
limitations, and rollback. A passing 0.7B record advances only Connect. The cumulative A–E evidence
remains owned by the
[Intelligence Builder onboarding sequence](guided-intelligence-bootstrap-v0.7.0-work-packet-v1.md).

## Rollback

Remove the additive application/testing exports or stop composing the Connection Agent. Existing
Core records remain immutable opaque history. Rollback performs no connector operation, deletes no
proposal, changes no grant, and leaves 0.7A contracts untouched.

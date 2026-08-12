# ACE 0.7.0 Domain and Extension Platform kickoff work packet (v1)

**Status:** bounded implementation candidate. This packet does not complete issue
[#39](https://github.com/augmented-cognition-engine/core/issues/39), E2, SI3, or the 0.7.0
release.

**Frozen:** 2026-08-11 from released `main` at
`492b99667b0a119234d4a8af26e448254c0a6abd`.

## Objective and public promise

Freeze the smallest stable third-party Domain Pack contract that lets an independently built pack
declare its vocabulary and policy, compile through unchanged ACE Core + Intelligence, pass a
public conformance suite, and remain portable across explicitly compatible hosts.

The first 0.7 packet promotes no domain ontology into ACE. It turns the existing alpha pack
substrate into a versioned product contract with an explicit compatibility window, deterministic
diagnostics, machine-readable schemas, golden-fixture conformance, and a deprecation policy.
In the 0.7 product sequence this is the 0.7A substrate. Its scope remains frozen: it makes guided
intelligence building safe and portable, but it is not itself the customer onboarding experience.
JSON is the machine-readable interchange and audit format; no product promise requires a customer
to hand-author it or understand compiler mechanics.

World Intelligence and Market Intelligence are the independent falsifiers:

```text
World pack  -----\
                  -> public schema -> compiler -> conformance receipt -> governed activation
Market pack -----/
```

Passing requires both domains to use the same public machinery without Core or Intelligence
learning World or Market nouns.

## Why this is the first 0.7 packet

ACE 0.4 established the inert Domain Pack compiler and governed Intelligence substrate. ACE 0.6
proved measured outcomes across Core and World, and Market has now reproduced the same neutral
impact lifecycle independently. The remaining adoption risk is not whether a pack can compile in
the source tree; it is whether an external builder can know which contract is supported, validate
it before activation, understand failures, and upgrade without reading ACE internals.

The compiler is therefore the domain-agnosticism guarantee and the first public 0.7 boundary. A
new vertical must require configuration and reviewed connectors, never a kernel fork.

## Ownership boundary

- **Core** owns durable state, provenance, authority, activation Decisions, receipts, outcomes,
  failure semantics, and immutable conformance evidence.
- **Intelligence** owns the pack schema, deterministic compiler, compatibility negotiation,
  structured diagnostics, conformance runner, and domain-neutral runtime binding.
- **Domain Packs** own entities, relations, aliases, source mappings, detector declarations,
  materiality, personas, synthesis policy, and specialized trust policy.
- **Connectors** own reviewed translation from an external source into the neutral Observation
  envelope. They are executable packages and are not part of the inert pack.
- **Trusted extensions** own separately governed executable capabilities. A pack cannot acquire
  extension, connector, network, persistence, scheduling, delivery, or action authority by
  declaration.

Entity-state projections remain rebuildable derivatives of Core-owned records. Intelligence may
declare and materialize a projection only through Core persistence contracts; it cannot create a
second authoritative state engine.

## Inert-pack rule

A Domain Pack is bounded JSON data. It contains no imperative control flow and no executable
payload. The compiler must fail closed on attempts to declare or smuggle:

- code, imports, callbacks, classes, functions, scripts, commands, expressions, loops, or eval;
- executable selectors or arbitrary query languages;
- network locations that imply transport authority;
- persistence, scheduling, publication, delivery, or external-action authority; or
- opaque binary resources or unbounded embedded material.

Source mappings, transforms, detector strategies, and synthesis templates must use closed,
versioned declarations interpreted by Intelligence. A need that cannot be expressed by a closed
declaration belongs in a separately reviewed connector or trusted extension.

## Initial public contract

The first candidate must publish and bind:

1. a stable Domain Pack manifest schema version;
2. an explicit compiler/runtime compatibility range rather than an implicit equality check;
3. independently versioned module contracts for ontology, source mapping, detection, personas,
   epistemic policy, synthesis, and decision outcomes;
4. exact resource digests, canonical ordering, bounded sizes, and duplicate-key rejection;
5. requested capabilities and authority declarations visible before activation;
6. a deterministic compiled-pack identity and compilation report;
7. a public compatibility result distinguishing supported, deprecated, migration-required, and
   rejected material; and
8. a conformance receipt binding pack digest, compiler identity, host contract, fixture identity,
   expected results, diagnostics, and pass/fail status.

The contract must not include `brief_id`, a domain entity name, or another product concept in a
Core receipt. Intelligence correlates domain resources to opaque Core request and record IDs.

## Public conformance suite

The reusable suite must be installable from the `ace-core` distribution and executable without a
model provider, network access, or a database. Each pack supplies bounded golden fixtures:

```text
manifest + resources + golden Observations
    -> compile
    -> derive expected entity references and Shifts
    -> verify routing/synthesis policy selection
    -> emit deterministic conformance receipt
```

Minimum positive checks:

- clean install and discovery from a separately built distribution artifact;
- byte-stable compilation and identities across two fresh directories;
- deterministic golden Observation-to-Shift expectations;
- requested capabilities, authorities, and source boundaries are inspectable before activation;
- co-installation of World and Market packs without shared mutable state or identifier collision;
- current host plus the explicitly supported previous contract window; and
- exact replay after a fresh process.

Minimum negative checks:

- unknown or removed schema version;
- unsupported compiler/runtime range;
- undeclared, missing, digest-mismatched, duplicate, oversized, or cyclic resources;
- imperative-control-flow and executable-payload attempts;
- unknown module contracts or cross-module references;
- domain identifier collisions;
- authority escalation through pack declarations;
- changed golden output under the same conformance identity; and
- activation attempted without a passing exact conformance receipt.

Diagnostics must be stable, path-specific, bounded, safe to expose, and actionable without a
traceback. Error messages are part of the builder experience and require compatibility review.

## Schema evolution and deprecation policy

The candidate policy must state:

- which manifest and module versions the current host accepts;
- the minimum notice period and release vehicle for deprecation;
- whether a change is additive, migration-required, or breaking;
- how an offline migration produces a new digest and preserves the prior pack as audit history;
- that hosts never silently rewrite or reinterpret signed pack material; and
- that unsupported or expired contracts fail before activation with no durable live effect.

Compatibility is negotiated from declared contracts and ranges. Package version alone is not a
substitute for contract compatibility.

## Executable acceptance

This bounded packet passes only when:

1. the schema and compatibility policy are distributed in the built `ace-core` wheel;
2. the public compiler and conformance helper operate from an installed artifact with no checkout
   import leakage;
3. World and Market independently pass the same suite from their own repositories;
4. at least one valid prior-version fixture passes the supported compatibility window;
5. migration-required and unsupported fixtures fail with exact structured diagnostics;
6. imperative pack content, authority escalation, digest drift, and identifier collision fail
   closed;
7. two clean runs produce byte-identical compiled identities and conformance receipts;
8. activation refuses missing, failed, stale, or mismatched conformance evidence; and
9. focused, package, compatibility, security, and release-hygiene checks pass.

Consumer evidence belongs in the World and Market repositories. Core records only the neutral
contract, its own acceptance, and exact external release or commit identities.

## Files initially owned by this packet

- `ace/intelligence/contracts/pack.py`
- `ace/intelligence/packs/compiler.py`
- `ace/intelligence/packs/diagnostics.py`
- `ace/intelligence/packs/activation.py`
- a machine-readable schema directory under the packaged `ace` namespace
- a public Domain Pack conformance helper under `ace/testing/`
- focused tests under `tests/intelligence/`
- compatibility/deprecation documentation
- this packet and its later immutable evidence record

File ownership is intentionally narrow. Connector SDKs, trusted-extension lifecycle, telemetry,
heterogeneous evidence semantics, and the full E2 platform remain later 0.7 packets.

## Explicit exclusions and non-claims

This packet does not:

- execute connectors or extensions;
- sandbox untrusted code;
- grant network, persistence, scheduler, delivery, publication, or action authority;
- add a UI, marketplace, remote registry, or automatic updater;
- complete heterogeneous time-series, geospatial, market-contract, or track semantics;
- complete SI1-SI4 or establish general domain neutrality from two examples;
- change the eleven-tool MCP surface; or
- declare ACE 0.7.0 ready.

## Rollback and failure semantics

The candidate is additive until release. Rollback removes the new stable schema, compatibility,
and conformance surface while preserving existing alpha behavior for the exact compatibility
window documented at packet start. No pack is silently migrated, and no prior conformance receipt
is rewritten.

A failed compile or conformance run has no activation effect. A partially emitted receipt is not a
pass. Any durable activation must bind the exact successful receipt, compiled pack digest, host
contract, and authority decision.

## Following packets

After this 0.7A packet passes, the Intelligence Builder journey proceeds in bounded slices:

1. **0.7B Connect:** Connection Agent, source option/profile/scope proposals, and resumable session
   state;
2. **0.7C Map:** Ontology Agent and cited, editable concept-model proposals;
3. **0.7D Watch + Brief:** separate Intelligence and Briefing Agents, monitor/materiality proposals,
   and the first grounded Brief preview; and
4. **0.7E Activate + prove:** Activation Agent, exact approval/conformance/activation, restart,
   update, feedback, and independent World and Market consumer proof.

The five agent boundaries and cumulative acceptance are frozen in the
[Intelligence Builder onboarding sequence](guided-intelligence-bootstrap-v0.7.0-work-packet-v1.md).
Connector SDK breadth, trusted-extension isolation, heterogeneous Observation semantics, telemetry,
and release closeout still require their own evidence within or alongside those product slices.

These packets may advance SI3 and E2 only through their own evidence. They do not inherit a pass
from this kickoff.

# Domain Pack v1 compatibility, migration, and deprecation policy

This document is the public lifecycle policy for the first stable third-party Domain Pack
boundary. It applies to the contracts distributed in `ace.intelligence.schemas`; it does not apply
to connectors or trusted extensions, which remain separate executable capability boundaries.

## Current host window

The stable host identifies itself as:

- compiler: `ace.intelligence.pack-compiler/v1`;
- Intelligence runtime: `ace.intelligence.runtime/v1`; and
- manifest: `ace.intelligence.domain-pack-manifest/v1`.

The v1 manifest declares explicit half-open compiler and runtime ranges. The current host accepts a
minimum of either the supported prior `v1alpha1` contract or stable `v1`, with an exclusive `v2`
ceiling. The current host contract must fall inside both declared ranges. Package versions are not
used as a substitute for this negotiation, and the exact declared ranges are Pack IR identity
material.

The prior `ace.intelligence.domain-pack-manifest/v1alpha1` contract remains supported with a
`deprecated` compatibility result for the 0.7.x line. It preserves its released Pack IR identity
and exact-equality compiler/runtime behavior. It was first declared deprecated on 2026-08-11 and
will not be removed before both 0.8.0 and 2027-02-07.

The v1 host accepts these independently versioned module contracts:

- ontology `v1alpha1`;
- source mapping `v1alpha1`;
- detection `v1alpha1` and `v1alpha2`;
- personas `v1alpha1`;
- synthesis `v1alpha1` and `v1alpha2`;
- epistemic status `v1alpha1` and `v1alpha2`; and
- decision outcomes `v1alpha1`.

Their JSON Schemas and the schema index are installed with `ace-core`. Support for a manifest does
not imply support for an undeclared module version.

## Change classification

- **Additive** changes add optional declarations or a new independently negotiated module
  contract without changing existing canonical material. They may ship in a compatible minor or
  patch release when old packs retain identical meaning and identity.
- **Migration-required** changes alter required material or canonical interpretation but have a
  deterministic offline transformation. The old material is never rewritten by a host. Migration
  creates a new manifest or module version, a new pack digest, and a new conformance receipt.
- **Breaking** changes remove a contract, reinterpret existing signed material, widen authority,
  or cannot preserve deterministic audit history. They require a new major contract identifier and
  a release whose notes explicitly name the break.

Every deprecation is announced in the changelog and release notes, linked from the public roadmap,
and retained for at least one complete ACE minor-release line and 180 days, whichever is longer.
Security fixes may refuse specifically unsafe material sooner, but must use a stable structured
diagnostic and may not silently reinterpret it.

## Migration and audit history

Migration is an explicit offline operation. It reads immutable prior bytes and emits new bytes; it
does not activate, persist, grant authority, or mutate the source pack. Builders retain the prior
pack, its digest, compilation result, and conformance receipt as audit history. The migrated pack
must compile and pass its own golden fixtures, producing a distinct digest and receipt.

Hosts never silently rewrite, upgrade, downgrade, or reinterpret signed pack material. A
prerelease contract that is known but outside the supported window returns
`migration_required`. An unknown or removed contract returns `rejected`. Unsupported compiler or
runtime ranges fail before activation with no durable live effect.

## Authority and activation

Domain Packs are inert bounded JSON. They cannot declare executable code, callbacks, selectors,
network transport, persistence, scheduling, delivery, publication, or external-action authority.
Capabilities and source-read requests remain inspectable declarations that must be satisfied by
separately reviewed host bindings.

Stable activation requires the complete exact conformance receipt, not an unchecked string. The
receipt must pass, bind the exact Pack IR and fixture expectations, and name the current compatible
compiler/runtime contracts. Missing, failed, stale, forged, or mismatched evidence is refused
before Core creates any durable activation effect. Core stores only the opaque receipt reference
inside its activation material; domain resource identities remain owned by Intelligence.

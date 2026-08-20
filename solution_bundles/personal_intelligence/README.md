# Personal Intelligence Solution Bundle

The public, installable manifest of the first-party **Personal Intelligence
Solution Bundle** for ACE 1.2. Per packet Decision 1, Personal Intelligence is
not an ontology inside ACE: it is this bundle — exact bindings of the shipped
Personal Intelligence domain pack, its default overlay, the read-only
local-source adapter family, and the local read-only source policy. The ACE
bundle machinery is domain-neutral; this distribution carries the concrete
bundle *value* as pure data (no importable code).

## Contents

- `bundle.json` — the `ace.intelligence.solution-bundle-manifest/v1alpha1`
  document, discovered checkout-free at the wheel path
  `solution_bundles/personal_intelligence/bundle.json`.
- `policy/local_read_only_sources.json` — the bound policy document.

## Exactness

Every binding is exact (Decision 3 — no version ranges, no universal-connector
promise):

- The **pack** binding is the compiled identity (`compiled_pack_id`,
  `pack_digest`) of the shipped `domain_packs/personal_intelligence` pack.
- Each **adapter** binding pins the adapter's distribution name, exact version,
  and a canonical source-tree digest: a sorted mapping of relative path to
  sha256-of-bytes over the adapter's shipped files, canonically hashed. Any
  drift in an adapter's shipped bytes changes the binding and fails resolution
  closed.
- The **policy** binding pins the policy document's exact bytes.

`bundle.json` is generated — never hand-edited — by
`scripts/build_solution_bundle_manifest.py`, which is deterministic (no clock,
no environment, no network). The test suite regenerates the document and
requires byte identity.

## Neither requires the other

This bundle names no other bundle. Code Intelligence composes beside it over
the shared graph by co-activation (Decision 14); neither is a dependency of
the other.

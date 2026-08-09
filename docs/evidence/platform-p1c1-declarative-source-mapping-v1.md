# Platform P1C1 declarative source-mapping evidence

**Status:** local, candidate evidence verified on 2026-08-06. This is a source-checkout/local-wheel
reproduction, not verification of a published artifact — no ace-core 0.4.1 git tag, GitHub Release,
or PyPI package exists yet. P1C2 remains open.

P1C1 adds the closed `ace.intelligence.source-mapping/v1alpha1` declaration module, a
Core-owned immutable source-snapshot contract, and a side-effect-free PREPARED interpreter. The
interpreter consumes one exact activation-bound compiled Pack IR, one mapping ID, one canonical
host snapshot, and one already-resolved subject binding. It returns one content-addressed
Observation and one exact-lineage Entity Snapshot.

## Trust boundary

- A rule binds one exact source definition and source type, an allowlist of URI schemes, one
  ontology entity target, ordered attribute mappings, one capability requirement, one authority
  request, and static confidence.
- RFC 6901 JSON Pointers select only captured payload values. The transform allowlist is exactly
  `copy` and faithfully representable `decimal_text_to_number`; optional string bounds and
  `ascii_upper` are declarative constraints.
- Closed schemas, unknown-key rejection, protected-field rejection, and structural executable-key
  rejection forbid expressions, programs, callbacks, templates, predicates, loops, conditions,
  registered operations, and code references. Ordinary inert pointer content is not treated as
  executable.
- Product, activation, mode, source and receipt identities, and all times come from the host
  envelope and resolved binding. Source payload labels cannot override them.
- Observation provenance durably pins the activation revision, compiled Pack ID and digest,
  source-mapping module ID and digest, and mapping ID and digest. The Entity Snapshot's single
  lineage edge pins that exact Observation without adding domain data to its attributes.
- Alpha source snapshots reject LIVE acquisition, non-integer JSON numeric tokens, non-finite
  values, duplicate keys, lone surrogates, malformed URI percent escapes, and control or DEL URI
  characters. Exact decimals are captured as text and must survive a Decimal-to-float round trip.
- Canonical mapped output is budgeted incrementally against the 32,000-character resource bound;
  later mappings are not evaluated after the bound is crossed.
- Every registered typed `CompiledModuleV1` requires its stored payload to equal the typed model's
  canonical normalization. Recomputed digests cannot admit reordered declarations or signed-zero
  aliases through direct IR construction.

The interpreter performs no I/O, network access, persistence, clock reads, model calls, secret
lookup, entity resolution, capability/grant resolution, or authority decision. Every LIVE input
fails closed. A committed activation remains admission evidence, not live authority.

## Public seams

- `ace.core`: `CanonicalSourceSnapshotV1Alpha1`, `SourceAcquisitionMode`.
- `ace.intelligence`: source-mapping declaration models and enums,
  `ResolvedSubjectBindingV1Alpha1`, `SourceMappingReferenceV1Alpha1`,
  `ResolvedSourceMappingPolicy`, `resolve_source_mapping_policy`,
  `resolve_source_mapping_rule`, `PreparedSourceMappingResult`,
  `PreparedSourceMappingError`, and `interpret_prepared_source_mapping`.
- `ace.testing`: `SourceMappingConformanceResult` and
  `exercise_prepared_source_mapping`.

## Deterministic evidence

Two structurally different domain-neutral fixtures use the same public interpreter without domain
branches. Their pinned outputs are:

| Fixture | Observation | Entity Snapshot |
|---|---|---|
| numeric | `observation:b5f4394738f8b5e50049d251a86c57e6` / `sha256:b5f4394738f8b5e50049d251a86c57e6ae2ef8df3adb2e620739d3c80c5b0244` | `entity_snapshot:34e55f3de2964b0ead40b4f3139069a7` / `sha256:34e55f3de2964b0ead40b4f3139069a73d70837eff877c8961b0f337f5b21f0f` |
| categorical | `observation:66426d907e83a36f6fe9eb8b619fade2` / `sha256:66426d907e83a36f6fe9eb8b619fade207c0a256f1eeec0089556f023e756912` | `entity_snapshot:c6103b731c5dd2e02694650c0d213e77` / `sha256:c6103b731c5dd2e02694650c0d213e77f136108562fdf9319647042f67a0905c` |

Semantically reordered declarations and `0.0`/`-0.0` confidence compile to identical Pack IR and
identity; material changes alter Pack identity. Regression coverage also proves exact source and
subject binding, two-rule provenance disambiguation, RFC 6901 root/empty-key/escape/index behavior,
numeric-token collision rejection, decimal fidelity, bounded recursion and Unicode failures,
aggregate output amplification control, direct-IR normalization enforcement, public error
normalization, and rejection of every LIVE attempt.

## Verification record

- Focused source-mapping, compiler, resource, ledger, boundary, artifact-contract, and build-backend
  gate: **89 passed, 1 deselected**.
- Complete Intelligence suite: **132 passed**.
- Kernel boundary and build coverage: **8 passed** before the final local-only mapping/artifact
  additions; the build-backend tests also passed in the final focused gate.
- Repository Ruff gate: **passed**.
- Full non-E2E suite before the final local-only mapping/artifact regressions: **7,178 passed, 46
  skipped, 251 deselected, 4 unrelated failures**.
- Extension-disabled suite before the final local-only mapping/artifact regressions: **7,164
  passed, 48 skipped, 263 deselected, 4 unrelated failures**.
- Wheel: `/tmp/ace-p1c1-final2.R17g1f/ace_core-0.3.0-py3-none-any.whl`, SHA-256
  `07f5134488f7de16800aae290bb05284fdffe8fb679353b0b3f9771630ad302c`.
- The isolated installed-wheel probe found all 15 permanent critical members byte-identical to
  source, imported `ace.core`, `ace.intelligence`, and `ace.testing` from the temporary installed
  site, found `ace/py.typed`, and loaded zero private `core.engine` modules from those imports.

The three stable unrelated full-suite failures are in
`tests/test_grounded_state_runtime_baseline.py`: its pre-existing source-revision helper assumes
`.git` is a directory and reads `.git/HEAD`, but this checkout is a linked worktree with a `.git`
pointer file. The fourth unrelated failure is persistent external SurrealDB test-state pollution in
`tests/test_synthesizer.py::test_atomic_capture_write_sets_specialty_field`: a transaction conflict
left `specialty:test_arch_30201` present, and a direct retry reported that exact record already
exists. P1C1 does not modify either area or clean unrelated persistence state.

## Explicit non-goals

P1C1 does not widen the P1B ledger and adds no persistence, adapter capture, acquisition-success
claim, use-time capability/grant resolution, authority decision, LIVE Observation admission,
Signal, Shift, Brief, routing, delivery, decision, outcome, or learning behavior. P1C2 owns live
authorization, capture, acquisition receipts, and LIVE admission and is explicitly open.

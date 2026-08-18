# Personal Intelligence local admission wiring v1

- Date: 2026-08-17
- Slice: PI3 remainder (#211) — wiring the acquisition port into governed admission
- Status: **contract chain specified; live-build integration remains**
- Related: [local source adapter architecture](personal-intelligence-local-source-adapters-v1.md),
  `ace/application/local_source_acquisition.py` (the merged acquisition port),
  `ace/application/recorded_source_admission.py` (the admission seam).

## The chain

An acquired local file becomes governed intelligence through this exact chain:

```
AcquiredLocalFile  (PI3 acquisition port — merged)
   → RecordedSourceMaterialV1Alpha1   (the builder specified here)
   → CoreRecordedSourceAdmissionService.admit(materials)   (live activated build)
   → canonical source snapshot + PREPARED Observation
```

`admit()` already exists and is the governed transaction. The missing link is the **builder** that
turns an `AcquiredLocalFile` plus its connection context into a valid
`RecordedSourceMaterialV1Alpha1`.

## What the builder needs (verified against the contract)

`RecordedSourceMaterialV1Alpha1` requires, per file:

| Field | Source | Notes |
|---|---|---|
| `source_uri` | the file's workspace path (3–2048 chars) | the acquired file's `relative_path` under the authorized root |
| `captured_payload_json` | the adapter's structured output, canonical JSON | the acquisition port already stores exactly this in `AcquiredLocalFile.structured_payload_json` |
| `captured_payload_digest` | `"sha256:" + sha256(captured_payload_json)` | **subtlety:** this digests the *canonical JSON payload*, not the raw file bytes. `AcquiredLocalFile.byte_digest` (raw bytes) is separate source provenance, not this field. |
| `observed_at` | caller-provided timestamp | keep it a parameter — the builder stays pure/testable |
| `locator` | the PI4 locator | optional; carries the citation anchor |
| `source_group_id`, `mapping_id` | connection config (slugs) | from the authorized source definition |
| `source_definition_ref`, `source_type_ref` | connection config (references) | from the authorized source definition |
| `subject_binding` | `ResolvedSubjectBindingV1Alpha1` | **live context — see below** |

## Why this belongs to the live activated build, not an isolated pure builder

`subject_binding` is a `ResolvedSubjectBindingV1Alpha1`, which carries an
`ActivationRevisionReferenceV1Alpha1`. Both enforce **exact-hash-derived identities**:

- `ActivationRevisionReferenceV1Alpha1.activation_id` must equal
  `domain_activation:<canonical_hash([product_id, activation_key])[:32]>`, plus a matching
  `revision_id`/`revision_digest`.
- `ResolvedSubjectBindingV1Alpha1.activation_revision.product_id` must equal the binding's
  `product_id`.

These identities are produced by an activated Domain Pack and a committed build head — they are not
values a standalone builder can invent. `admit()` further binds the material to the current
authority-grant head and one committed Domain Activation head before persisting.

The consequence: the builder is a pure function `(AcquiredLocalFile, connection_context,
observed_at) -> RecordedSourceMaterialV1Alpha1`, but `connection_context` (subject binding,
activation reference, source refs) is **resolved by the live build**, so the builder and its
`admit()` call are exercised against a running activated build — a live-SurrealDB integration —
not fabricated in isolation. Attempting to unit-test it against a hand-built activation fixture
would test the fixture's hash math, not the wiring.

## Remaining PI3 work (precisely scoped)

1. Add `build_recorded_material(acquired, *, connection_context, observed_at)` where
   `connection_context` is resolved from the authorized build's source definition and committed
   activation head. Only `status == "acquired"` files map (unsupported files stay inventory-only).
2. Set `locator` from PI4 and disclose the local acquisition mode (the recorded/PREPARED mode) so a
   later Brief may cite it — this is the citation-validator change also noted in PI4.
3. Exercise `acquire_local_folder → build_recorded_material → admit()` against a live activated
   build with SurrealDB, asserting the PREPARED Observations and their locators land, then feed
   them into the existing Brief synthesis for the first cited Brief (J5).

This is the integration seam between the merged ingestion spine (PI2 adapters, PI3 acquisition,
PI4 mapping/locators) and the governed intelligence lifecycle. It is deliberately done against a
running build rather than mocked, because its correctness is the exact-identity binding.

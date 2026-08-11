# Measured-impact observed-result provenance work packet (v1)

**Status:** bounded stacked implementation candidate; this packet does not complete issue
[#38](https://github.com/augmented-cognition-engine/core/issues/38), pass SI4, apply a proposal, or
close the 0.6.0 release.

**Frozen:** 2026-08-10 from the measured-impact disposition candidate at
`3c920bb5c411bd9d91a5e2a6c96d4014e9b66763`.

## Objective

Close one exact provenance gap between a product-owned measurement and Core's Outcome. A criterion
may require every scalar impact measure to name the exact immutable observed-result record that
produced it. The measured-impact service must resolve that record without future leakage and make
missing, temporally mismatched, or unavailable result material explicitly unproven.

The primary World proving target is an independently recorded citation-correctness review. World
owns citation semantics and review policy; the neutral platform sees only an exact immutable result
reference carried by the Outcome measures.

## Ownership boundary

- **Core** owns immutable record identity, product scope, availability, authority, append-only
  Outcome/evaluation/proposal history, and exact replay.
- **Intelligence** owns the domain-neutral criterion flag and optional exact observed-result
  coordinate carried with quality, latency, cost, failures, degraded state, and limitations.
- **Application composition** exact-loads the result and checks product, cutoff, observation time,
  and recording order before classification.
- **Products and Domain Packs** own result schemas, reviewers, measurement policy, evidence meaning,
  thresholds, and source-specific correctness semantics.

No citation, Federal Register, market, customer, or provider noun enters `ace.core`,
`ace.intelligence`, or `ace.application`.

## Frozen contract

`ImpactOutcomeMeasuresV1Alpha1.observed_result` is an optional
`ImmutableRecordReferenceV1`. `ImpactCriterionV1Alpha1.requires_observed_result` defaults to false
for the earlier candidate packet and becomes part of the criterion digest. When true, absence of
that reference excludes the pair as `observed_result_unavailable`.

When present, the service requires the reference to remain in the evaluation product, excludes it
without payload access when `available_at` is later than the cutoff, requires its `as_of` to equal
the Outcome observation time, requires availability no later than Outcome recording, and exact-
loads the immutable envelope. An unavailable or changed record is explicit unproven evidence. A
cross-product reference is invalid request material and fails closed.

The observed-result payload remains opaque to Core and Intelligence. Product code records the
score inside the Outcome and the review artifact independently; exact identity connects them.

## Executable acceptance and negative controls

The packet must prove:

- the existing useful, harmful, and unproven classifications still execute with an exact result;
- a criterion that requires result provenance excludes a missing exact result as unproven;
- a post-cutoff result is excluded from reference metadata without loading its payload;
- a cross-product result fails closed before evaluation append;
- the exact result reference participates in Outcome, request, evaluation, and replay digests; and
- all earlier attribution, conditions, outcome, duplicate/replay, restart, atomicity, and authority
  controls remain green.

## Files, rollback, and deletion criteria

This packet owns the additive fields in `ace/intelligence/contracts/impact.py`, their resolution in
`ace/application/measured_impact.py`, focused tests, this work packet, candidate evidence, and
restrained roadmap/maturity references. It changes no schema, package version, CLI, MCP tool,
Decision, Action, or Core Outcome contract.

Rollback removes the additive fields, checks, tests, and candidate documentation. Existing
immutable records remain history. Supersede this alpha shape before release if products cannot
produce exact reviewed-result artifacts without moving domain policy into the platform or if a
stronger generic measurement coordinate replaces it.

## Non-claims and next packet

An exact reviewed result proves provenance, not that the review is correct, independent in every
real-world sense, causal, statistically representative, or beneficial to a person. The World
candidate is bounded to two recorded official sources, one cited claim, two matched pairs, and one
frozen product rule. It does not prove live network freshness or general Brief quality.

The next bounded packet should add a materially different product-owned outcome or an independent
Market reproduction before any release promotion. Issue
[#49](https://github.com/augmented-cognition-engine/core/issues/49) findings F1, F3, and F5 still
require explicit 0.6 release-owner disposition; this packet does not implement or re-date them.

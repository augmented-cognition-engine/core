# ACE 0.6.0 Measured Intelligence kickoff work packet (v1)

**Status:** bounded implementation candidate; this packet does not complete issue
[#38](https://github.com/augmented-cognition-engine/core/issues/38), the World Intelligence public
journey, or the 0.6.0 release.

**Frozen:** 2026-08-10 from live `main` at
`be5e76c79715bb34bcbdcae9a0471a5c317fafe7`.

## Objective and product promise

Establish the smallest durable, domain-neutral path by which ACE can determine, under explicit
and inspectable product-defined criteria, whether an intelligence artifact or governed cognition
revision was useful, harmful, or remains unproven. A result may propose promotion, rejection,
rollback, or retirement, but it must never apply that proposal or make the evaluated subject
selectable by itself.

World Intelligence is the first external proving target:

```text
Observation -> Shift -> Signal -> Brief -> Decision -> reviewed Action
            -> observed Outcome -> governed feedback
```

The contracts in this packet remain neutral to World nouns and source policy so that Market
Intelligence can later reproduce them independently.

## Acceptance contract reconciled for this packet

Issue #38 and the public roadmap require the eventual public release to:

1. link exact outcome identity and provenance to the Decision, reviewed Action, evaluated
   artifact or cognition revision, and observed result;
2. compare treatment and control evidence under frozen matched conditions and disclose quality,
   latency, cost, failures, degraded states, uncertainty, exclusions, and limitations;
3. enforce an explicit cutoff so information that was unavailable at evaluation time cannot leak
   into the result;
4. classify impact as useful, harmful, or unproven under product-owned criteria rather than a
   caller-supplied quality label;
5. preserve append-only history, exact replay, changed-material conflict, restart durability, and
   fail-closed authority; and
6. trace a public real-data journey through an explicit, authorized promotion, rejection,
   rollback, or retirement decision.

This packet accepts items 1-5 for a bounded executable Core + Intelligence slice. Item 6 remains
for the World Intelligence public journey and later release closeout.

## Dependencies and non-claims

The packet composes these passed inputs without widening them:

- the 0.5.0 T1/B1 single-host, one-durable-store, explicitly trusted-adapter runtime;
- I3 exact material-use attribution, which proves influence rather than benefit;
- the L1 frozen executable-workload method, whose result does not generalize to people,
  customers, providers, external products, or real-world benefit; and
- the GI1/GI2 domain-neutral Intelligence substrate and World/Market falsification.

F2 is not required for this slice and remains gated. SI1-SI4 remain not ready. This packet does
not claim causality, universal accuracy, beneficial impact outside a declared product measure,
self-certification, autonomous optimization, distributed execution, general exactly-once effects,
or 0.6.0 release readiness.

## Ownership boundary

- **Core** owns immutable coordinates, durable records, product/scope identity, authority,
  Decision, Action, observed Outcome, append-only transactions, and governed-state heads.
- **Intelligence** owns domain-neutral impact criterion, matched conditions, evidence,
  useful/harmful/unproven evaluation, uncertainty, limitations, and non-effective change proposal
  contracts plus the pure deterministic evaluator.
- **Application composition** exact-loads and validates the full chain, resolves authority, and
  atomically appends the evaluation and proposal without creating live state.
- **Domain Packs and products** own domain nouns, source mapping and trust policy, condition
  material, outcome meaning, metric direction, thresholds, materiality, control construction, and
  the later authorized disposition.

No `core.engine` contract is imported into the public `ace` packages. The pre-existing internal
cognition-effectiveness evaluator is prior art only; its free-form cohort, optional attribution,
caller-supplied outcome label, and non-durable proposal are not promoted as the 0.6 contract.

## Public identity and provenance chain

Every durable coordinate is an exact `ImmutableRecordReferenceV1`, including its product, space,
kind, stable key, storage identity, material hash, payload contract, observation time, and
availability time.

The slice freezes:

1. an `ImpactCriterionV1Alpha1`, held as the exact governed `impact_criterion` head, containing the
   product-owned measure, direction, useful/harmful thresholds, minimum matched pairs, window,
   reviewed-action requirement, and classification-to-proposal mapping;
2. an evaluated intelligence artifact or cognition revision and an explicit control subject;
3. canonical matched `ImpactConditionsV1Alpha1` records for product context, route, and
   observation window;
4. treatment/control `ImpactEvidenceV1Alpha1` pairs linking exact material-use attribution,
   Decision, review, Action admission and terminal result, observed Outcome, outcome measures, and
   conditions;
5. an `ImpactEvaluationV1Alpha1` receipt binding the criterion head, ordered included evidence,
   exact exclusions and reasons, cutoff, classification, effect interval, operational metrics,
   uncertainty, and limitations; and
6. an optional `ImpactGovernanceProposalV1Alpha1` binding the exact evaluation and target while
   freezing `live_effect=false`, `selectable=false`, and `requires_human_review=true`.

An intelligence artifact Decision must name the exact target subject. A cognition revision is
first admitted to the same immutable record plane as `record_kind=cognition_revision`. Treatment
and control must use distinct Decisions and Outcomes. The Action review must approve the exact
admission intent and effect-free plan; the terminal record must bind that admission and its exact
result. The observed Outcome must bind the same Decision, product measure, window, and a time no
earlier than the terminal Action result.

## Deterministic classification

For each complete treatment/control pair, the evaluator normalizes the primary-value delta using
the criterion's higher-is-better or lower-is-better direction. It records the mean effect and a
deterministic 95 percent normal interval over matched-pair deltas.

- **Useful:** the lower interval bound meets the product's useful threshold.
- **Harmful:** the upper interval bound meets the negative harmful threshold.
- **Unproven:** evidence is incomplete or excluded, the minimum matched-pair count is not met, or
  the interval supports neither useful nor harmful.

Unproven is a valid result, not an error or inferred success. Missing exact attribution,
conditions mismatch, unavailable or unknown Outcome, and post-cutoff availability are explicit
exclusions. Malformed, cross-product, or digest-conflicting durable material fails closed.
Duplicate evidence identities are rejected rather than counted twice.

This interval is a bounded deterministic decision rule, not a universal causal estimator. The
receipt states that association is not causality and records missing latency or cost coverage.

## Durability, replay, and authority

The application service authorizes a semantic operation digest against both the explicit
operation binding and exact criterion head. A denial appends nothing. The evaluation and optional
proposal append in one immutable transaction with stable identities. An authority projection may
add stricter capability or grant heads, but it must preserve every requested frozen head exactly;
replacing or omitting one fails closed.

An exact request replay returns the historical transaction, evaluation, and proposal without
reclassification or reauthorization, including after a fresh store and process restart. Reusing
the same evaluation key with changed criteria, conditions, evidence, cutoff, or requested material
raises a replay conflict. The service exposes no apply operation; a later Core-authorized packet
must review the exact proposal and mutate live state through a separate governed-state transition.

## Executable acceptance and negative controls

The candidate must prove:

- useful, harmful, and statistically unproven classifications from complete matched evidence;
- promotion, rejection, rollback, and retirement as product-mapped proposal values, all
  non-effective;
- the same service path for an intelligence artifact and an immutable cognition revision;
- missing attribution, mismatched conditions, unavailable Outcome, and future/post-cutoff Outcome
  availability remain explicitly unproven;
- duplicate evidence fails closed and cannot amplify the sample;
- exact replay is stable while divergent replay conflicts;
- denied authority writes no evaluation or proposal, and a proposal cannot be constructed with a
  live effect; and
- a real SurrealDB store reopens the exact evaluation and proposal from a fresh service and a
  fresh Python process without duplicate append or reclassification.

## Files owned by this packet

- `ace/intelligence/contracts/impact.py`
- `ace/intelligence/impact.py`
- `ace/application/measured_impact.py`
- the minimal public export and contract-boundary additions for those modules
- `tests/intelligence/test_measured_impact.py`
- `tests/intelligence/measured_impact_restart_process.py`
- this work packet, its candidate evidence, and restrained roadmap/maturity references

## Explicit exclusions and rollback

This packet does not change package version, schemas, CLI or eleven-tool MCP surface, existing
Decision/Action/Outcome contracts, current governed heads, pack policy, connector behavior, or
release automation. It does not apply a proposal. It does not add World or Market domain logic.

Rollback removes the additive public modules, exports, tests, and candidate documentation. No
existing record shape or database migration requires reversal. Any candidate impact records remain
immutable audit history and non-effective by contract.

## Issue #49 disposition required

Three accepted security-review residuals in issue
[#49](https://github.com/augmented-cognition-engine/core/issues/49) carry a "next minor" deadline
and therefore require explicit release-owner disposition for 0.6.0:

- **F1:** a generation guard or real-database concurrency proof plus receipt reconciliation;
- **F3:** trusted-registration ceilings plus partial-registration rollback/reporting; and
- **F5:** pin the legacy optimizer query to `self_optimizer_proposal`.

This packet neither resolves nor silently re-dates them. Before 0.6.0 release closeout, maintainers
must either accept bounded hardening packets for them or record an explicit new deadline and
containment rationale. F2/F6 retain their dated deadline, F4 belongs to the next security bundle,
and F7 remains required before production traffic under issue #49.

## Remaining World journey and next bounded packet

The World Intelligence product must now freeze one public real-data scenario and product-owned
criterion, then supply exact LIVE Brief and control subjects, material-use attribution, Decision,
reviewed Action, observed Outcome, conditions, and cutoff to this unchanged neutral contract. Its
evidence must disclose source/time coverage, citation correctness, contradiction coverage,
calibration, detection delay, false-alert rate, revision stability, latency, cost, failures,
degraded states, leakage controls, and silence as a valid outcome where applicable.

The next bounded packet is therefore the World public measured-feedback journey. It should produce
at least one honest useful, harmful, or unproven result, have a human/Core authority explicitly
accept or reject the non-effective proposal through a separate governed transition, reproduce from
public data after restart, and leave Market able to falsify the same contracts independently.

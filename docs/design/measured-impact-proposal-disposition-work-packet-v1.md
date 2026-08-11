# Measured-impact proposal disposition work packet (v1)

**Status:** bounded stacked implementation candidate; this packet does not complete issue
[#38](https://github.com/augmented-cognition-engine/core/issues/38), apply a governance proposal,
pass SI4, or close the 0.6.0 release.

**Frozen:** 2026-08-10 from the Measured Intelligence kickoff candidate at
`9078018a5fd3c310011b6c9efbfe5255e0e36887`.

## Objective

Close the smallest missing governance step after measured-impact evaluation: let one exact,
authenticated, authorized reviewer accept or reject one exact non-effective proposal through a
durable Core Decision without changing the evaluation, applying the proposed action, or mutating
effective governed state.

The World proving case deliberately separates product measurement from governance judgment. Its
frozen structural citation-coverage criterion classifies the result as useful and maps that result
to `promote`; a separately authorized reviewer rejects broader promotion because that bounded
measure does not establish citation correctness, general Brief quality, causality, human benefit,
or live freshness.

## Ownership boundary

- **Core** owns authenticated identity, exact immutable record coordinates, authority closure,
  Decision, append-only persistence, and governed-state preconditions.
- **Intelligence** continues to own the domain-neutral evaluation and non-effective proposal
  material introduced by the kickoff packet; this packet does not change those contracts.
- **Application composition** exact-loads the proposal, evaluation, and target, resolves current
  Core authority, and appends one generic Core Decision.
- **Products and Domain Packs** own reviewer-role meaning, rationale, product policy, and any later
  separately authorized application of an accepted proposal.

The public `ace` packages import no `core.engine` implementation. The word `human` is a product
policy claim about an authenticated principal and governed role/grant; this neutral Core contract
does not claim to prove biological personhood.

## Frozen disposition contract

`MeasuredImpactDispositionRequestV1Alpha1` binds:

1. one product and authenticated runtime context;
2. the exact evaluation and proposal `ImmutableRecordReferenceV1` values from one atomic measured-
   impact closure;
3. one reviewer-role reference;
4. an `accept` or `reject` disposition, rationale, and decision time; and
5. the exact proposal availability and authentication window.

The service exact-loads and revalidates the durable envelopes, requires the proposal to bind the
evaluation identity, digest, target, and evaluation time, and exact-loads the target. It then
creates a normal `DecisionV1Alpha1` whose subject is the exact proposal, whose decision type is
`impact_governance_proposal_disposition`, and whose action disposition is always `no_action`.

`accept` means that the reviewer accepts the proposal for a possible later governance path;
`reject` means that the exact proposal is declined. Neither value applies `promote`, `reject`,
`rollback`, or `retire`, changes selectability, or mutates a governed head.

## Authority, history, and replay

New disposition writes require current authorization against both the evaluation criterion head
and the disposition operation head. A stronger authority projection may add exact capability or
grant heads, but it must preserve every requested frozen head exactly. Denial, changed heads,
expired authority, unavailable records, cross-product material, or mismatched evaluation/proposal
lineage fails closed before a Decision is appended.

The transaction key is derived from the exact proposal reference. One proposal therefore receives
one append-only disposition through this service: exact replay returns the historical Decision
without reauthorization, while a contradictory second disposition conflicts instead of replacing
history. The immutable-store preconditions make criterion or authority drift fail atomically.

## Executable acceptance and negative controls

The candidate must prove:

- both accept and reject create exact `no_action` Decisions and leave governed heads unchanged;
- the Decision subject is the exact proposal and the proposal still binds the exact evaluation;
- exact replay survives criterion-head advance and does not call the authorizer;
- a contradictory second disposition cannot rewrite history;
- mismatched evaluation/proposal, cross-product material, and unsupported dispositions fail closed;
- denied, changed, or stale authority appends no Decision;
- stricter current authority closure is retained on the immutable transaction;
- an interrupted append leaves no partial Decision; and
- production SurrealDB persistence reopens the exact Decision from a fresh service and fresh Python
  process without duplicate append or reauthorization.

## Files owned by this packet

- `ace/application/measured_impact_disposition.py`
- the minimal `ace.application` public export additions
- `tests/intelligence/test_measured_impact_disposition.py`
- `tests/intelligence/measured_impact_disposition_restart_process.py`
- this packet, its candidate evidence, and restrained roadmap/maturity references

## Exclusions, rollback, and deletion criteria

This packet changes no package version, database schema, CLI, MCP tool surface, existing Decision,
Action, Outcome, evaluation, or proposal shape. It adds no proposal-application API, autonomous
optimization, source policy, World noun, or release automation.

Rollback removes the additive service, exports, tests, and candidate documentation. Any Decisions
already recorded by a host remain immutable audit history. Delete or supersede this alpha contract
before release if a later governance path cannot consume the generic exact-subject Decision without
weakening authority, replay, or the non-applying boundary.

## Remaining release work

This packet and World P2C4 demonstrate an explicit authorized rejection over recorded official
public data, but they do not establish broader outcome quality or a supported 0.6 artifact. The next
bounded measurement packet should add an independently reviewed product outcome such as citation
correctness, contradiction coverage, correction quality, detection delay, or false-alert rate.
A proposal-application packet is separate and should exist only when product policy and explicit
Core authority justify changing effective state.

Issue [#49](https://github.com/augmented-cognition-engine/core/issues/49) findings F1, F3, and F5
still require explicit 0.6 release-owner disposition. This packet does not implement, re-date, or
silently absorb them.

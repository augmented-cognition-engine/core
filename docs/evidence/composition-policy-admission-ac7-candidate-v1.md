# AC7 composition-policy admission candidate evidence v1

- Date: 2026-08-12
- Exact base: `79629ed4da17908b194df5c2d64ae7ec1a00dcbd`
- Candidate branch: `codex/v0.7-composition-policy-admission`
- Status: local stacked candidate; draft publication pending final verification

## Candidate claim and limit

One exact inert AC6 `CompositionPolicyChangeProposalV1Alpha1` can traverse a separate,
present-tense governed lifecycle: independent review, rejection or approval, Core authority
resolution, compare-and-swap admission, bounded runtime resolution, suspension, recovery,
supersession, and rollback. The proposal remains evidence forever and never becomes policy or
authority by itself.

AC6 proved one narrow provider-free condition among fourteen. AC7 does not generalize that result,
establish that dynamic composition is generally beneficial, complete integrated 0.7 acceptance,
or begin an AC8+ implementation sequence. Composition implementation freezes after this closeout
pending cumulative 0.7 integration and release reconciliation.

## Frozen admission coordinates

- AC6 proposal:
  `composition_policy_change_proposal:1deb3eff369eec029b627ce10d4b9f9e`
- AC6 comparison:
  `composition_matched_comparison:9b2a6152b28766bb323fa247405916a1`
- Admission plan: `composition_policy_plan:47a32ab8beedeebf93fe69f13774aa00`
  (`sha256:47a32ab8beedeebf93fe69f13774aa00235ea73a6288f2b006769ab1b854602e`)
- Admission request: `composition_policy_request:e2b3a34acae4ee36cea8c21c57d47e50`
- Independent review: `composition_policy_review:d6254c4dfc95aac938d660641d336798`
- Policy revision: `composition_policy_revision:28148e08f4d788ef628864481e6c72db`
  (`sha256:28148e08f4d788ef628864481e6c72db3779f2912d07d9a23e4e212513ac82eb`)
- Core commit receipt: `governed_state_commit:d6322b2cb8f978197bdceac1162b2ac1`
- Admission receipt: `composition_policy_admission:0db5d63a721dd3121dd42a4b89cb32fa`
- Runtime resolution: `composition_policy_runtime:e62fc2f7fe62d79e842d7bed33137d13`
  (`sha256:e62fc2f7fe62d79e842d7bed33137d13c0faaf96cdde5cbe3a751f08f1d8b01b`)

The frozen packet and result are
`evaluations/fixtures/ac7_composition_policy_admission_conformance_v1.json` and
`evaluations/results/ac7_composition_policy_admission_v1.json`. The fresh-process verifier reports
fixture digest `sha256:4d3673f3b6b66014794b176f6abe4859f7e5a85987c5652ab219edf9354cf03a`
and result digest `sha256:cfe24935c3817ab5064c6859ed1aa1665e726734e78bac72cd0a65fd513416ee`.

## Positive lifecycle and fail-closed proof

The provider-free journey admits an exact active head, resolves a bounded non-reusable runtime
receipt, suspends and refuses runtime use, recovers under a new approval/authority transaction,
reopens the exact durable chain after restart, supersedes through a distinct durable proposal, and
rolls back through a new present-tense transaction targeting an exact earlier active revision.
Concurrent transitions from the same expected head allow exactly one winner.

The frozen seventeen-case matrix covers missing/foreign/fabricated proposal, protocol/comparison
drift, threshold failure, self-approval, missing/wrong/stale/revoked/expired/rotated authority,
actor/principal/scope/policy mismatch, stale head, concurrent adoption, duplicate nonce conflict,
tampered revision, future evidence, suspended policy, forbidden roster/authority/model/delivery/
effect mutation, proposal self-activation, historical-authority rollback, stale cached policy after
restart, and unavailable durable owners.

Runtime policy is selection-only. Its receipt fixes `reusable=false`, `grants_authority=false`, and
`makes_participant_eligible=false`. AC2/AC4 authority and participant eligibility, task scope,
budgets, delivery/export permissions, and effect admission remain separate current-head checks.

## Verification record

| Check | Result |
|---|---|
| Focused AC7 contracts, lifecycle, rejection, CAS/concurrency, restart, deterministic-process, matrix and result verifier | 7 passed |
| AC2/AC4/AC5/AC6/AC7 stacked regression | 77 passed |
| Package identity, Core boundary, naked kernel, contract boundary and thin MCP client | 57 passed |
| Full non-E2E/non-extension lane | 7,468 passed, 241 skipped, 261 deselected; four sandbox-only localhost socket failures listed below |
| Changed-file Ruff and format | Passed |
| Lock and diff checks | Passed |
| Secret scan over every AC7-owned path | Passed |
| Thin public MCP count | Exactly 11 |
| Scoped authority/effect/domain/AM1 scan | No domain vocabulary, AM1 dependency, Agent Memory write, public TaskCreate change, provider route, delivery/export/effect adapter, or authority creation path |

The four broad-suite failures were environmental and outside AC7: two Canvas proxy tests could not
bind loopback ports 8799/8801; the egress-guard loopback connect probe was denied; and the startup
no-DB test could not bind an ephemeral loopback port. Each trace was `PermissionError: [Errno 1]
Operation not permitted`. No AC7-focused or stacked regression failed.

An initial isolated `uv` bootstrap also attempted to restore dependencies and was blocked by
sandbox DNS while fetching `pydantic-core==2.41.5`. No dependency or lock change was needed. All
verification then used the existing complete locked repository runtime. A repository-wide Ruff
format check identified six pre-existing unrelated files that the installed Ruff would reformat;
AC7-owned files pass exact format checks and those baseline files were preserved.

## Installed-wheel proof and preservation

- Wheel: `ace_core-0.6.0-py3-none-any.whl`
- The final verification-build SHA-256 is recorded in the stacked PR/control-tower handoff rather
  than embedded here, avoiding a self-referential digest in a document packaged inside the wheel.
- A checkout-free target installation imported
  `ace.application.composition_policy_admission` and
  `ace.intelligence.contracts.composition_policy` through their public package surfaces.
- The wheel contains the AC7 contracts, service, fixture, result, verifier, design packet, and this
  evidence record.

AC7 adds no schema, endpoint, CLI command, TaskCreate field, MCP tool, provider dependency,
credential, external repository edit, Domain Pack noun, AM1 dependency, or Agent Memory write.
Package identity remains `ace-core`; the naked kernel and exactly eleven thin public MCP tools are
unchanged.

## Release and integration entry gate

The candidate may enter integrated 0.7 acceptance only after its stacked draft PR is reviewed
against exact AC6 base/head, the production Core adapters demonstrate the same atomic head-CAS and
immutable audit behavior, and cumulative AC1–AC7 plus independent product integration passes. This
candidate must not be merged, released, tagged, or published by itself and does not declare 0.7
ready.

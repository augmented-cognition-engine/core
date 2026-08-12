# AC7 composition-policy admission work packet v1

- Date: 2026-08-12
- Status: implementation candidate; AC6 closeout, not a supported product or 0.7 acceptance claim
- Exact AC6 source head: `79629ed4da17908b194df5c2d64ae7ec1a00dcbd`
- Stack base: `codex/v0.7-agent-measured-composition`

## Outcome and finite boundary

AC7 closes the governance gap deliberately left by AC6. It provides the separate present-tense
path by which one exact, inert `CompositionPolicyChangeProposalV1Alpha1` may be independently
reviewed, rejected, approved, admitted as a current policy head, superseded, suspended, recovered,
or rolled back. AC7 does not begin an AC8+ implementation sequence. Composition implementation
freezes after this packet pending cumulative integrated 0.7 acceptance and release reconciliation.

This candidate does not claim that 0.7 is complete. AC6 proved only that one provider-free fixture
cleared one of fourteen frozen conditions. AC7 neither generalizes that result nor makes AC6
evaluation evidence live authority.

## Admission packet and owners

The additive public packet is:

1. `ace.intelligence.composition-policy-admission-plan/v1alpha1` — exact scope, AC6 lineage,
   expected head, action, bounded selection constraints/preferences, rollback target, and all
   forbidden-effect flags fixed false;
2. `ace.intelligence.composition-policy-admission-request/v1alpha1` — exact actors/principals,
   current Core heads, approval/grant references, expected head, time window, and stable nonce;
3. `ace.intelligence.composition-policy-review/v1alpha1` — independent human/service disposition
   over the exact plan and request, applying no policy itself;
4. `ace.intelligence.composition-policy-revision/v1alpha1` — immutable projected configuration;
5. admission, rejection, and runtime-resolution receipts over exact content addresses and heads.

Core remains the authority and durability owner. `CoreAuthorityResolver` resolves exact approval
and current `administer_composition_policy` authority. `GovernedStateStore` owns the current
`composition_policy` head and compare-and-swap revision commit. `ImmutableRecordStore` owns plans,
requests, reviews, rejections, and durable audit. AC7 adds no parallel grant, approval, database,
or authority system.

## AC6 dependency and revalidation

Admission exact-loads the durable AC6 protocol, assignment, observations, comparison, and proposal.
It recomputes the matched comparison and proposal under the frozen protocol, requires the exact
positive result to remain satisfied, and verifies that every proposal live/effect/authority flag
remains false. Missing, foreign, future, tampered, scope-crossed, or threshold-failing evidence
fails closed. The proposal remains evidence forever and cannot approve or admit itself.

## Lifecycle and runtime

- Rejection durably records exact reasons and creates no policy head.
- First admission expects no current head. Every later transition carries the exact current head.
- Supersession requires a distinct durable AC6 proposal plus a new plan, request, review, approval,
  authority resolution, and Core commit.
- Rollback is a new present-tense approved transaction targeting an exact earlier active revision;
  the earlier approval and commit remain audit evidence only.
- Suspension and recovery are explicit CAS-protected head revisions. Suspended policy never
  resolves for runtime use.
- Restart reopens the exact head, revision, and Core receipt; history is never treated as current
  authority.

Runtime resolution returns one exact, bounded, non-reusable receipt over the current active policy
head plus current authority/configuration heads. Its constraints/preferences can inform selection
only. AC2/AC4 execution authority, participant heads and eligibility, task scope, budgets,
delivery/export permissions, and effect admission remain separate present-tense checks. Policy
never grants authority or makes an ineligible participant eligible.

## Preservation and acceptance gate

AC7 adds no TaskCreate field, endpoint, CLI command, public MCP tool, provider, credential, schema,
Domain Pack noun, AM1 dependency, or Agent Memory write. Package identity, naked-kernel behavior,
and the exactly eleven thin public MCP tools remain unchanged.

Acceptance requires the deterministic provider-free lifecycle and fail-closed fixture, CAS and
concurrency controls, restart/reopen determinism, installed-wheel import/execution proof, focused
and broad regression, Ruff/format/lock/diff scans, and authority/effect/domain/AM1/MCP/secret
scans. Publication remains a stacked draft PR only; merge, release, tag, and package publication
are outside this packet.

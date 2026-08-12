# AC4 agent onboarding and governance work packet v1

- Date: 2026-08-12
- Status: **0.7G AC4 implementation candidate; not a supported product claim**
- Stack base: `codex/v0.7-agent-composition-pipeline` at `26fa78d`
- Architecture authority: `agent-composition-lifecycle-v1.md` from the preserved source checkout
- Control-tower identity decision: additive option A with stable coordinate plus exact registration snapshot

## Outcome

AC4 adds a provider-neutral application journey that can inspect, propose, review, approve, activate,
suspend, revise, revoke, retire, reopen, and audit bounded agent governance without treating code
installation, discovery, model output, conformance, requested grants, or health as authority.

The implemented separation is:

```text
stable governance coordinate
  != immutable AC1 registration snapshot
  != definition content revision
  != binding content revision
  != requested grants
  != current Core grant
  != runtime health
  != activation or runtime authority
```

AC4 does not add an endpoint, CLI command, MCP tool, provider adapter, credential store, external
effect, delivery path, marketplace, UI, lifecycle-stage adapter, or autonomous spawn path.

## Frozen AC1 preservation and identity decision

`AgentPrincipalV1Alpha1` remains byte-for-byte unchanged. Its content-addressed identity includes
its bootstrap `lifecycle` and `lifecycle_revision` fields, so AC4 treats it as an immutable
registration snapshot. `GovernedAgentDefinitionRevisionV1Alpha1.principal_id` continues to bind
that exact snapshot identity.

`AgentGovernanceCoordinateV1Alpha1` is the new stable lookup coordinate. It contains only
`product_id`, `principal_key`, and `governance_id`, with the ID derived only from the first two
fields. Lifecycle, owner, implementation, protocols, snapshot, approval, grant, health, and
authority are excluded. The first explicit lifecycle revision starts suspended and exact-references
the AC1 snapshot. Updated registration material creates a new AC1 snapshot under the same stable
governance coordinate; existing definitions and bindings become ineligible until separately revised.
The lifecycle revision copies the snapshot implementation and supported-protocol material so eligibility
can validate compatibility and health without retargeting or rewriting the frozen AC1 artifact.

There is no automatic migration or reinterpretation of existing AC1 compatibility participants.

## Contract coordinates

| Owner | Contract | Purpose |
|---|---|---|
| Core | `ace.core.agent-governance-coordinate/v1alpha1` | Stable `(product_id, principal_key)` lookup only |
| Intelligence | `ace.intelligence.agent-principal-lifecycle-revision/v1alpha1` | Exact registration snapshot and current lifecycle lineage |
| Intelligence | `ace.intelligence.agent-definition-proposal/v1alpha1` | Immutable author-controlled definition proposal |
| Intelligence | `ace.intelligence.agent-binding-proposal/v1alpha1` | Immutable author-controlled binding proposal |
| Intelligence | `ace.intelligence.agent-governance-diff/v1alpha1` | Deterministic inspectable semantic diff |
| Intelligence | `ace.intelligence.agent-review-disposition/v1alpha1` | Exact human/Core review whose identity excludes projected result fields |
| Intelligence | `ace.intelligence.agent-definition-lifecycle-revision/v1alpha1` | Current definition content plus separate lifecycle state |
| Intelligence | `ace.intelligence.agent-binding-lifecycle-revision/v1alpha1` | Current binding content plus separate lifecycle state |
| Intelligence | `ace.intelligence.agent-grant-request-lifecycle-revision/v1alpha1` | Inert requested-grant head |
| Intelligence | `ace.intelligence.agent-runtime-health-revision/v1alpha1` | Health evidence that can only constrain eligibility |
| Intelligence | `ace.intelligence.agent-compatibility-receipt/v1alpha1` | Protocol compatibility evidence, no effect |
| Intelligence | `ace.intelligence.agent-conformance-receipt/v1alpha1` | Conformance evidence, no effect |
| Intelligence | `ace.intelligence.agent-dry-run-receipt/v1alpha1` | Zero-tool, zero-authority, zero-external-effect dry run |
| Intelligence | `ace.intelligence.agent-activation-receipt/v1alpha1` | Exact five-head and admitted-grant eligibility evidence; not reusable authority |
| Intelligence | `ace.intelligence.agent-compatibility-replacement-receipt/v1alpha1` | AC3/AC5 no-effect replacement seam without history rewrite or authority carry-forward |

## Existing seams reused

AC4 uses `GovernedStateStore`, `CoreAuthorityResolver`, `ResolvedApprovalReceiptV1`,
`ResolvedAuthorityGrantV1`, and Core governed-state revision/head/commit/audit receipts as the only
mutable current-state and authority-admission plane. It uses `ImmutableRecordStore` for append-only
proposal, diff, review, evidence, activation, replacement, and audit records. Activation appends
under exact multi-head preconditions, so any head movement makes the prior receipt stale.
Every lifecycle admission also appends the exact lifecycle revision and Core commit receipt to that
audit plane; reopen validates head, payload, actor, approval, authority, chronology, and receipt closure.

Governed cognition supplies the proposal/diff/review lineage pattern, including result fields that
do not create circular receipt identities. Its dedicated policy, store, and approval-activates-head
semantics are not reused. AC4 creates no second permission or persistence system.

## Lifecycle and authority matrix

| Dimension | Current states | Can grant authority? | Eligibility requirement |
|---|---|---:|---|
| Principal lifecycle | suspended, active, revoked, retired | No | exactly active |
| Definition lifecycle | approved, active, suspended, revoked, superseded, retired | No | exact current active content and snapshot alignment |
| Binding lifecycle | approved, active, suspended, revoked, superseded, retired | No | exact current active narrowing and snapshot alignment |
| Grant request lifecycle | requested, withdrawn, revoked | No | exact current requests; each request re-resolved through Core |
| Runtime health | healthy, degraded, unavailable, quarantined | No | exactly healthy |
| Compatibility/conformance/dry run | passed or failed evidence | No | exact current registration/definition/binding, non-future, and passing |
| Activation receipt | no-effect eligibility evidence | No | all five heads current, lifecycle administrator current, and every requested grant currently admitted |
| Runtime execution | outside AC4 | Only through existing Core runtime resolution | must revalidate current AC4 and Core grant/capability/configuration heads |

Approval, lifecycle activation, grant request, actual grant admission, roster selection, and runtime
use each retain a separate identity and receipt. Definition or binding activation requires a current
`administer_lifecycle` grant. Principal onboarding, activation, suspension, revocation, snapshot
supersession, and retirement require the same separately resolved administrative authority. An agent
cannot approve or activate itself. The activation receipt retains exact resolved grant hashes,
authority classes, effective times, and expiries for audit, while remaining explicitly non-reusable.

## Deterministic conformance

`evaluations/fixtures/ac4_agent_onboarding_governance_conformance_v1.json` freezes deterministic
service, model-agent, adversarial-definition, stale-approval, widened-binding, revoked-grant,
incompatible-protocol, and retired-principal cases. Focused tests prove stable identities, proposal
and diff lineage, five independent heads, no-effect evidence, current-grant resolution, stale-head
failure, restart/reopen, registration supersession, immutable audit retention, and zero audit writes
on refusals.

## AC3 and AC5 convergence

AC4 remains an AC1 sibling and imports no AC3 adapter or AC2 runtime service. AC3 compatibility
`ADAPTER` and `DETERMINISTIC_SERVICE` participant references remain historical, candidate-only
references with no invented governance identity.

AC5 can create an `AgentCompatibilityReplacementReceiptV1Alpha1` only after a separate AC4
durably recorded activation transaction proves the exact current stable governance coordinate, registration snapshot,
definition, binding, requested-grant head, health head, passing evidence, and Core-current grants.
The replacement receipt retains the opaque compatibility participant reference and exact eligible
AC4 coordinates while fixing `rewrites_history=false`, `carries_authority_forward=false`, and
`reusable_authority=false`. AC5 must revalidate current heads and runtime authority at use time; it
cannot replay the activation or replacement receipt as a grant. Replacement re-resolves the lifecycle
and requested grants at replacement time, so revoked authority cannot be carried into the handoff.

## Hard exclusions and limitations

- No AC2 runtime authority implementation or modification.
- No AC3 lifecycle participant adapter or history rewrite.
- No AC5 delivery/export/external-agent protocol, destination, or external effect.
- No provider SDK, route, model selection, credential, endpoint, UI, schema, or marketplace.
- No public AgentPrincipal v1alpha2 or migration.
- No self-approval, self-activation, self-spawn, automatic discovery onboarding, or installation grant.
- No AM1 dependency and no domain vocabulary in Core.
- AC2 pre-execution integration of the five AC4 head preconditions remains a downstream stacked
  adapter responsibility; AC4 does not modify the sibling AC2 runtime-authority implementation.

Rollback is removal of the additive AC4 contracts, services, fixtures, tests, and documentation.
No frozen AC1 identity, MCP surface, database schema, provider route, or external state is migrated.

# AC1 provider-neutral agent-composition contracts and ports work packet v1

- Date: 2026-08-11
- Status: **0.7G AC1 implementation candidate; not a supported product claim**
- Stack base: `codex/v0.7-intelligence-builder-map` at `e1f6492`
- Architecture authority: `agent-composition-lifecycle-v1.md` from the preserved source checkout
- Dependency posture: independent of unpublished 0.7D runtime code, AM1, and lifecycle-stage wiring

## Outcome

This packet adds the smallest provider-neutral AC1 contract and port foundation for lifecycle-wide
agent composition. It preserves the canonical separation:

```text
agent principal
  != governed definition revision
  != stage-role binding revision
  != task composition plan
  != stage-run manifest
  != stage-run receipt
  != stage-handoff or delivery receipt
```

It adds no schema migration, provider adapter, model route selection, active agent, runtime stage,
activation authority, delivery effect, endpoint, CLI command, or MCP tool.

## Existing-path inventory and disposition

| Existing path | AC1 disposition |
|---|---|
| Orchestrator classifier | Future typed requirement contribution to Compose; never authority |
| `CognitiveComposer` and composition scorer | Candidate/roster-policy inputs; not the canonical task graph |
| Recipes, phases, instruments and advisory tool slots | Exact governed procedure/cognition references; not principals, grants or manifests |
| I2 deliberation receipt | Future AC2 contributor, conflict, synthesis and degraded-coverage bridge; preserve execution attribution |
| I3 intelligence-use receipt and Context Manifest lineage | Opaque exact artifact references only; AC1 does not fork or reinterpret AM0/I3 types |
| Task and attempt receipts | Existing execution context and replay lineage; not agent identities |
| Orchestration `AgentConfig`, `AgentResult` and pattern results | Host adapter inputs/outputs only; ephemeral IDs and prose handoffs are non-conforming |
| MAKE/SHIP arms | Later Act/Verify participant adapters behind governed action contracts |
| Sentinel engines | Later Detect/Observe scheduled participants; trigger policy never grants authority |
| Legacy handoff dispatcher and bus handoff events | Non-canonical compatibility paths; typed stage handoff and external delivery remain separate |
| Core reasoning binding and provider route | Exact execution binding belongs in a manifest; observed route belongs only in a run receipt |
| Core immutable records, state preconditions and authority-use receipts | Reused substrate for future persistence/admission adapters; not reimplemented here |

## Contract ownership

### Core

`ace.core.agent_composition` owns:

- stable product-scoped agent principals with no embedded grant, provider, context or memory;
- exact opaque artifact references;
- historical Domain Activation lineage with `live_authority=false`;
- multi-dimensional authority coordinates;
- task composition plan, graph node, participant, manifest, run, stage-handoff and delivery identities;
- exact usage, context-use-state and terminal-state receipt vocabulary; and
- intended-versus-actual validation that prevents tools, authority or budgets from widening at run
  time.

The canonical task-time identity prefix is `task_composition_plan:`. No bare `plan_id` field is
published.

### Intelligence

`ace.intelligence.contracts.agent_composition` owns:

- the fourteen lifecycle-stage meanings frozen by AC0;
- conservative orchestration patterns: deterministic, solo, pipeline, fanout/join, adversarial,
  quorum, human gate and scheduled;
- governed definition and stage-role binding revisions;
- semantic narrowing validation for tools, sources, destinations, contract families, authority and
  budgets;
- requirements, authorization/compatibility candidates and roster dispositions; and
- instruction contributions and the exact canonical precedence receipt.

The instruction receipt carries identities, constraints, issues and resolution results. It does not
publish prompt bodies, source content, credentials, hidden reasoning or private context.

### Application

`ace.application.agent_composition` exposes only provider-neutral protocols for:

- planning;
- Context Manifest resolution;
- immutable manifest compilation;
- stage execution;
- deterministic join;
- prepared typed stage handoff; and
- a separately typed, intentionally unimplemented delivery-effect seam.

Adapters own storage, provider execution, sources, destinations and transport.

## Instruction precedence and authority

The implemented precedence is:

1. Core invariants;
2. runtime authority and safety;
3. Domain Activation policy;
4. governed agent-definition revision;
5. stage-role binding;
6. task brief;
7. authorized Context Manifest; and
8. handoff or destination contract.

Resolution is deterministic and intersection-only. A missing required layer blocks resolution with
`ace.composition.instruction.missing_required_layer`. Context Manifest content remains data-only;
separately governed instruction policy must arrive as its own exact policy contribution. A task,
retrieved document, preview, contributor output or model-generated approval cannot create a grant,
add a tool, activate a plan, select a destination or authorize delivery.

## Deterministic conformance fixtures

`evaluations/fixtures/ac1_agent_composition_conformance_v1.json` freezes five shapes:

| Shape | Required proof |
|---|---|
| Solo | One exact principal/definition/binding and one typed output |
| Pipeline | Declared dependencies and schema-bearing edges; prose alone is not a handoff |
| Fanout/join | Independent participants and an explicit deterministic join, including partial coverage |
| Adversarial | Independently attributable producer/challenger; malicious context cannot self-spawn, activate or deliver |
| Human gate | A declared human participant and exact approval authority; generated approval text is insufficient |

The focused tests prove stable identities across replay and semantically irrelevant input ordering,
frozen manifests, role-binding narrowing, complete instruction precedence, authorization-first
intersection, activation-lineage non-authority, AM0 identity separation, observed-route separation,
run subset validation, declared human gates and import boundaries.

## Future classify → compose → engage → synthesize bridge

AC2 should be an adapter sequence, not a rewrite:

```text
existing classification
  → typed composition requirement
  → existing composer/recipe candidate contributions
  → authorization-first roster receipt
  → opaque Context Manifest resolution
  → immutable participant manifests
  → existing engagement execution adapters
  → run receipts + existing I2 contributor artifacts
  → explicit deterministic/adversarial join
  → typed stage handoff
```

The bridge must preserve existing recipe and instrument revisions, I2 execution-unit attribution,
I3 eligible/authorized/selected/injected/reflected/decision-material lineage, failure/taint/partial
coverage, existing task behavior and the exact eleven-tool public MCP surface.

No AC2 wiring begins until the control tower supplies the exact completed dependency branch and
commit.

## Dependency handoffs

### 0.7D Watch + Brief

AC1 provides `ExactArtifactReferenceV1Alpha1` and `trigger_artifacts` as the future typed seam for
the exact approved Watch proposal and inert cited Brief preview identities. It deliberately does
not guess or publish their unfinished contract names. The preview is neither an activated runtime
stage output nor evidence of scheduling, delivery, execution authority or activation.

### 0.7E Activate + prove

The accepted historical seam is
`ace.application.domain-activation-commit-reference/v1alpha2`. AC1 wraps that exact opaque reference
only in `DomainActivationLineageV1Alpha1`, whose `live_authority` field is literally false. It may
support context and lineage inspection. It cannot satisfy a grant, runtime-authority, execution,
delivery, approval or lifecycle gate.

Domain Activation Plan identity, digest, approval, embedded-material admission, upgrade, rollback,
reactivation and live authority remain 0.7E-owned. A future live runtime bridge requires a separate
exact control-tower handoff; historical commit lineage must not be promoted into it.

### 0.7F Agent Memory

AC1 imports no AM0 runtime type and is not an AM1 entry dependency. Candidate Receipt and Context
Manifest/I3 lineage are carried as opaque exact references. The plan-local key is explicitly
`composition_participant_id`; it is not AM0 `ParticipantId`. AC1 defines no `ContextManifestId` or
`CandidateReceiptId` type and does not interpret opaque receipt payloads.

## Vocabulary collision ledger

| Risk | Resolution |
|---|---|
| Task Composition Plan versus Domain Activation Plan | `TaskCompositionPlanV1Alpha1`, `task_composition_plan:` and `composition_plan_id/digest` only |
| Historical activation commit versus live authority | `DomainActivationLineageV1Alpha1.live_authority=false`; separate authority coordinates are mandatory |
| AM0 `ParticipantId` versus plan-local participant | `composition_participant_id` |
| AM0 Context Manifest/Candidate Receipt IDs | Opaque `ExactArtifactReferenceV1Alpha1`; no parallel ID types |
| Principal versus persona/archetype/role | Stable `AgentPrincipalV1Alpha1`; lenses and labels never substitute |
| Host provider route versus plan policy | execution binding in manifest; actual route only in run receipt |
| Existing `independent`, `fanout`, `parallel`, `team` names | Future explicit adapters to canonical solo/fanout-join/etc.; no silent equivalence |
| Stage handoff versus external delivery | `StageHandoffReceipt` proves no external send; `DeliveryReceipt` is separate |

## Acceptance and boundaries

AC1 candidate acceptance requires:

- focused contract and conformance tests pass;
- public import-boundary tests pass;
- naked-kernel and installed-package imports remain provider-free;
- the thin public MCP server still registers exactly eleven tools;
- no schema, shared 0.7D service/session contract or release narrative is changed; and
- the exact diff contains only additive 0.7G contracts, ports, fixtures, tests and this packet.

This packet does not claim active lifecycle composition, provider interoperability, restart-durable
composition persistence, delivery, Agent Memory ingestion, autonomous spawning, dynamic-composition
benefit, or a supported 0.7G product surface.

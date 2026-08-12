# Agent Memory AM0 Work Packet v1

**Status:** contract/conformance candidate complete; draft PR authorized, runtime integration not started
**Date:** 2026-08-11
**Roadmap authority:** [`docs/design/agent-memory-roadmap.md`](agent-memory-roadmap.md)
**Companion audit:** [`docs/design/agent-memory-charter-audit-v1.md`](agent-memory-charter-audit-v1.md)

## 1. Outcome

AM0 establishes the provider-neutral vocabulary, contracts, ports, import boundaries, and conformance fixtures required for Agent Memory to be implemented safely inside ACE Core.

AM0 does not create a memory product, database, reasoning engine, MCP surface, or new top-level bounded context. It makes later AM1-AM9 work possible without allowing storage details, experimental compatibility paths, or vendor concepts to become public ACE semantics by accident.

The user-visible outcome is intentionally indirect: ACE can preserve continuity while users install,
connect sources, map concepts, receive briefings, rely on monitors for fresh updates, and provide
feedback—without managing memory architecture. Later memory features will have one stable definition
of identity, provenance, time, scope, authority, lifecycle, retrieval evidence, and material use.

### Current isolated implementation

The unstaged `codex/agent-memory-am0` worktree now contains:

- Core-owned `ace.core.agent_memory` and `ace.core.agent_memory_ports` contracts for the frozen
  identity/scope, source-coordinate, three-clock, lifecycle, ledger, authority, and erasure-proof
  boundary;
- Intelligence-owned `ace.intelligence.contracts.agent_memory` contracts and Protocols for memory
  families, epistemic state, semantic query, ranking contributions, candidates, reconciliation,
  graph/query repositories, context composition, and evolution proposals;
- a lineage-only bridge to existing `ace.context.manifest/v1` and
  `intelligence-use-receipt-v1` identities, with no competing use-state fields; and
- focused contract, hostile/unknown case, import-boundary, MCP-inventory, replay, atomic-failure,
  product-scope, and canonical-source bridge tests.

Verification evidence and the one pre-existing worktree limitation are recorded in
[`agent-memory-am0-migration-plan-v1.md`](agent-memory-am0-migration-plan-v1.md).
Threat controls and their executable evidence are mapped in
[`agent-memory-am0-threat-model-v1.md`](agent-memory-am0-threat-model-v1.md).

## 2. Entry conditions and authority

### Entry conditions

- The Agent Memory roadmap is the governing sequence.
- The existing 11-tool public MCP contract remains unchanged.
- SurrealDB remains the first persistence adapter, not the public semantic boundary.
- Existing Grounded State, governed cognition, L1, and I1-I3 work may be reused only through explicit bridges.
- The project owner has declared the Core 0.6 technical work complete.

### Baseline reconciliation

The isolated AM0 branch begins at current `origin/main` commit `492b99667b0a119234d4a8af26e448254c0a6abd`, where package identity, capability maturity, roadmap, and release evidence agree on public Core `0.6.0`. AM0 treats that release as closed and reusable. It neither reopens 0.6 nor treats its L1/I3 evidence as Agent Memory-specific evidence.

### Authority granted by AM0

AM0 may add:

- additive, provider-neutral contract types;
- Core ledger/dependency ports and Intelligence reconciliation/query/projection ports;
- bridge interfaces to existing ACE capabilities;
- conformance fixtures and architecture tests;
- documentation and decision records.

AM0 may not:

- add or rename a public MCP tool;
- make a database schema authoritative;
- migrate or delete existing records;
- promote captured or retrieved content into belief or truth;
- grant an extension, model, telemetry process, or adapter new authority;
- reclassify experimental behavior as supported without its own evidence gate.

## 3. Scope

### In scope

1. Canonical Agent Memory vocabulary and identifiers.
2. Three independent temporal dimensions: ledger order, knowledge time, and world time.
3. Exact-source-span representation, including explicit unknowns.
4. Authenticated product, actor, session, source, visibility, and retention scope.
5. Authority, epistemic state, lifecycle state, and semantic family as separate dimensions.
6. Provider-neutral persistence, graph-projection, query, lifecycle, and dependency-index ports.
7. Bridges to Grounded State, governed cognition, measured intelligence, context manifests, and current source/session candidates.
8. Import-boundary and storage-conformance tests.
9. Classification of existing implementation paths as canonical, bridge, experimental, compatibility-only, or retirement candidates.
10. A closeout checklist that reconciles authoritative documentation and release claims.

### Out of scope

- Database migrations or a production Agent Memory schema.
- Full session ingestion and idempotent replay implementation (AM1).
- Durable ledger and reconciliation runtime implementation (AM2).
- Context assembly, ranking, graph expansion, or budget allocation (AM3-AM4).
- Hard-erasure runtime behavior (AM4) or reflection and consolidation behavior (AM5).
- Evaluation claims beyond contract and architecture conformance (AM6).
- A second storage backend implementation (AM9).
- A new top-level `ace.memory` package.
- An onboarding agent, source-connection workflow, ontology mapper, briefing generator, monitor scheduler, or user-interface implementation.
- Copying Spectron or another vendor's APIs, schemas, identifiers, generated clients, runtime dependencies, or documentation language.

## 4. Bounded-context placement

Agent Memory is a cross-cutting capability assembled from existing ACE bounded contexts. AM0 must preserve the following ownership split.

| Owner | AM0 responsibility | Must not own |
|---|---|---|
| `ace.core` | Memory identity/scope, exact source coordinates, ledger/knowledge/world time, append-only lifecycle, authority bindings, opaque immutable receipts, ledger ports, and erasure dependency proof | Semantic query, ranking, candidates, graph meaning, selection/composition, belief policy, memory-family meaning, or database-specific types |
| `ace.intelligence` | Semantic memory families and epistemic state, reconciliation/evolution proposals, semantic query, ranking contributions, candidate records/receipts, graph/query ports, selection, context composition, uncertainty, correction, and durable cognitive-memory policy | Concrete persistence or product orchestration |
| `ace.application` | Use-case orchestration and composition of Core and Intelligence ports | New foundational semantics or adapter leakage |
| Existing `core.engine` adapter boundary | First SurrealDB implementation and temporary bridges from legacy runtime paths | Public contracts, concrete `RecordID` leakage, or semantic authority |

No contract module may import FastAPI, the SurrealDB driver, `RecordID`, a concrete repository, an extension package, or an MCP server module.

## 5. Canonical vocabulary

### 5.1 Stable identifiers

AM0 defines opaque, typed identifiers for:

- `SessionId`
- `TurnId`
- `ParticipantId`
- `SourceId`
- `SourceVersionId`
- `SourceSpanId`
- `AssertionId`
- `LedgerEntryId`
- `LifecycleEventId`
- `QueryId`
- `CandidateReceiptId`
- `ContextManifestId`
- `EvolutionProposalId`

Identifiers are storage-neutral strings or value objects. Database record identifiers are adapter-private. Canonical identity derivation must be deterministic where replay/idempotency requires it, and the derivation version must be explicit.

### 5.2 Semantic families

Every memory assertion declares exactly one semantic family:

- `episodic_experience`
- `identity_assertion`
- `learned_fact`
- `active_context`
- `preference`
- `instruction_policy`
- `uncertainty`
- `correction`
- `durable_cognitive_memory`

The family is not a truth or trust score. It determines which reconciliation policy is eligible to evaluate the assertion.

### 5.3 Separate dimensions

The following dimensions must never be collapsed into one confidence or trust value:

| Dimension | Question answered | Example states |
|---|---|---|
| Provenance | Where exactly did this come from? | source, version, span, author, capture method |
| Authority | Who may assert or change this? | user, system policy, product operator, model proposal, external source |
| Reliability | How dependable is the source for this claim type? | measured or unknown |
| Epistemic state | What does ACE currently know about the assertion? | observed, proposed, accepted, disputed, rejected, superseded, unknown |
| Confidence | How strongly does the relevant actor support the assertion? | bounded value plus method, or unknown |
| Freshness | How current is the supporting evidence for the present task? | measured from an explicit selector, or unknown |
| Validity | Does the assertion apply in the requested world-time interval? | valid, invalid, open, unknown |
| Relevance | Does the assertion help this query? | query-specific score and receipt |
| Retention | May the data continue to be stored or derived? | active, restricted, expired, erase-pending, erased |

Repetition, retrieval frequency, similarity, graph centrality, or telemetry volume must not strengthen truth, authority, or confidence by themselves.

### 5.4 Three clocks

Each assertion and lifecycle event supports three independent temporal selectors:

1. **Ledger coordinate:** the immutable ordering/version coordinate assigned by ACE when the event is accepted into the ledger.
2. **Knowledge time:** when ACE first observed or learned the information, including an explicit `unknown` state.
3. **World time:** when the assertion is valid in the represented world, expressed as an instant, interval, open interval, recurring condition, or `unknown`.

Ingestion time may be retained as operational metadata, but it cannot substitute for unknown knowledge time or world time. Missing source time must not default to the current clock in canonical contracts.

### 5.5 Source spans

`SourceSpan` is a tagged union with explicit locator kinds:

- UTF-8 byte range;
- normalized text-character range with normalization version;
- page and bounding region;
- image/video frame and region;
- audio/video timecode interval;
- structured pointer such as JSON Pointer plus source-version identity;
- whole-source assertion;
- unknown or unavailable, with a reason.

A span is valid only against one immutable `SourceVersionId`. Adapters may translate native locators, but they may not invent exactness. When exact location is unavailable, the canonical value remains unknown/unavailable.

### 5.6 Scope and visibility

Scope is injected by authenticated Core context and is never accepted as authoritative merely because it appears in captured content.

The minimum scope tuple is:

```text
product_scope + actor_scope + session_scope + source_scope + visibility + retention_class
```

Every read, candidate generation, graph expansion, lifecycle operation, and erasure dependency walk must enforce the applicable tuple before ranking or traversal.

### 5.7 Lifecycle

Lifecycle state is event-derived, never overwritten in place. Minimum states:

- `active`
- `restricted`
- `superseded`
- `expired`
- `erase_pending`
- `erased`
- `quarantined`

Supersession changes applicability, not historical trust. Erasure is distinct from supersession and requires derivative tracking.

## 6. Provider-neutral contract set

AM0 should introduce the smallest contract set capable of supporting later milestones.

| Contract | Required content | Key invariant |
|---|---|---|
| `SourceDescriptor` | source identity, immutable version, origin, content hash, capture method, authenticated scope | Captured payload cannot define its own authoritative scope |
| `SessionRecord` | session identity, participants and roles, source references, ordered turns | Replay preserves identity and order |
| `TurnRecord` | turn identity, participant, content/source version, exact or unknown span, three clocks | No silent current-time substitution |
| `HistoricalLineageReference` | exact referenced contract, opaque committed-record reference, full material digest, fixed historical/non-live literals | External lineage can be retained but never becomes present authority |
| `MemoryAssertion` | family, normalized proposition/payload, provenance, authority, epistemic state, clocks, scope | Recording is not believing |
| `LifecycleEvent` | target, exact prior coordinate for every non-initial event, operation, actor authority, reason, timestamp, dependency intent | Lifecycle is append-only and authorized |
| `MemoryQuery` | authenticated scope, temporal selectors, eligible families/states, budgets, receiver | Authorization precedes ranking |
| `CandidateReceipt` | query/scope identity, opaque Core authorization-filter receipt, lifecycle snapshot, candidates, signals, omissions, scores, and provenance | Authorization and lifecycle filtering precede ranking; retrieval is inspectable and is not material use |
| `MemoryContextLineage` | candidate receipt plus exact existing Context Manifest item/source-receipt and optional I3 intelligence-use/decision references | It carries no duplicate selected/injected/material-use flags; those claims remain owned by Context Manifest and I3 |
| `ReconciliationProposal` | proposed assertion/evolution, evidence links, conflicts, policy version, authority required | Models and telemetry propose; they do not self-promote |

All versioned contracts must reject unknown required semantic versions safely. Unknown optional enum values may be preserved for round trip only when the consuming policy explicitly treats them as unsupported, not as a familiar default.

## 7. Storage and projection ports

Ports specify semantics, not query language or schema. Core owns only the ledger and dependency
ports. Intelligence owns reconciliation, graph projection, semantic query, selection, and context
composition ports. Meta-Intelligence is not a port-owning package or layer.

### `LedgerWriter`

- Append source, assertion, and lifecycle events atomically where the use case requires it.
- Enforce expected prior coordinate for optimistic concurrency.
- Return immutable ledger coordinates and a write receipt.
- Distinguish conflict, authorization failure, invalid contract, unavailable storage, and indeterminate outcome.

### `LedgerReader`

- Read by typed identifier and authenticated scope.
- Reconstruct state at a ledger coordinate and knowledge/world-time selector.
- Preserve unknown temporal values rather than coercing them.
- Exclude erased/restricted content before returning data unless explicitly authorized for the lifecycle use case.

### `ReconciliationRepository`

- **Owner:** Intelligence.
- Load assertions and conflicts eligible for one versioned policy.
- Persist proposals and authorized decisions separately.
- Never mutate a prior assertion to simulate correction or supersession.

### `GraphProjectionRepository`

- **Owner:** Intelligence.
- Project typed, provenance-bearing edges derived from immutable ledger entries.
- Return expansion receipts and omissions.
- Enforce authorization and lifecycle filters before traversal.
- Support rebuild from the ledger; the projection is not the source of truth.

### `MemoryQueryRepository`

- **Owner:** Intelligence.
- Produce authorized candidates and their source/version links.
- Reference the exact opaque Core authorization-filter receipt and lifecycle snapshot applied
  before candidate generation, ranking, traversal, or cache access.
- Accept explicit signal availability and budget constraints.
- Return degraded-state metadata when an index or signal is unavailable.
- Never claim that a candidate was injected or used.

### `DependencyIndex`

- **Owner:** Core.
- Record direct and derived dependencies for summaries, embeddings, caches, graph projections, and context artifacts.
- Support complete dependency enumeration for hard erasure.
- Fail closed when completeness cannot be established.
- Bind the content-free completion proof to the exact erase-pending request event.

### Transaction and retry semantics

Every mutating port defines:

- idempotency key behavior;
- expected-version behavior;
- atomicity boundary;
- retry-safe and retry-unsafe failures;
- indeterminate-outcome recovery;
- an indeterminate append error is never marked safe for blind retry and always carries the exact
  durable-receipt lookup reference required before another append;
- receipt shape;
- adapter conformance tests.

The SurrealDB adapter may use native transactions and record identifiers internally, but the port result must remain provider-neutral.

## 8. Bridges to existing ACE capabilities

| Existing capability | AM0 disposition | Required bridge behavior |
|---|---|---|
| Grounded State contracts | Canonical foundation | Reuse evidence/provenance/time concepts; do not duplicate or weaken explicit unknowns |
| Grounded State ingestion | Canonical foundation | Reuse Core-owned scope injection and deterministic identity derivation |
| Governed cognition | Canonical foundation | Route policy revisions and authorized decisions through immutable, reviewable governance |
| Candidate generation | Canonical ranking mechanics | Extend authorization and temporal selectors before any Agent Memory use |
| L1 foresight evidence | Reusable evaluation method | Do not present it as Agent Memory evidence |
| I1-I3 measured intelligence | Canonical use-evidence foundation | Preserve observed injection, reflection, decision delta, scope, and lineage requirements |
| Context Manifest candidate | Bridge candidate | Keep retrieved, eligible, selected, injected, and materially used states distinct |
| `ace.core.source` candidate | Bridge candidate | Preserve inert payload, host-owned scope, source version, and multiple time fields |
| Public 11-tool MCP server | Fixed compatibility boundary | No count, name, or semantic break in AM0 |

## 9. Existing-path classification backlog

| Path/capability | AM0 classification | Follow-up owner | Required action |
|---|---|---:|---|
| `core/engine/grounded_state/contracts.py` | Canonical foundation | AM0 | Import or bridge without creating competing time/provenance concepts |
| `core/engine/grounded_state/ingestion_contracts.py` | Canonical foundation | AM0/AM1 | Reuse Core-owned scope and identity rules |
| `core/engine/candidates.py` | Canonical mechanics | AM3/AM4 | Add complete authorization/lifecycle/time enforcement outside ranking |
| Governed cognition revision flow | Canonical foundation | AM2/AM6 | Use for policies and authorized evolution decisions |
| `core/engine/product/intelligence_use.py` | Canonical evidence foundation | AM3/AM6 | Connect context-manifest evidence without loosening material-use gates |
| Documented `ace.context.manifest/v1` candidate | Candidate reference; implementation absent from isolated current main | AM0/AM3 | Keep AM0 linkage reference-only; stabilize runtime composition only after the owning Context Manifest implementation lands independently |
| `ace/core/source.py` | Candidate bridge | AM0/AM1 | Align IDs, scopes, spans, and time with canonical contracts |
| `core/engine/session/models.py` | Experimental compatibility input | AM1 | Replace generated identities/current-time defaults in canonical ingestion |
| `core/engine/capture/schemas.py` | Experimental compatibility input | AM1/AM2 | Map observations/proposals without treating model output as belief |
| `core/engine/capture/pipeline.py` | Experimental compatibility input | AM1/AM2 | Route through canonical admission and reconciliation |
| `core/engine/capture/atomic_write.py` | Adapter pattern only | AM2 | Preserve atomicity/replay pattern behind provider-neutral ports |
| `core/engine/api/documents.py` | Security and ingestion debt | AM1 | Enforce product fence on reads; add exact locators and durable job states |
| `core/engine/capture/provenance.py` | Retirement candidate for authoritative memory | AM2/AM6 | Replace static trust collapse with separate dimensions and governed evidence |
| Freshness/decay/utilization/archive paths | Fragmented compatibility behavior | AM3/AM5 | Unify lifecycle semantics; do not infer truth from age or use count |
| `core/engine/capture/forget.py` | Insufficient for hard erasure | AM4 | Replace with dependency-complete erasure protocol and verification receipt |
| Legacy insight store | Compatibility-only | AM1/AM2 | Do not make it the canonical Agent Memory ledger |

## 10. Implementation slices

### AM0-A — Vocabulary and value contracts

**Outputs**

- Typed identifiers, semantic families, authority and epistemic states.
- Explicit unknown representation and version handling.
- Serialization round-trip fixtures.

**Tests**

- Identifier stability and invalid input.
- Enum/union round trip.
- Unknown required version rejection.
- No implicit promotion from observed/proposed to accepted.

**Failure behavior**

- Invalid or unknown required semantics fail with a typed contract error.
- No fallback maps an unknown state to trusted, active, or accepted.

**Authority change:** none.

### AM0-B — Time, spans, scope, and lifecycle

**Outputs**

- Three-clock selectors.
- Tagged source-span locators.
- Authenticated scope tuple and visibility/retention values.
- Append-only lifecycle event contract.

**Tests**

- Missing time remains unknown.
- World-time queries do not substitute ledger or ingestion time.
- Source-version mismatch invalidates a span.
- Scope supplied inside captured payload is ignored as authority.
- Supersession does not alter historical provenance or trust dimensions.

**Failure behavior**

- Ambiguous selectors and fabricated spans are rejected.
- Missing authorization fails before ranking/traversal.

**Authority change:** none; Core remains the scope authority.

### AM0-C — Ports and transaction semantics

**Outputs**

- Ledger, reconciliation, graph projection, query, and dependency-index protocols.
- Typed receipts and failures.
- A backend conformance-test interface using an in-memory test double only for contract verification.

**Tests**

- Idempotent replay.
- Expected-coordinate conflict.
- Atomic-write failure.
- Indeterminate-outcome recovery.
- Projection rebuild without changing ledger truth.
- Lifecycle filtering before result delivery.

**Failure behavior**

- Storage unavailable, conflict, unauthorized, invalid, and indeterminate are distinct.
- Degraded reads disclose unavailable signals and omissions.

**Authority change:** none; adapters implement mechanics only.

### AM0-D — Existing-capability bridges

**Outputs**

- Mappings to Grounded State evidence and temporal contracts.
- Governed-cognition policy/decision bridge.
- Intelligence-owned Candidate Receipt linkage to exact existing Context Manifest and I3 receipt identities, without a competing use-state contract.
- Compatibility mapping for current session/source/capture inputs.

**Tests**

- Mapping preserves provenance and unknowns.
- Compatibility input cannot self-assign scope or authority.
- Retrieval receipt cannot masquerade as injection or material use.
- Model-produced insight remains a proposal until authorized.

**Failure behavior**

- Lossy mappings fail or explicitly mark unavailable fields; they do not fabricate values.

**Authority change:** none; bridges do not promote maturity.

### AM0-E — Threat model and risk controls

**Outputs**

- Threat cases for cross-product leakage, prompt-supplied scope, poisoned repetition, stale correction, graph traversal leakage, cache leakage, partial deletion, and post-restart derivatives.
- Control-to-test traceability.

**Tests**

- Hostile captured content cannot escape authenticated scope.
- Repetition does not increase epistemic authority.
- Restricted/erased nodes cannot be recovered via edges, embeddings, summaries, caches, or receipts.
- Unknown lifecycle or policy versions fail closed.

**Failure behavior**

- Authorization, lifecycle, or dependency completeness uncertainty fails closed.

**Authority change:** none.

### AM0-F — Architecture and closeout conformance

**Outputs**

- Import-boundary tests.
- Public MCP inventory assertion.
- Architecture documentation and decision-ledger reconciliation.
- Release-state reconciliation record.

**Tests**

- Contract modules import no web framework, SurrealDB driver, concrete record identifier, MCP server, or extension package.
- Kernel starts with extensions disabled.
- Public MCP inventory remains exactly 11 tools.
- All referenced roadmap and evidence artifacts exist.

**Failure behavior**

- Boundary violations block AM0 closeout.
- Conflicting authoritative release metadata is reported, never silently rewritten.

**Authority change:** none.

## 11. Proposed verification locations

Exact filenames may follow the repository's established test layout, but the verification surface must remain visibly grouped:

```text
tests/agent_memory/test_contracts.py
tests/agent_memory/test_temporal_selectors.py
tests/agent_memory/test_source_spans.py
tests/agent_memory/test_scope_authority.py
tests/agent_memory/test_storage_port_conformance.py
tests/agent_memory/test_bridge_mappings.py
tests/agent_memory/test_import_boundary.py
tests/agent_memory/test_unknown_versions.py
tests/agent_memory/test_kernel_startup.py
tests/agent_memory/test_public_mcp_inventory.py
evaluations/fixtures/agent_memory_am0_contract_v1.json
```

The fixture must include ordinary, unknown-time, disputed, superseded, hostile-scope, repeated-poison, cross-product, partial-write, and lifecycle-restricted cases. It is a contract fixture, not a product-quality benchmark.

## 12. Failure contract

| Condition | Required behavior | Forbidden behavior |
|---|---|---|
| Missing world or knowledge time | Preserve explicit unknown | Substitute current/ingestion time |
| Unknown required contract/policy version | Reject safely | Interpret as the latest familiar version |
| Missing authenticated scope | Fail before read/rank/traverse | Trust content-provided scope |
| Index/signal unavailable | Return degraded receipt and omissions | Present partial result as fully evaluated |
| Write timeout with unknown commit state | Return indeterminate outcome and support receipt lookup | Blind retry that may duplicate ledger entries |
| Reconciliation conflict | Preserve both evidence paths and require policy/authority | Overwrite the earlier assertion |
| Supersession | Change applicability through a new event | Lower the old record's historical trust |
| Erasure dependency incomplete | Fail closed and retain erase-pending state | Claim successful hard deletion |
| Retrieved but not injected | Record retrieval only | Count as use or reinforcement |
| Injected but no decision delta | Record injection, no material-use claim | Count as material memory benefit |

## 13. Compatibility and migration posture

AM0 is additive and must require no production database migration. Legacy paths remain callable at their existing maturity level while bridges are introduced. A bridge does not make a legacy store canonical and does not make an experimental path supported.

No public MCP contract changes are permitted. No package-version update is implied by adding AM0 contracts. Any later compatibility removal requires its own deprecation decision, migration evidence, and roadmap reconciliation.

## 14. Bounded Intelligence Builder product trace

AM0 must freeze one synthetic or public-data trace that reflects the public product promise:

```text
install → connect sources → map concepts and ontology → first briefing
→ source update or correction → monitor-triggered refreshed briefing
→ later-session continuity → feedback proposal
```

The trace is contract-level acceptance evidence. It does not authorize implementing an onboarding
agent or any other product component named in the sequence.

The trace passes only when:

1. source admission preserves authenticated product/principal scope, immutable source version, exact or explicitly unavailable coordinates, and independent knowledge/world time;
2. concept/ontology mapping is represented only by exact Intelligence policy/revision references—Agent Memory neither maps nor activates it;
3. the first briefing links authorized memory candidates to an existing Context Manifest item and does not claim I3 material use without an exact intelligence-use receipt;
4. a correction or source update appends lineage, keeps the prior assertion inspectable, and prevents superseded material from being selected as current;
5. a monitor-triggered refresh re-evaluates authorization, lifecycle, correction, preference, and world-time validity rather than reusing stale context silently;
6. a later clean invocation can recover eligible continuity after restart without user-visible memory configuration or private source-body exposure;
7. feedback creates only a governed relevance/evolution proposal and cannot directly change belief, rank policy, source reliability, or retention;
8. a matched no-memory or stale-context control can attribute a briefing difference without claiming correctness or benefit; and
9. cross-product, hostile-scope, unknown-time, stale-cache, and missing-receipt cases fail closed or become explicit degraded states.

This acceptance trace proves only that the AM0 contracts can support repeat briefing updates and
onboarding continuity. It does not prove briefing quality, monitor reliability, onboarding quality,
memory benefit, or production readiness.

## 15. Evidence required for AM0 closeout

AM0 may close only when the work packet can point to:

1. Contract and serialization tests for all canonical vocabulary.
2. Negative tests for unknown time, unknown versions, hostile scope, and unauthorized lifecycle operations.
3. Import-boundary tests proving provider neutrality.
4. Storage-port conformance tests against a deterministic test implementation.
5. Bridge tests proving no loss or fabrication of provenance, scope, time, and use-state.
6. A kernel-startup check with extensions disabled.
7. A public MCP inventory check showing exactly 11 tools.
8. A classified list of legacy paths and their owners in AM1-AM7.
9. Reconciliation across:
   - `ROADMAP.md`;
   - `docs/capability-maturity.md`;
   - architecture documentation;
   - relevant `docs/evidence/` records;
   - operational documentation and issue ledger;
   - package and public-release metadata.
10. A baseline record proving AM0 began from the reconciled public Core 0.6.0 main commit without reopening its claims.
11. The bounded Intelligence Builder product trace with first-briefing, refreshed-briefing, later-session, correction, and feedback-proposal evidence.
12. The AM0 threat model with control-to-test traceability and explicit AM1-AM9 residual work.

AM0 evidence supports only the claim that the contract and boundary foundation is ready. It does not support claims about memory quality, latency, persistence, retrieval benefit, hard erasure, or production readiness.

## 16. Definition of done

AM0 is done when:

- one provider-neutral vocabulary covers identity, provenance, scope, three clocks, lifecycle, semantic family, authority, and epistemic state;
- contracts distinguish recording, retrieval, selection, injection, material use, correction, supersession, and erasure;
- Core ledger/dependency ports and Intelligence reconciliation/query/projection ports have explicit transaction, retry, and failure semantics;
- SurrealDB and legacy implementation types cannot cross the contract import boundary;
- existing ACE capabilities have tested, non-authority-expanding bridges;
- hostile and unknown cases fail safely;
- the 11-tool public MCP inventory is unchanged;
- the AM0 baseline remains bound to the reconciled Core 0.6.0 main commit without altering its release claims;
- the roadmap, audit, risk register, and decision ledger agree on AM1 entry conditions; and
- the bounded product trace shows repeat briefing freshness and later-session continuity without exposing or requiring user-managed memory architecture.

## 17. Stop conditions

Implementation must pause and create a decision record if any slice would:

- introduce a new public tool or top-level bounded context;
- require a database-specific type in a public contract;
- collapse authority, confidence, relevance, freshness, validity, or retention into one score;
- fabricate missing time or source location;
- permit captured content, telemetry, repetition, or retrieval to grant epistemic authority;
- weaken authentication or lifecycle filtering to improve ranking or traversal;
- claim hard erasure without complete derivative enumeration and verification;
- copy a vendor contract or make a vendor runtime a required ACE dependency;
- reopen, weaken, or silently broaden the closed Core 0.6 public-release claim; or
- turn the bounded product trace into an onboarding-agent, connector, ontology-mapping, briefing, monitor, or UI implementation inside AM0.

## 18. AM1 handoff gate

AM1 may begin implementation once AM0-A through AM0-C contracts are stable enough to prevent identity, scope, source-span, and clock semantics from being reinvented in the ingestion layer. AM1 must then implement idempotent session/source ingestion, exact provenance, durable queued/partial/failed/repair states, and cross-product read fencing using these contracts.

AM1 must not wait for AM0-E and AM0-F documentation polish if the executable boundary tests are already active, but AM0 cannot close until every slice is complete.

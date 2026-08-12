# Agent Memory AM1 episodic experience ledger work packet v1

**Status:** isolated publication candidate; implemented and verified, not accepted or merged
**Date:** 2026-08-12
**Depends on:** AM0-A through AM0-C contracts and the reviewed AM0 canonical-source bridge
**Frozen fixture specification:**
[`agent_memory_am1_session_normalization_v1.json`](../../evaluations/fixtures/agent_memory_am1_session_normalization_v1.json)

## 1. Outcome

AM1 makes authorized sessions, turns, tool events, and external events durable as exact episodic
source experience. Two adapters representing the same frozen session must produce the same
canonical identities, order, source coordinates, clocks, and content-free receipts.

AM1 is invisible infrastructure for continuity. It supports later briefing refreshes and later
sessions, but it does not implement an onboarding agent, concept mapper, ontology activation,
briefing generator, monitor scheduler, semantic memory extraction, reconciliation, ranking, or UI.

The active ACE 0.7 stack separately owns Connect and Map/Ontology Agent product artifacts. AM1 may
retain exact approved artifact references as optional session linkage after those contracts land;
it must not copy their proposal bodies into Core contracts, reinterpret their semantics, or become
a second onboarding/session authority.

## 2. Entry gate and branch posture

The control tower authorized one exact, non-rewriting convergence:

- AC7 parent: `c7ff511a80ab3bdd3a13e7ca270567eaf6b3b1bf` on
  `codex/v0.7-composition-policy-admission` (draft PR #116);
- AM0 parent: `48e1aea6ff848be63aab2d49adda1428231ca522` on
  `codex/agent-memory-am0-final-verification` (draft PR #108);
- exact two-parent convergence commit: `a55edc2848c742dc98cfa01f6632bb75d5f31d81` on
  `codex/v0.7-agent-memory-composition-convergence`; and
- AM1 implementation branch: `codex/v0.7-agent-memory-am1`, created from that exact convergence.

PR #108 remains the authoritative review for all 21 AM0-owned paths and claims. Neither source
identity may be rewritten, and the convergence publication must remain a convergence-only draft
that forbids squash. AM1 publication must be an AM1-only draft against the exact convergence ref.

Historical 0.7D through AC7 artifacts are optional lineage only. They are not episodic memory
content, current memory authority, or an ingestion dependency. In particular, composition policy,
participant eligibility, activation, delivery/export, and effect authority remain with their
owning current-head systems.

AM2 is not dispatched by this packet. It remains closed until the control tower accepts the AM1
publication and names the exact integrated AM1 base.

## 3. Architectural boundary

| Owner | AM1 responsibility | Forbidden ownership |
|---|---|---|
| Core | Authenticated memory/session/source scope; deterministic opaque identities; exact or unavailable source coordinates; ledger, knowledge, and world time; append-only ingestion lifecycle; opaque immutable records and receipts | Semantic memory family, belief, ranking, graph meaning, selection, or content-derived authority |
| Intelligence | No required AM1 write-path ownership; may later consume authorized episodic references through AM2 proposals | Session identity, source scope, ingestion authority, or ledger truth |
| Application | Validate an authenticated import request, select one explicitly authorized adapter, normalize, build one atomic append, recover indeterminate outcomes, and project bounded status | Foundational contract invention, model extraction, or product UI |
| Adapter | Parse one exact source format and return inert bounded source events with native coordinates and explicit unavailable fields | Product/principal scope, canonical IDs, current-time defaults, persistence, authority, or silent fallback |
| Existing durable owner | Reuse `ImmutableRecordStore` and `SurrealImmutableRecordStore` for product fences, opaque atomic append, receipt lookup, ordering, and restart replay | A new schema, migration, database, persistence runtime, public semantics, concrete `RecordID` leakage, or adapter-specific identity |

The public dependency direction remains Core → Intelligence → Domain. Meta-Intelligence is only an
internal cross-cutting capability name and owns no AM1 package or port.

## 4. Current-state audit

| Current path | Verified behavior | AM1 disposition |
|---|---|---|
| `ace.core.agent_memory` | Frozen session, participant, turn, scope, provenance, three-clock, and lifecycle values | Canonical AM1 value boundary |
| `ace.core.agent_memory_ports` | Storage-neutral append/read protocols and typed failure semantics | Canonical ledger boundary |
| `ace.core.agent_memory_bridges` | Maps an immutable Core source snapshot to exact/unavailable provenance without payload authority | Canonical source-admission bridge |
| `core/engine/session/models.py` | Mutable dataclasses with source-agnostic names; no exact provenance, authenticated scope, three clocks, or canonical replay identity | Compatibility input only |
| `core/engine/session/adapters/claude_code.py` | Maps event fields but generates random IDs and defaults missing session/time values | Experimental adapter; replace defaults with explicit normalization failure/degradation |
| `core/engine/session/adapters/generic.py` | Silently accepts unknown formats, generates random session/event IDs, defaults missing time to `now`, and returns no turns | Must not enter canonical AM1; unknown formats fail closed or require an explicitly named compatibility adapter |
| `core/engine/session/registry.py` | Global mutable registry silently falls back to `GenericAdapter` | Replace in AM1 composition with explicit adapter identity/version and no fallback |
| `ace.intelligence.contracts.source_acquisition` | Strong governed LIVE source capture and immutable material contracts for domain Intelligence sources | Reuse patterns and Core source snapshots; do not make Intelligence own session ledger identity |
| `ace.testing.immutable_records` | Deterministic atomic in-memory conformance store | AM1 contract test double only; never production truth |

## 4.1 Future 0.7 lineage rules

- Approved 0.7D Watch proposals and inert Brief previews may later be retained as exact source or
  derivation references. They are not canonical memory and must not be interpreted as activated
  Monitors, Subscriptions, Shifts, or canonical Brief resources.
- 0.7E activation plan approval never becomes continuing memory authority. Memory may retain the
  exact resulting `ace.application.domain-activation-commit-reference/v1alpha2` tuple through a
  full-material-digest Core historical-lineage reference, but current activation, rollback, upgrade,
  suspension, and reactivation must be resolved from their owning exact contracts at use time.
- Lifecycle, export, and erasure operations over memory records preserve external activation and
  composition identities as historical lineage unless their owning subsystem separately authorizes
  deletion. Agent Memory cannot erase or rewrite another bounded context's authoritative record.

## 5. Contract additions

AM1 should add the smallest provider-neutral contract set needed for ingestion. Exact names may be
refined during AM1-A, but ownership and meaning are frozen here.

### Core contracts

- `SessionImportIntentV1Alpha1`: authenticated scope reference, explicit adapter identity/version,
  immutable input-source reference/digest, idempotency key, requested time, and bounded limits.
- `EpisodicSourceEventV1Alpha1`: adapter event coordinate, participant/role reference, event kind,
  exact source provenance, three clocks, ordinal, and content digest. Payload/body remains in an
  opaque Core record, not a public receipt.
- `SessionNormalizationReceiptV1Alpha1`: input digest, adapter identity/version, canonical session,
  participant, turn, and event references, omissions/degraded reasons, and receipt digest. No body.
- `SessionIngestionStatusV1Alpha1`: `queued`, `normalizing`, `ready`, `partial`, `failed`, `stale`,
  `retry_pending`, or `repair_required`, with append-only attempt and predecessor references.
- `TranscriptViewReceiptV1Alpha1`: exact authorized scope, bounded returned source/event references,
  omissions/redactions, lifecycle snapshot, and expiry. It contains no transcript body.

### Application protocols

- `SessionSourceAdapter`: normalize one credential-free immutable input under explicit size/event
  bounds; return inert events and native coordinates without canonical scope or identity.
- `SessionAdapterRegistry`: resolve an exact adapter artifact/version or fail; no generic fallback.
- `SessionIngestionService`: validate intent, derive canonical values, append atomically through
  `AgentMemoryLedgerWriter`, and recover indeterminate outcomes through receipt lookup.
- `SessionReadService`: authorize before record lookup and return a bounded transcript view plus a
  content-free receipt. The body channel remains private and separately authorized.

No AM1 contract may import a host, extension, SurrealDB, `RecordID`, MCP server, model provider, or
Domain Pack implementation.

## 6. Identity and ordering freeze

Canonical identity must be derived only from authenticated scope and immutable source material:

```text
session = scope + source identity/version + native session coordinate + derivation version
participant = session + native participant coordinate + normalized role
event = session + source version + native event coordinate + content digest + event kind
turn = session + ordered participant/event references + turn boundary policy version
attempt = import intent + adapter artifact/version + immutable input digest
```

Adapter name alone is not identity. Arrival time, database ID, process ID, UUID generation, and
current wall clock are forbidden identity inputs. Events use one gap-free canonical processing
order after normalization while retaining their original native coordinate and reported time.

Exact replay returns the prior receipt. The same idempotency identity with different immutable
material fails as a divergent replay. Duplicate native coordinates with different material fail;
out-of-order arrival is normalized only when the fixture supplies sufficient stable coordinates.

## 7. Temporal and source rules

- Ledger time is assigned only when Core commits the append.
- Knowledge time represents when ACE first observed the event and may be explicitly unknown.
- World time represents when the event applies outside the ledger and may be explicitly unknown.
- Adapter capture/ingestion time cannot replace either unknown value.
- Text events require UTF-8 byte coordinates against an immutable source version when available.
- Tool events use structured pointers or exact byte/timecode coordinates where the source provides
  them; otherwise AM1 records `UnavailableSourceSpanV1Alpha1` with a reason.
- A source-version mismatch rejects the batch before append.

## 8. Implementation sequence

### AM1-A — Import, event, status, and receipt contracts

**Outputs**

- Frozen Core contracts listed in section 5.
- Strict serialization and unknown-version behavior.
- Deterministic derivation helpers with explicit derivation versions.

**Acceptance**

- Round trips preserve unknown time and exact/unavailable locators.
- Captured payload fields cannot set scope, role authority, visibility, retention, or acceptance.
- Public receipts contain digests/references only, never unrestricted source bodies.

### AM1-B — Normalization application service

**Outputs**

- Explicit adapter resolution with no fallback.
- Deterministic normalization, ordering, and atomic append construction.
- Typed handling of conflict, unauthorized, unavailable, invalid, and indeterminate outcomes.

**Acceptance**

- Exact replay returns the same receipt and creates no new records.
- Divergent replay conflicts before any partial append.
- Missing session/time/location becomes a typed failure or explicit unknown, never a random ID or
  current-time default.

### AM1-C — Two independent fixture adapters

**Outputs**

- One structured event-stream fixture adapter.
- One transcript/export fixture adapter with materially different raw field names and nesting.
- No live connector or product onboarding flow.

**Acceptance**

- Both normalize the frozen fixture to identical session, participant, turn, event, ordering, and
  provenance identity material.
- Adapter-specific fields do not leak into canonical receipts.

### AM1-D — Durable existing-owner integration

**Outputs**

- Existing opaque Core/Surreal transaction owner used directly; no new schema or adapter.
- Atomic append, product/principal fences, receipt lookup, and as-of ordering.
- Queued/normalizing/partial/failed/retry/repair status history.

**Acceptance**

- Exact replay and divergent replay behave identically before and after database/API restart.
- Injected failure leaves no partial canonical batch.
- An indeterminate timeout is resolved by receipt lookup before retry.

### AM1-E — Transcript privacy and authorized views

**Outputs**

- Separate body and metadata paths.
- Bounded view receipt with redaction, omission, lifecycle, and expiry evidence.
- Non-disclosing foreign-product/principal failures.

**Acceptance**

- Public task/status/MCP projections contain no transcript body, prompts, credentials, private tool
  results, or hidden reasoning.
- Unauthorized reads do not disclose whether the session, source, event, or body exists.
- Restricted, expired, erased, and quarantined records are removed before view assembly.

### AM1-F — Restart, repair, and closeout

**Outputs**

- Fresh-process normalization/append/read replay.
- Repair receipt for partial compatibility imports without rewriting committed records.
- Architecture, operations, risk, and evidence reconciliation.

**Acceptance**

- Ordered turns survive database and API restart.
- Interrupted work reaches a truthful terminal or repair-required state.
- Thin public MCP remains exactly eleven tools.

## 9. Failure contract

| Condition | Required behavior | Forbidden behavior |
|---|---|---|
| Unknown adapter or version | Fail before parsing | Fall back to a generic adapter |
| Missing native session coordinate | Typed invalid/degraded result | Generate a UUID |
| Missing source event time | Explicit unknown | Substitute `now` or ingestion time |
| Duplicate exact event | Return prior identity/receipt | Append a second record |
| Same coordinate, different material | Divergent-replay conflict | Last-write-wins overwrite |
| Out-of-order arrival with stable coordinates | Deterministically reorder and receipt the normalization | Preserve accidental arrival order as truth |
| Out-of-order arrival without stable coordinates | Partial/repair-required or reject | Invent order |
| Adapter-supplied product/principal/authority | Ignore as inert payload and use authenticated Core context | Accept it as scope or authority |
| Write timeout with unknown commit state | Return indeterminate and look up the durable receipt | Blindly retry |
| Foreign or unauthorized read | Non-disclosing denial | Reveal identity, count, excerpt, or existence |
| Restricted/expired/erased lifecycle | Filter before body lookup | Fetch then redact after disclosure |

## 10. Frozen fixture matrix

The v1 fixture specification freezes:

- two differently shaped adapter inputs representing the same three-event session;
- explicit authenticated product/principal/source scope outside both inputs;
- stable native session, participant, event, and ordering coordinates;
- one exact UTF-8 byte span and one explicitly unavailable tool-result span;
- distinct knowledge and world-time treatment;
- exact replay, divergent replay, duplicate, out-of-order, missing-time, hostile-scope,
  cross-product, partial-write, indeterminate, restart, lifecycle-restricted, and private-body cases;
- equality requirements across adapters without freezing pre-contract derived IDs prematurely.

AM1-A must replace the fixture's identity-relation assertions with exact expected IDs and digests
once the derivation contract is implemented. That fixture revision must be reviewed before AM1-C
adapter code is accepted.

## 11. Verification locations

```text
ace/core/agent_memory_ingestion.py
ace/application/agent_memory_ingestion.py
core/engine/agent_memory/surreal_ledger.py
core/engine/agent_memory/adapters/event_stream.py
core/engine/agent_memory/adapters/transcript_export.py
tests/agent_memory/am1/test_ingestion_contracts.py
tests/agent_memory/am1/test_normalization_conformance.py
tests/agent_memory/am1/test_replay_and_atomicity.py
tests/agent_memory/am1/test_scope_and_privacy.py
tests/agent_memory/am1/test_restart_and_repair.py
```

Exact runtime paths may follow repository conventions after architecture review. Public contracts
remain under `ace`; concrete SurrealDB and source-format adapters remain under the engine host.

## 12. Evidence and definition of done

AM1 is complete only when:

1. two fixture adapters produce identical canonical identity material;
2. exact and divergent replay, duplicate, out-of-order, partial, indeterminate, and repair behavior
   pass against the in-memory conformance seam and SurrealDB;
3. foreign-product/principal and lifecycle-restricted reads fail before body access without
   existence disclosure;
4. public receipts and all eleven MCP projections remain content-free;
5. fresh database/API processes reproduce the same session, turn order, and receipts;
6. schema-zero and supported-predecessor migration paths pass without changing AM0 identities;
7. all residual limitations and compatibility paths are recorded; and
8. roadmap, capability maturity, architecture, operations, evidence, package, and issue state are
   reconciled without reopening Core 0.6.0.

Passing AM1 proves a bounded episodic ledger and ingestion path. It does not prove semantic memory,
retrieval quality, briefing quality, monitor freshness, memory benefit, or onboarding quality.

## 13. Stop conditions

Pause and create a decision record if AM1 would:

- add or rename a public MCP tool;
- make a raw adapter schema, transcript format, or SurrealDB identifier canonical;
- create `ace.memory`, a Meta-Intelligence package, or a fourth public layer;
- give captured system/tool content instruction authority;
- allow a model to normalize canonical scope, identity, role authority, or time;
- expose unrestricted bodies in receipts, status, logs, or public errors;
- begin semantic assertion extraction or reconciliation from AM2;
- implement an onboarding agent, connector UX, ontology mapping, briefing generation, monitor
  scheduling, or user-facing memory management; or
- stage, commit, push, publish, or mix the work into Core PR #99 without explicit authorization.

## 14. Candidate closeout record

The point-in-time AM1 verification record is
[`agent-memory-am1-candidate-v1.md`](../evidence/agent-memory-am1-candidate-v1.md). It must record
the exact final AM1 commit, changed-path manifest, Core/application/adapter/schema ownership,
database and service restart proof, focused and broad check results, and residual limitations
before publication. Until those fields are complete and accepted, this work packet proves no
production maturity, semantic-memory behavior, retrieval benefit, learning, or release readiness.

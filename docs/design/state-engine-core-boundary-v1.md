# State Engine v0.2 Core boundary

Status: **TP8 boundary decision; applies to the measured ACE 0.1.4 / schema v168 packet**

This document classifies the State Engine surface after TP8. Stability means that a domain-neutral
contract has measured identity, isolation, replay, migration, and recovery evidence. It does not
freeze Python implementation details or promote connector, extraction, ontology, or model policy
into Core.

## Classification

| Component | Classification | Compatibility decision |
|---|---|---|
| Product-scoped evidence identities, temporal meanings, provenance, immutable payloads, idempotency, and supersession | stable Core contract | v1 material-derived IDs and meanings remain readable/replayable across compatible v0.2 migrations |
| Bounded ingestion manifest plus item/batch receipts | stable Core contract | exact replay, terminal disposition, and transaction semantics are stable |
| Evidence query and frozen bounded evidence pack | stable Core contract | trusted product scope, bounds, omissions, degradation, identity, and replay are stable |
| Candidate request/receipt and deterministic multi-signal accounting | stable Core contract | receipt meaning and bounds are stable; ranking weights and physical indexes are internal versioned policy |
| Reviewed epistemic assertion and deterministic as-of belief projection | stable Core contract | evidence binding, status meanings, resolver version, and replay hash are stable |
| Transition proposal, challenge, reviewed revision, and calibration receipt | stable Core contract | mechanism, preconditions, uncertainty, causal limits, review, lineage, and calibration meanings are stable |
| Consequence rollout request/proposal/revision, branch execution, prediction, reconciliation, and reasoning-use receipt | stable Core contract | simulations remain separate from observations/beliefs; frozen inputs, use states, and append-only reconciliation are stable |
| Promotion proposal/review/receipt and memory lineage | stable Core contract | authority, eligibility, disposition, evidence lineage, correction, and supersession meanings are stable |
| Product archive/reactivation and operational receipts | stable Core contract | append-only lifecycle and exact operational receipt identities are stable |
| Source/content adapter proposal interface | supported adapter interface | adapters may supply bounded proposals and external content digests; Core owns scope, identity, validation, receipts, and replay |
| Extension task-action preparation/projection envelope | supported adapter interface | current and N−1 envelopes are supported when they pass Core conformance; extensions never own task or product authority |
| Physical same-database metadata and external content-body adapters | supported adapter interface | inline SurrealKV metadata plus filesystem-digest input were measured; other adapters require their own portability evidence |
| Candidate ranking weights, index layout, bounded preselection query plan, and storage implementation | internal implementation detail | may change without semantic contract break when receipts remain versioned and replay meaning is preserved |
| Deterministic belief/transition/rollout service implementation | internal implementation detail | may change behind exact contracts, policy versions, tests, and migration rules |
| Automated transition discovery, broad domain calibration, and repeated large-corpus task orchestration | experimental Core capability | K2/K3 remain candidate pending the bounded pre-R7 packet |
| Automatic promotion policy beyond the exact allow-list | experimental Core capability | new automatic authority requires a versioned rule, explicit acceptance, and adversarial evidence |
| Connector authentication, crawling, scheduling, retry policy, rate limits, and source availability | extension-owned policy | never imported by Core |
| Extraction prompts/models, source mapping, confidence thresholds, entity-resolution proposals, and cheap relation proposals | extension-owned policy | outputs are untrusted proposals validated at the Core boundary |
| Domain entity types, predicates, mechanisms, causal evidence requirements, and transition templates | domain-owned ontology or extraction behavior | versioned outside Core; Core stores neutral typed material and policy identifiers |
| OLC-specific mappings, corpus identities, slugs, and reference questions | domain-owned ontology or extraction behavior | remain in the reference extension/evaluation layer |
| Raw document lake and large source bodies | extension/external storage concern | Core retains stable identity, content hash, reference, provenance, and bounded selected content, not an unbounded copy |

## Compatibility guarantees

For a supported v0.2 deployment, Core guarantees:

1. Stable v1 records are product-scoped and material-derived; byte-equivalent delivery replays and
   different material at the same stable coordinate conflicts visibly.
2. Event/valid, publication, ingestion, extraction, and ACE creation times remain distinct. Unknown
   time remains unknown.
3. Evidence, reviewed belief, transition hypotheses, simulations, observed outcomes, and promoted
   memory remain different meanings and identities.
4. Append-only revisions, challenges, lifecycle events, corrections, and supersession preserve prior
   material. Migrations do not rewrite accepted semantic history silently.
5. Evidence selection, context injection, reflection, decision-material use, and promotion remain
   separate receipts.
6. Product scope comes from authenticated Core context. Adapter/model/source payload cannot override
   scope, identity, review, mutation, task, tool, or promotion authority.
7. The public thin MCP client remains exactly eleven tools. State Engine functionality is internal
   and extension-first; it does not add a twelfth tool.
8. Current and N−1 extension envelopes are supported only through the declared Core conformance
   contract. Unknown future contracts fail closed or degrade visibly.

Compatibility does not promise byte-identical database queries, physical index names, ranking
scores across a declared policy-version change, internal Python symbols, or unsupported direct table
writes.

## Schema and migration policy

Schema v168 is the TP8 head. New State Engine migrations are additive, schema-full where authority
or lifecycle is involved, append-only for semantic/receipt history, product-indexed, fail-closed,
and idempotent under current-head partial application. Destructive mutation, backfill that changes
meaning, or history rewriting requires a separately reviewed migration and compatibility packet.

Supported paths are schema zero through the head and the documented v0.1.x predecessor through the
head. TP8 also proves current v167→v168 partial-statement recovery. Arbitrary interruption inside
historical pre-v142 migrations is not guaranteed; a deliberate mid-v14 stop failed closed and is a
published negative result. Operators should restore a pre-migration backup for that historical case.

## Adapter contract and portability

An adapter may read a connector, inline content store, or external content-addressed store, but it
only proposes bounded source/entity/alias/claim/event/participant/relation/failure material. It must
preserve source external identity, source version, local coordinate, publisher, content digest,
temporal precision, provenance, and explicit degradation. It may not supply authoritative product
scope or Core record IDs.

Core validates every proposal, derives stable identity and idempotency, persists the item in a real
transaction, records exact terminal receipts, and owns replay. External content must be digest-
verified before proposal creation. The measured filesystem adapter is read-only input portability;
Core receipts, semantic identity, lifecycle, and replay remain in SurrealKV. A new physical adapter
is supported only after it reproduces identical Core IDs, isolation, query, lifecycle, and replay
semantics.

## Deployment and operational guarantees

The supported measured topology is one ACE API/worker deployment and one SurrealDB/SurrealKV
database, with bounded synchronous ingestion clients. Multiple fresh clients may replay manifests,
but TP8 does not establish distributed ordering, consensus, exactly-once delivery across independent
databases, multi-region failover, or multi-writer throughput.

The frozen reference limits are 200 records/item, 200 items/manifest, 200 candidate records, 50
returned candidates, 20 evidence-pack records, 8 runtime evidence records, 2,400 runtime context
characters, 8 rollout branches/steps/transitions, and 20 promotion retrieval results. The measured
single-node corpus is 200,000 claims/236,000 initial semantic records with an initial 2 GiB storage
budget. Operators must rebenchmark materially larger corpora, different hardware, concurrency,
indexes, or adapters.

Bulk ingestion has no per-claim primary-model synthesis requirement. Provider-backed task reasoning
remains governed by the ordinary ACE provider and task budgets; TP8 exercised only explicit
provider-free paths and makes no hosted latency or cost promise.

## Known negative results and deferred work

- Preliminary unbounded preflight scans and an unindexed candidate query failed scale thresholds;
  bounded direct preloads and compound indexes replaced them. The raw failures remain published.
- Arbitrary historical pre-v142 mid-file migration recovery is unsupported.
- K2 needs a repeated large-corpus frozen-domain transition/calibration matrix.
- K3 needs repeated fresh API/worker/client large-corpus task, promotion, restart, and later-retrieval
  latency evidence.
- Distributed ingestion, multi-writer consistency, remote object-storage adapters, automatic broad
  causal discovery, online autonomous learning, real-world forecast calibration, beneficial impact,
  and production deployment hardening are deferred beyond this packet.

No claim is made of general world-model intelligence, causal truth, calibrated forecasting,
autonomous improvement, or decision benefit.

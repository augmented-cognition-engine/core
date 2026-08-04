# ACE State Engine TP1A truthful observation outcomes v1

Status: **implemented and verified as TP1A; the remaining TP1 work was subsequently completed**

Current TP1 closeout: [reliable memory lifecycle v1](state-engine-tp1-reliable-memory-lifecycle-v1.md).
The evidence and totals below remain the point-in-time TP1A record.

This record describes the ordinary observation-processing lifecycle introduced by TP1A. It closes
the failure mode in which a synthesizer invocation could be followed by `status = 'processed'`
without durable evidence of what happened. It does not establish the full TP1 worker lifecycle, any
TP2 grounded-evidence capability, or K1/K2/K3.

## Authoritative flow

```text
capture
  -> pending observation
  -> processing attempt
  -> synthesizer outcome
  -> durable receipt
  -> explainable terminal state or retry
```

The immutable, extra-forbid contract is `ace.capture.synthesis-outcome/v1`. Processing state and
business disposition are separate:

| Processing state | Meaning | Compatibility status |
|---|---|---|
| `pending` | Persisted and eligible for an initial attempt | `pending` |
| `processing` | One numbered attempt has started | `pending` |
| `succeeded` | A durable receipt names one evidenced successful disposition | `processed` |
| `retryable_failed` | A bounded failure receipt exists and `next_retry_at` is set | `pending` |
| `dead_letter` | The third failed attempt exhausted the TP1A retry budget | `failed` |

A `succeeded` receipt has exactly one of these dispositions:

- `insight_created`, with one or more durable created-insight references;
- `insight_updated`, with one or more durable updated-insight references;
- `insight_merged`, with one or more durable merged-insight references;
- `conflict_preserved`, with both conflicting-insight and durable conflict-record references; or
- `skipped`, with a required bounded reason.

A failure receipt has no successful disposition. It contains a bounded category, stable code, error
type, and at most 500 characters of normalized message text; it never stores a traceback or provider
payload. A compatibility `processed` marker is written only after the receipt is durable. Receipt or
finalization failure restores the prior attempt coordinate and pending state when the database is
available, allowing the same deterministic attempt to be resumed.

## Persistence and identity

Migration `v161_synthesis_outcome_receipt.surql` adds the SCHEMAFULL
`synthesis_outcome_receipt` table, observation lifecycle fields and indexes, and the merge-attempt
marker used to make confidence boosts replay-safe. It does not alter or backfill historical rows.
Receipt update and delete permissions are `NONE`.

All identities are deterministic over canonical, key-sorted JSON and truncated to the first 32
hexadecimal characters of SHA-256 where a record key is needed:

```text
attempt_id = synthesis_attempt:sha256({
  product_id, observation_id, attempt_count, route,
  processor_version, policy_version, schema_version
})[:32]

receipt_id = synthesis_outcome_receipt:sha256({product_id, attempt_id})[:32]

new_insight_id = insight:sha256({
  product_id, attempt_id, content_hash, ordinal
})[:32]

conflict_id = conflict:sha256({
  product_id, attempt_id, insight_id, ordinal
})[:32]
```

The material hash covers product and observation identity plus synthesis-relevant content, type,
confidence, domain/discipline hints, source, and source-memory identity. Mutable queue bookkeeping
is excluded. Exact replay of a completed attempt returns the existing receipt and deterministic
insight/conflict records. Changed material at the same attempt coordinate fails closed; history is
not overwritten. Embedding-dedupe confidence boosts record the attempt identity and cannot apply
twice.

Receipt creation validates that the observation and every insight or conflict reference belong to
the receipt product. Observation reads, queue claims, updates, retries, finalization, receipt reads,
health counts, synthesizer lookups, insight updates, conflict writes, deduplication, and embedding
updates all include product scope.

## Current entry points

The single finalization owner is
`core.engine.capture.lifecycle.process_observation_attempt`. Current ordinary paths reach it as
follows:

| Entry path | Route behavior |
|---|---|
| Thin public `ace_capture` | Calls `POST /observations`; the API persists pending, then runs `api_inline` |
| Broad/internal MCP `ace_capture` | Persists pending, then runs `mcp_inline` |
| Document ingestion | Persists each extracted observation, then runs `document_ingestion` |
| `CapturePipeline` | Persists first, then runs `capture_pipeline`; its no-database compatibility mode cannot claim durable success |
| `CaptureService` | Persists first, then runs `capture_service`; its no-database compatibility mode cannot claim durable success |
| Worker hook `POST /observe` and file watcher | Persist pending; live and poll drains run `worker_live` or `worker_poll` |
| Worker session-end synthesis | Persists summary, decisions, and learnings as pending work for the worker lifecycle |

Other current producers—chat remember/session capture, task and initiative events, agent-lifecycle
events, reasoning conclusions, composition/failure classification, review learning/capture, product
feedback, project/session-memory imports, and the PM optimizer—now write a product-owned explicit
`pending` state. They do not invent terminal status; the worker is their route to the shared
lifecycle.

The direct research-agent duplicate synthesis call was removed because its capture call already
owns synthesis. Correction, intervention, and foresight observation types retain their separate
versioned lifecycle contracts and are not reclassified as ordinary synthesis. Health excludes such
processed rows from `legacy_unexplained` only when the corresponding specialized contract version is
present.

## Legacy treatment

No historical receipt is fabricated. A product-owned ordinary observation with
`status = 'processed'` and no outcome receipt is counted as `legacy_unexplained`. ACE does not infer
whether that row created, updated, merged, conflicted, skipped, or failed. Historical remediation is
future TP1 work and must preserve this uncertainty.

## Health semantics

Product-scoped outcome health is additive on the existing API `/health` and `/health/ops`, worker
`/health/status`, broad/internal `ace_health`, and thin `ace_start` responses. No MCP tool was added;
the supported public surface remains exactly eleven tools.

The bounded projection reports pending count, oldest pending age, processing count, successful
counts by all five dispositions, retryable failures, dead letters, legacy unexplained rows, and the
last successful outcome time. The declared TP1A policy is:

- maximum healthy pending age: 900 seconds;
- maximum retryable failures: 0;
- maximum dead letters: 0; and
- maximum legacy unexplained rows: 0.

Exceeding any threshold makes outcome health `degraded`, and that degradation overrides recent
hook/worker activity on the combined surfaces. A fresh bounded queue may remain healthy. Processing
age, lease expiry, and supervisor liveness are not claimed by TP1A.

## Verification

Verification on 2026-08-03 used source revision
`6b6342f65224ca0c3db2f38c3bc141a58de9e8ea`, CPython 3.12.13, and no paid model calls:

- Ruff over every changed Python implementation and test path: passed;
- focused receipt, health, capture, worker, MCP, migration, schema, API, review, and producer
  compatibility lane: 151 passed and 12 database-unavailable skips;
- the receipt/lifecycle acceptance file against a disposable real SurrealKV database after applying
  all migrations through v161: 17 passed;
- a separate disposable SurrealKV stop/start check: 1 passed, proving the receipt and its
  observation/insight references survived restart and remained unreadable from another product;
- schema migration lint, safety, and idempotency are included in the focused lane, while fresh
  migration application reached schema v161 successfully; and
- thin MCP registration and package-boundary checks are included in the focused lane and retained
  exactly 11 public tools; and
- the complete extension-disabled, non-E2E compatibility suite: 6,729 passed, 47 skipped, and 245
  deselected, with zero failures.

The disposable databases were local, contained only synthetic test records, and were removed after
verification. No live graph, customer data, provider call, historical backfill, commit, push, or
publication was used.

## Remaining TP1 work

TP1A establishes truthful outcomes, not the complete TP1 operating model. TP1 still requires:

- product-scoped leases with atomic concurrent claiming, owner identity, expiry, and recovery;
- a continuous bounded drain loop rather than one-batch reconnect behavior;
- explicit recovery policy for attempts stranded in `processing` by process death;
- supported worker startup, shutdown, restart, and supervision guidance;
- throughput and processing-age policy tied to those lease/supervision guarantees; and
- an explicit, non-fabricating remediation policy for historical `legacy_unexplained` rows.

TP0 is not rewritten by this work. The frozen corpus and its zero baseline remain unchanged. TP2
grounded evidence persistence, belief resolution, dynamics, rollouts, and bulk knowledge ingestion
remain out of scope; K1, K2, and K3 remain `not ready`.

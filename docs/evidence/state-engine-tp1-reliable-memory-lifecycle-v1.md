# ACE State Engine TP1 reliable memory lifecycle v1

Status: **implemented and verified; T1 and K1–K3 remain not ready**

This record closes TP1's memory-plane lifecycle packet. TP1A already made every ordinary synthesis
attempt truthful through immutable outcome receipts. TP1B adds exclusive work ownership, crash
recovery, continuous draining, queue-aware health, and a supervised worker operating path. It does
not implement the TP2 grounded-evidence plane, distributed task execution, or any dynamics or
consequence capability.

## Authoritative worker flow

```text
pending observation
  -> atomic product-scoped claim
  -> processing lease + numbered attempt
  -> heartbeat while synthesis runs
  -> durable TP1A outcome receipt
  -> succeeded | retryable_failed | dead_letter

process death
  -> lease expiry
  -> replacement claim with a higher generation
  -> resume the same attempt coordinate
```

`ace.capture.observation-lease/v1` is an immutable, extra-forbid contract. A lease names exactly one
product, observation, owner, generation, acquisition, heartbeat, and expiry and records whether it
recovered a prior processing attempt. Migration `v162_observation_processing_leases.surql` adds
optional lease fields and claim/owner indexes to `observation`; legacy and pending rows remain
compatible.

The candidate read and conditional update execute in one SurrealDB transaction. Each invocation
claims at most one row, so a client never holds an un-heartbeated batch while an earlier model call
runs. Serializable transaction conflicts from simultaneous workers are retried five times with a
bounded yield; after the winner commits, losers reselect and return no claim. Product, current lease
ID, owner, and unexpired time fence every renewal, lifecycle update, and finalization.

The defaults are a 120-second lease and a 30-second heartbeat. A legacy row stranded in `processing`
without lease metadata becomes recoverable after 300 seconds. Recovery preserves the numbered
attempt: a crash does not consume a retry, and a receipt written before a crash is replayed rather
than synthesizing the same material again. A replaced owner cannot renew, restore, or finalize the
row. Deterministic TP1A attempt identities keep insight, conflict, and receipt effects replay-safe.

## Continuous delivery and product scope

SurrealDB LIVE SELECT is now a low-latency wake-up only. The independent fallback loop runs for the
worker lifetime even when LIVE is unavailable. Each pass drains at most four ten-attempt cycles,
claims one observation at a time, yields between full cycles, and sleeps one second only when no
ready work was found. Startup and reconnect also wake the same leased poll path.

The claimed observation's product identity controls synthesis, deduplication, embedding, signal
extraction, receipt persistence, and finalization. LIVE events from another product are ignored.
Foreign-product claims return no record; forged owners and stale leases fail closed.

## Health semantics

The existing API, worker, broad MCP, and thin eleven-tool surfaces remain additive. Product-scoped
database health now reports:

- total queue depth, ready pending count, and oldest pending age;
- processing count, oldest processing age, and expired/orphaned lease count;
- successful outcomes in the latest five minutes and the derived per-minute rate;
- each successful disposition, retries, dead letters, legacy unexplained rows, and last success; and
- in-process claims, recoveries, lost fences, leased outcomes, and bounded-drain activity.

A database result is healthy only when pending age is at most 900 seconds, processing age is at most
300 seconds, and no expired lease, retryable failure, dead letter, or unexplained legacy row breaches
policy. Missing queue visibility is degraded rather than green. Recent hook traffic cannot override
either a queue-policy breach or unavailable lifecycle visibility.

No historical outcome is fabricated. An ordinary legacy observation already marked `processed`
without a TP1A receipt remains `legacy_unexplained`. Operators are instructed to preserve that gap,
not delete leases or synthesize a receipt by inference.

## Supervision

`infra/docker-compose.yml` now contains `ace-worker`. It waits for a healthy SurrealDB and successful
migration, exposes only a loopback host port, has a process-liveness probe, and uses
`restart: unless-stopped`. Worker shutdown cancels LIVE, drain, and filesystem-watcher tasks before
closing the database pool. The foreground launcher accepts `ACE_WORKER_HOST` and `ACE_WORKER_PORT`;
worker owner identity is generated per process unless an operator supplies a unique
`ACE_WORKER_INSTANCE_ID`.

The durable operating and recovery procedure is in
[`docs/worker-operations.md`](../worker-operations.md). Compose structure was validated locally; no
container image was published and no deployment was mutated by this packet.

## Acceptance matrix

| Requirement | Evidence |
|---|---|
| One owner under concurrency | Eight real concurrent claims produce exactly one lease; serializable conflicts retry without duplicate ownership |
| Product isolation | Foreign-product claim returns none; forged owner renewal and stale generation renewal raise `ObservationLeaseLost` |
| Live owner remains exclusive | A 50 ms heartbeat protects a 200 ms lease during a 350 ms synthetic processing call |
| Crash recovery | An expired generation is replaced, the stale owner cannot renew, and the replacement finalizes attempt 1 without incrementing it |
| Restart continuity | Disposable SurrealKV is stopped twice: the expired attempt is recovered after the first restart and its terminal receipt remains identical after the second |
| Continuous bounded drain | Unit acceptance proves repeated full batches are capped and the fallback schedules another cycle after idle without LIVE |
| Graceful lifecycle | Worker lifespan acceptance proves LIVE, drain, and watcher tasks all start, receive cancellation, and precede pool close |
| Queue-aware green status | Real health acceptance degrades expired/old processing and reports recent throughput; mocked unavailable visibility also degrades |
| Supervision | Compose parse/config validation and configuration sentinels prove migration dependency, liveness, loopback mapping, and restart policy |
| TP1A compatibility | Real TP1A disposition/receipt tests pass against the same v162 database and all restart lanes remain green |

## Verification

Verification on 2026-08-03 used source revision
`6b6342f65224ca0c3db2f38c3bc141a58de9e8ea`, CPython 3.12.13, SurrealDB 3.2.1, and no model-provider
calls:

- Ruff lint over Core, thin client, and tests: passed; format checks over every TP1B-touched Python
  path: passed; `git diff --check`: passed;
- Docker Compose configuration parse and the worker supervision contract test: passed;
- TP1A plus TP1B real-database acceptance against a disposable v162 namespace: 23 passed;
- disposable TP1A receipt, TP1B two-restart recovery, and schema-zero-to-v162 API restart lane:
  3 passed;
- complete extension-disabled, non-E2E compatibility suite: 6,740 passed, 47 skipped, and 246
  deselected in 526.74 seconds; and
- explicit kernel-boundary sentinel: 4 passed.

The full suite reported 28 warnings from existing deprecation, collection, short-test-key, and
unawaited-test-mock paths; it had zero failures. Disposable databases contained only synthetic
records and were stopped and removed after verification. No live graph, customer data, provider
call, historical backfill, commit, push, publication, or hosted-service change was used.

## Boundaries after TP1

TP1 makes the ordinary cognitive-memory observation lifecycle reliable within its declared
database lease model. It does not make arbitrary external provider calls exactly once: after a hard
crash, a model request whose response was never durably recorded may be issued again. It supports
one configured product per worker process; multiple products require distinct worker instances.
The Compose path is local supervision, not evidence of Kubernetes, multi-region, partition-tolerant,
or managed-service operations.

T1 remains `not ready` because durable task cancellation, portable execution state, resource
reporting, and explicit distributed-task guarantees exceed this observation worker. TP0's frozen
corpus is unchanged. TP2 evidence ingestion, belief-state resolution, transition hypotheses, and
consequence rollouts remain unimplemented, so K1, K2, and K3 remain `not ready`.

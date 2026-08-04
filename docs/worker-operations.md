# Reliable observation worker operations

ACE's observation worker turns pending cognitive-memory observations into durable synthesis outcome
receipts. The supported supervised deployment is the `ace-worker` service in
`infra/docker-compose.yml`. The worker uses product-scoped, expiring database leases; SurrealDB
LIVE SELECT reduces latency but is not required for delivery.

## Start and inspect

From a source checkout with `.env` configured:

```bash
docker compose -f infra/docker-compose.yml up -d surrealdb migrate ace-api ace-worker
docker compose -f infra/docker-compose.yml ps ace-worker
curl -fsS http://127.0.0.1:${ACE_WORKER_HOST_PORT:-37778}/health/status
docker compose -f infra/docker-compose.yml logs --tail 100 ace-worker
```

Compose waits for a healthy database and a successful schema migration before starting the worker,
checks process liveness on `/health`, and restarts a failed worker with `restart: unless-stopped`.
The host port binds to loopback. `ACE_PRODUCT_ID` selects the one product drained by that worker and
defaults to `product:platform`.

For a development-only foreground process, run:

```bash
uv run python core/engine/worker/start.py
```

`ACE_WORKER_HOST` and `ACE_WORKER_PORT` override its bind address and port. Each concurrent worker
must have a distinct `ACE_WORKER_INSTANCE_ID`; when unset, ACE generates a process-and-UUID owner.
The database claim is authoritative, so LIVE events and multiple workers may race without sharing
one lease simultaneously.

## Shutdown and restart

Use Compose so the process receives a graceful termination signal:

```bash
docker compose -f infra/docker-compose.yml stop ace-worker
docker compose -f infra/docker-compose.yml start ace-worker
# or
docker compose -f infra/docker-compose.yml restart ace-worker
```

Shutdown cancels the LIVE subscription, continuous drain, and filesystem watcher before closing the
database pool. The worker claims only one observation at a time, so no client-side batch remains
hidden during shutdown. If the process dies during synthesis, its lease expires after at most the
default 120 seconds; a replacement worker recovers the same attempt coordinate and does not consume
an extra retry merely because the process died. An older owner cannot renew or finalize after a new
lease generation wins.

Pending rows written while the worker is stopped remain durable. On startup the independent bounded
drain runs continuously, including when LIVE SELECT is unavailable. Legacy rows already marked
`processing` without lease metadata become recoverable after 300 seconds. Existing processed rows
without a truthful outcome receipt are never backfilled by inference; they remain visible as
`legacy_unexplained`.

## Health and recovery

`GET /health/status` combines in-process worker activity with product-scoped database truth. The
observation projection includes:

- queue depth and oldest pending age;
- current processing count and oldest processing age;
- expired or orphaned processing leases;
- successful outcomes in the last five minutes and their per-minute rate;
- retryable failures, exhausted dead letters, legacy unexplained rows, and last success; and
- lease claims, recovered leases, lost fences, completed leased outcomes, and drain activity for
  the current process.

A green observation result requires queue lag at or below 900 seconds, processing age at or below
300 seconds, no expired lease awaiting recovery, and no retryable, dead-letter, or unexplained
legacy breach. Recent hook traffic alone cannot override a degraded database lifecycle.

If health reports `expired_processing_lease`, keep the supervised worker running and confirm that
the count clears on the next drain. Repeated `lease_loss_count` growth usually means duplicate owner
IDs, severe event-loop/model latency beyond the heartbeat, or database connectivity loss. Inspect
worker logs and database readiness before manually changing any queue row. Do not delete or rewrite
a lease or fabricate a receipt as recovery.

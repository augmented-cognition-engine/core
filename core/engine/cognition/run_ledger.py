"""Run-level persistence for reasoning passes (the dual-ledger).

create_run()    — write the Task Ledger when a reasoning pass starts.
finalize_run()  — write the Progress Ledger (phases + executor trace) at the end.
get_recent_runs() — read recent runs for a product (cross-session learning source).

Every function is fail-safe: a DB error returns None / [] and never raises, so
persistence can never block or alter reasoning output. Mirrors the resilience
contract of MultiPhaseExecutor._capture_phase_output.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.engine.core.otel import current_trace_id

logger = logging.getLogger(__name__)

# Hard ceiling on any single run_ledger DB op. The pool bounds connection *acquisition* (5s) and
# *health-check* (2s), but the query itself was unbounded — a socket that's alive but never answers
# would block the reasoning hot path forever (cf. the "CLI hangs under sustained DB load" note). A
# wait_for cancels a hung query; the pool's connection() release() then health-checks and discards
# the (possibly poisoned) connection, so cancellation is safe and self-healing.
# Set to 2.0 to match the pool's own release health-check budget: a fully-hung socket costs
# timeout + 2.0s (the release health-check hangs on the same poisoned socket before recycling), so
# 2.0 keeps a create_run + finalize_run pair under ~8s worst case while staying >> a healthy query.
_DB_TIMEOUT_S = 2.0


async def _query(pool, sql: str, params: dict, *, timeout: float | None = None):
    """Run one query under a hard timeout. On timeout, asyncio.wait_for raises TimeoutError (an
    Exception subclass in 3.11+), which each caller's existing `except Exception` catches → fail-safe
    degrade (None / [] / no-op). Zero overhead on the healthy path (query completes well under the
    ceiling). Cancellation of a hung query is absorbed by the pool's release-time health check. The
    timeout is resolved at call time (not bound as a default) so it honors monkeypatching/config."""

    async def _run():
        async with pool.connection() as db:
            return await db.query(sql, params)

    return await asyncio.wait_for(_run(), timeout=_DB_TIMEOUT_S if timeout is None else timeout)


async def create_run(
    *,
    product_id: str,
    thought: str,
    meta_skills: list[str],
    depth: int,
    discipline: str | None,
) -> str | None:
    """Write the Task Ledger; return the new reasoning_run record id (or None)."""
    from core.engine.core.db import parse_one, pool

    try:
        result = await _query(
            pool,
            """
            CREATE reasoning_run SET
                product = <record>$product,
                thought = $thought,
                meta_skills = $meta_skills,
                depth = $depth,
                discipline = $discipline,
                trace_id = $trace_id,
                status = 'running',
                started_at = time::now()
            """,
            {
                "product": product_id,
                "thought": thought[:2000],
                "meta_skills": meta_skills,
                "depth": depth,
                "discipline": discipline,
                "trace_id": current_trace_id(),
            },
        )
        row = parse_one(result)
        if not isinstance(row, dict):
            logger.debug("create_run: unexpected DB response shape: %r", row)
            return None
        run_id = row.get("id")
        run_id = str(run_id) if run_id else None
    except Exception as exc:
        logger.debug("create_run failed (non-fatal): %s", exc)
        return None
    # Append-only log: emit the opening event (seq 0). Best-effort — never affects the run row above.
    await append_event(
        run_id,
        "run_started",
        {"thought": thought[:2000], "depth": depth, "discipline": discipline, "meta_skills": meta_skills},
        seq=0,
    )
    return run_id


async def finalize_run(
    *,
    run_id: str | None,
    conclusion: str,
    phases: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    status: str = "complete",
) -> None:
    """Write the Progress Ledger onto an existing run. No-op if run_id is None."""
    if not run_id:
        return
    from core.engine.core.db import pool

    wrote = False
    try:
        await _query(
            pool,
            """
            UPDATE <record>$run_id SET
                conclusion = $conclusion,
                phases = $phases,
                trace = $trace,
                status = $status,
                ended_at = time::now()
            """,
            {
                "run_id": run_id,
                "conclusion": (conclusion or "")[:8000],
                "phases": phases,
                "trace": trace,
                "status": status,
            },
        )
        wrote = True
    except Exception as exc:
        logger.debug("finalize_run failed (non-fatal): %s", exc)
    if not wrote:
        # The primary run-row write failed or timed out — under a DB hang every subsequent query
        # would hang too, multiplying the hot-path block by (1 + n_phases). Skip the best-effort
        # event mirror; the run row is the source of truth and the events are reconstructable.
        return
    # Append-only log: one immutable event per phase, then a terminal event. Emitted AFTER the run-row
    # UPDATE above and each is fail-safe. Break on the first failed write (append_event returns None)
    # so a mid-sequence DB hang can't multiply the block across every remaining event.
    # NOTE: this also skips the terminal run_complete/run_failed event on a transient phase-event
    # failure. Safe today — no reader scans for terminal events (the reasoning_event log is write-only
    # until forkable foresight / the trace UI land). TODO(reader-lands): when a reader depends on the
    # terminal marker to know a run finished, still attempt the terminal event after a phase failure.
    seq = 0
    for ph in phases or []:
        seq += 1
        if await append_event(run_id, "phase", ph if isinstance(ph, dict) else {"value": ph}, seq=seq) is None:
            return
    seq += 1
    terminal = "run_complete" if status == "complete" else "run_failed"
    await append_event(
        run_id,
        terminal,
        {"conclusion": (conclusion or "")[:2000], "n_phases": len(phases or []), "status": status},
        seq=seq,
    )


async def append_event(
    run_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    seq: int,
    pool=None,
) -> str | None:
    """Append one immutable reasoning_event (the append-only log). Fail-safe: returns None on any
    error, never raises — event persistence must never block or alter reasoning. `run` is bound as a
    RecordID (not a <record>$x cast — the v3 trap). Callers supply a per-run monotonic `seq`."""
    if not run_id:
        return None
    from core.engine.core.db import parse_one, parse_record_id
    from core.engine.core.db import pool as default_pool

    pool = pool or default_pool
    try:
        result = await _query(
            pool,
            """
            CREATE reasoning_event SET
                run = $run, seq = $seq, event_type = $event_type,
                payload = $payload, created_at = time::now()
            """,
            {"run": parse_record_id(run_id), "seq": seq, "event_type": event_type, "payload": payload or {}},
        )
        row = parse_one(result)
        return str(row["id"]) if isinstance(row, dict) and row.get("id") else None
    except Exception as exc:
        logger.debug("append_event failed (non-fatal): %s", exc)
        return None


async def get_run_events(run_id: str, *, pool=None) -> list[dict[str, Any]]:
    """Read a run's events, oldest first (replay/inspection). seq + run are in the SELECT so the
    v3 'ORDER BY field must be selected' rule is satisfied. Returns [] on any failure."""
    from core.engine.core.db import parse_record_id, parse_rows
    from core.engine.core.db import pool as default_pool

    pool = pool or default_pool
    try:
        result = await _query(
            pool,
            "SELECT seq, event_type, payload, created_at, run FROM reasoning_event WHERE run = $run ORDER BY seq ASC",
            {"run": parse_record_id(run_id)},
        )
        return parse_rows(result)
    except Exception as exc:
        logger.debug("get_run_events failed (non-fatal): %s", exc)
        return []


async def get_recent_runs(*, product_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent reasoning runs for a product (newest first).

    The cross-session learning source: instrument tuning and frontier-scan
    benchmarking read from here. Returns [] on any failure.
    """
    from core.engine.core.db import parse_rows, pool

    try:
        result = await _query(
            pool,
            """
            SELECT * FROM reasoning_run
            WHERE product = <record>$product
            ORDER BY started_at DESC
            LIMIT $lim
            """,
            {"product": product_id, "lim": limit},
        )
        return parse_rows(result)
    except Exception as exc:
        logger.debug("get_recent_runs failed (non-fatal): %s", exc)
        return []

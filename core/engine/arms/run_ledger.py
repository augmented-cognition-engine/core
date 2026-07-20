"""The arm run ledger — a build is durable before it does any work.

create_run()    — the Task Ledger, written at dispatch (BEFORE plan/execute).
checkpoint()    — the Progress Ledger: one immutable, seq-ordered event per completed phase.
finalize_run()  — the terminal state (verified | failed | parked) + how many attempts it took.
get_runs_needing_attention() — the single read for what is waiting on a human (parked + interrupted).

Every function is fail-safe: a DB error returns None / [] and NEVER raises. Bookkeeping
must not be able to break the build — the same contract as cognition/run_ledger.py, whose
shape this deliberately mirrors (that one ledgers reasoning; this one ledgers building).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.engine.core.otel import current_trace_id

logger = logging.getLogger(__name__)

# Hard ceiling on any single ledger DB op — a socket that is alive but never answers must not
# block the build loop forever. Matches cognition/run_ledger._DB_TIMEOUT_S; see the note there
# on why 2.0s is the right budget against the pool's release-time health check.
_DB_TIMEOUT_S = 2.0


async def _query(pool, sql: str, params: dict):
    """Run one query under a hard timeout. On timeout asyncio.wait_for raises TimeoutError
    (an Exception subclass on 3.11+), which each caller's `except Exception` absorbs into the
    fail-safe degrade path. Cancelling a hung query is safe: the pool health-checks and
    discards the (possibly poisoned) connection on release."""

    async def _run():
        async with pool.connection() as db:
            return await db.query(sql, params)

    return await asyncio.wait_for(_run(), timeout=_DB_TIMEOUT_S)


async def create_run(
    *,
    product_id: str,
    intent: str,
    arm_domain: str,
    spec_id: str | None = None,
    pool=None,
) -> str | None:
    """Write the Task Ledger; return the new arm_run id (None if the DB is unavailable).

    Called BEFORE plan() — that is the whole point. A run that dies during execute leaves a
    'running' row behind, which is what makes an interrupted build visible at all.
    """
    from core.engine.core.db import parse_one, parse_record_id
    from core.engine.core.db import pool as default_pool

    pool = pool or default_pool
    try:
        result = await _query(
            pool,
            """
            CREATE arm_run SET
                product = $product,
                spec = $spec,
                intent = $intent,
                arm_domain = $arm_domain,
                trace_id = $trace_id,
                attempts = 0,
                status = 'running',
                started_at = time::now()
            """,
            {
                "product": parse_record_id(product_id),
                "spec": parse_record_id(spec_id) if spec_id else None,
                "intent": (intent or "")[:2000],
                "arm_domain": arm_domain,
                "trace_id": current_trace_id(),
            },
        )
        row = parse_one(result)
        if not isinstance(row, dict) or not row.get("id"):
            logger.debug("create_run: unexpected DB response shape: %r", row)
            return None
        return str(row["id"])
    except Exception as exc:
        logger.debug("arm create_run failed (non-fatal): %s", exc)
        return None


async def checkpoint(
    run_id: str | None,
    phase: str,
    payload: dict[str, Any] | None = None,
    *,
    seq: int,
    pool=None,
) -> str | None:
    """Append one immutable arm_run_event. No-op (None) without a run_id — the DB was down at
    create and the build carries on regardless. `run` is bound as a RecordID, not a
    <record>$x cast (the v3 trap)."""
    if not run_id:
        return None
    from core.engine.core.db import parse_one, parse_record_id
    from core.engine.core.db import pool as default_pool

    pool = pool or default_pool
    try:
        result = await _query(
            pool,
            """
            CREATE arm_run_event SET
                run = $run, seq = $seq, phase = $phase,
                payload = $payload, created_at = time::now()
            """,
            {"run": parse_record_id(run_id), "seq": seq, "phase": phase, "payload": payload or {}},
        )
        row = parse_one(result)
        return str(row["id"]) if isinstance(row, dict) and row.get("id") else None
    except Exception as exc:
        logger.debug("arm checkpoint failed (non-fatal): %s", exc)
        return None


async def finalize_run(
    *,
    run_id: str | None,
    status: str,
    reason: str = "",
    attempts: int = 1,
    diagnosis: str = "",
    pool=None,
) -> None:
    """Close the run: verified | failed | parked. No-op without a run_id."""
    if not run_id:
        return None
    from core.engine.core.db import parse_record_id
    from core.engine.core.db import pool as default_pool

    pool = pool or default_pool
    try:
        await _query(
            pool,
            """
            UPDATE $run SET
                status = $status,
                reason = $reason,
                diagnosis = $diagnosis,
                attempts = $attempts,
                ended_at = time::now()
            """,
            {
                "run": parse_record_id(run_id),
                "status": status,
                "reason": (reason or "")[:2000],
                "diagnosis": (diagnosis or "")[:2000],
                "attempts": attempts,
            },
        )
    except Exception as exc:
        logger.debug("arm finalize_run failed (non-fatal): %s", exc)
    return None


async def reconcile_stale_runs(*, product_id: str, older_than_minutes: int = 60, pool=None) -> int:
    """Close out zombie runs: 'running' rows that no process is coming back to finish.

    A killed process (OOM, crash, a laptop lid) leaves its run at 'running' with nobody to write
    a terminal state. Nothing reconciles those on its own, so they accumulate — and once
    the attention list is full of zombies, the "needs a human" signal degrades into noise. That is
    precisely how a good instrument turns into a lying one.

    A zombie is parked, not failed: nobody judged that work either.

    The age threshold is the safety margin. A build genuinely IN FLIGHT right now (this process,
    or a concurrent ACE) is also 'running', and reaping it would be worse than the disease — so we
    only touch runs old enough that no plausible build is still working on them.

    Returns the number reconciled (0 on any failure — never raises).
    """
    from core.engine.core.db import parse_record_id, parse_rows
    from core.engine.core.db import pool as default_pool

    pool = pool or default_pool
    try:
        result = await _query(
            pool,
            f"UPDATE arm_run SET status = $status, diagnosis = $diagnosis, ended_at = time::now() "
            f"WHERE product = $product AND status = 'running' "
            f"AND started_at < time::now() - {int(older_than_minutes)}m "
            f"RETURN id",
            {
                "product": parse_record_id(product_id),
                "status": "parked",
                "diagnosis": (
                    "The process died mid-build (interrupted: crash, OOM, or kill). Nothing judged this "
                    "work. Any workspace it left behind is still on disk."
                ),
            },
        )
        return len(parse_rows(result))
    except Exception as exc:
        logger.debug("reconcile_stale_runs failed (non-fatal): %s", exc)
        return 0


async def reconcile_stranded_specs(*, product_id: str, older_than_minutes: int = 60, pool=None) -> int:
    """Release specs stuck in 'building' that nothing is actually building. Returns how many.

    The twin of reconcile_stale_runs, and the more dangerous one. build_spec() marks a spec
    'building' BEFORE dispatch. If the process dies mid-build, the run gets reconciled — but the
    SPEC stays 'building' forever. The session only picks 'approved', and build_spec refuses a
    'building' spec ("already building"). So the spec can never be built again, no error is raised,
    and nothing appears in any failure list. The work silently stops existing.

    Released to **approved**, deliberately, NOT blocked: a crashed process is not a broken
    environment. Releasing lets the loop RETRY it once — and if the environment really is dead, that
    retry parks and blocks it. Self-correcting, and it terminates (blocked is not 'building', so
    this never sees it again).

    Two guards against double-building work that IS in flight:
      - a spec with a LIVE ('running') arm_run is never touched — someone is building it right now;
      - and it must have gone 'building' long enough ago that no plausible build is still starting up
        (updated_at older than the threshold). A NULL updated_at means it predates the timestamp and
        is ancient by definition.

    Call AFTER reconcile_stale_runs, so that any remaining 'running' run is genuinely in flight.
    Returns 0 on any failure — never raises.
    """
    from core.engine.core.db import parse_record_id, parse_rows
    from core.engine.core.db import pool as default_pool

    pool = pool or default_pool
    try:
        async with pool.connection() as db:
            stranded = parse_rows(
                await db.query(
                    f"SELECT id, updated_at FROM agent_spec "
                    f"WHERE product = $p AND status = 'building' "
                    f"AND (updated_at IS NONE OR updated_at < time::now() - {int(older_than_minutes)}m)",
                    {"p": parse_record_id(product_id)},
                )
            )
            if not stranded:
                return 0

            live = parse_rows(
                await db.query(
                    "SELECT spec FROM arm_run WHERE product = $p AND status = 'running'",
                    {"p": parse_record_id(product_id)},
                )
            )
            in_flight = {str(r.get("spec")) for r in live if r.get("spec")}

            released = 0
            for spec in stranded:
                sid = str(spec["id"])
                if sid in in_flight:
                    continue  # someone is building it RIGHT NOW — releasing it would double-build
                await db.query(
                    "UPDATE $s SET status = $st, updated_at = time::now()",
                    {"s": parse_record_id(sid), "st": "approved"},
                )
                logger.info("released stranded spec %s (was 'building' with no live run)", sid)
                released += 1
        return released
    except Exception as exc:
        logger.debug("reconcile_stranded_specs failed (non-fatal): %s", exc)
        return 0


async def get_runs_needing_attention(*, product_id: str, limit: int = 50, pool=None) -> list[dict[str, Any]]:
    """The single read for "what is waiting on a human". THE reader — every surface goes through
    here rather than writing its own arm_run query, so the read cannot drift away from what
    dispatch actually writes.

    Two shapes, one meaning ("nobody is coming unless you look"):
      - PARKED:  the environment broke mid-build. Never judged; workspace preserved; diagnosis says
                 what to fix.
      - RUNNING: nobody ever finalized it — the process died mid-build. A park the engine never got
                 the chance to write (reconcile_stale_runs converts the old ones).

    A FAILED build is deliberately absent: it WAS judged, it was wrong, it was discarded. That is a
    normal outcome, not an interruption, and listing it would drown the signal.

    started_at is in the SELECT so v3's 'ORDER BY field must be selected' rule is satisfied.
    Returns [] on any failure — a status read must never raise.
    """
    from core.engine.core.db import parse_record_id, parse_rows
    from core.engine.core.db import pool as default_pool

    pool = pool or default_pool
    try:
        result = await _query(
            pool,
            """
            SELECT id, intent, arm_domain, status, reason, diagnosis, attempts, started_at, spec
            FROM arm_run
            WHERE product = $product AND status IN ['parked', 'running']
            ORDER BY started_at DESC
            LIMIT $lim
            """,
            {"product": parse_record_id(product_id), "lim": limit},
        )
        return parse_rows(result)
    except Exception as exc:
        logger.debug("get_runs_needing_attention failed (non-fatal): %s", exc)
        return []

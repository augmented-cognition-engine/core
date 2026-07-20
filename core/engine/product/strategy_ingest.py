"""Strategy Ingestion — register ACE's own strategy as graph nodes.

Idempotent reconciler: re-running seed_session_strategy() reconciles docs->graph
without duplicating. Every write binds parse_record_id RecordIDs (never <record>$x
casts or string-bound IN — the SurrealDB v3 silent-no-op trap).
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.graph.edge_writer import create_edge
from core.engine.product import strategy_seed_data as _seed
from core.engine.product.decisions import create_decision

logger = logging.getLogger(__name__)

# Statuses the docs may still DRIVE on re-ingest — the pre-work states only. ANY status past these
# is preserved: the build loop sets executing/verifying/built; a human gate sets blocked; terminal
# states are shipped/completed/superseded/failed. Re-ingest must never regress real loop or human
# progress back to a doc value (the drift the State-of-ACE audit found). Un-blocking/un-shipping is
# a live-side action, never a silent side effect of a docs edit.
DOC_DRIVABLE_STATUSES = {"draft", "approved"}


async def ingest_phase(
    title: str,
    ordinal: int,
    status: str,
    summary: str | None,
    source_ref: str | None,
    source_created: str | None,
    product_id: str,
    pool=None,
) -> str | None:
    """UPSERT a roadmap_phase by (product, ordinal). Returns the record id str."""
    pool = pool or default_pool
    prod = parse_record_id(product_id)
    try:
        async with pool.connection() as db:
            existing = parse_rows(
                await db.query(
                    "SELECT id FROM roadmap_phase WHERE product = $p AND ordinal = $o LIMIT 1",
                    {"p": prod, "o": ordinal},
                )
            )
            fields = {
                "title": title,
                "status": status,
                "summary": summary,
                "source_ref": source_ref,
                "source_created": source_created,
            }
            if existing:
                rid = parse_record_id(str(existing[0]["id"]))
                await db.query(
                    "UPDATE $id SET title=$title, status=$status, summary=$summary, "
                    "source_ref=$source_ref, source_created=$source_created",
                    {"id": rid, **fields},
                )
                return str(existing[0]["id"])
            created = parse_rows(
                await db.query(
                    "CREATE roadmap_phase SET product=$p, ordinal=$o, title=$title, "
                    "status=$status, summary=$summary, source_ref=$source_ref, "
                    "source_created=$source_created",
                    {"p": prod, "o": ordinal, **fields},
                )
            )
            return str(created[0]["id"]) if created else None
    except Exception as exc:
        logger.warning("ingest_phase(%s) failed (non-fatal): %s", ordinal, exc)
        return None


async def ingest_spec(
    objective: str,
    status: str,
    priority: str,
    phase_ordinal: int | None,
    capability_slug: str | None,
    source_refs: list[str],
    source_created: str | None,
    product_id: str,
    pool=None,
) -> str | None:
    """UPSERT an agent_spec by (product, objective). Status update + source_ref union."""
    pool = pool or default_pool
    prod = parse_record_id(product_id)
    try:
        async with pool.connection() as db:
            existing = parse_rows(
                await db.query(
                    "SELECT id, source_ref, status FROM agent_spec WHERE product = $p AND objective = $obj LIMIT 1",
                    {"p": prod, "obj": objective},
                )
            )
            # Resolve optional record refs as RecordIDs (never <record>$x cast).
            phase_id = None
            if phase_ordinal is not None:
                ph = parse_rows(
                    await db.query(
                        "SELECT id FROM roadmap_phase WHERE product = $p AND ordinal = $o LIMIT 1",
                        {"p": prod, "o": phase_ordinal},
                    )
                )
                if ph:
                    phase_id = parse_record_id(str(ph[0]["id"]))
            cap_id = None
            if capability_slug:
                cap = parse_rows(
                    await db.query(
                        "SELECT id FROM capability WHERE slug = $s LIMIT 1",
                        {"s": capability_slug},
                    )
                )
                if cap:
                    cap_id = parse_record_id(str(cap[0]["id"]))

            if existing:
                prior = existing[0].get("source_ref") or []
                if isinstance(prior, str):
                    prior = [prior]
                merged = sorted(set(prior) | set(source_refs))
                rid = parse_record_id(str(existing[0]["id"]))
                # Status-monotonic: re-ingest may only drive PRE-WORK statuses (draft/approved or a
                # legacy null). Any live status past that — set by the build loop (executing/
                # verifying/built), a human gate (blocked), or terminal (shipped/completed/
                # superseded/failed) — is PRESERVED, so re-ingest never regresses real progress.
                live_status = existing[0].get("status")
                effective_status = (
                    status if (live_status is None or live_status in DOC_DRIVABLE_STATUSES) else live_status
                )
                await db.query(
                    "UPDATE $id SET status=$status, priority=$priority, phase=$phase, "
                    "capability=$cap, source_ref=$source_ref, source_created=$source_created",
                    {
                        "id": rid,
                        "status": effective_status,
                        "priority": priority,
                        "phase": phase_id,
                        "cap": cap_id,
                        "source_ref": merged,
                        "source_created": source_created,
                    },
                )
                return str(existing[0]["id"])

            created = parse_rows(
                await db.query(
                    "CREATE agent_spec SET product=$p, objective=$obj, source='strategy_ingest', "
                    "status=$status, priority=$priority, phase=$phase, capability=$cap, "
                    "acceptance_criteria=[], source_ref=$source_ref, source_created=$source_created",
                    {
                        "p": prod,
                        "obj": objective,
                        "status": status,
                        "priority": priority,
                        "phase": phase_id,
                        "cap": cap_id,
                        "source_ref": sorted(set(source_refs)),
                        "source_created": source_created,
                    },
                )
            )
            return str(created[0]["id"]) if created else None
    except Exception as exc:
        logger.warning("ingest_spec(%r) failed (non-fatal): %s", objective[:40], exc)
        return None


async def _find_decision_by_title(title: str, product_id: str, pool=None) -> str | None:
    pool = pool or default_pool
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT id FROM decision WHERE product = $p AND title = $t LIMIT 1",
                    {"p": parse_record_id(product_id), "t": title},
                )
            )
            return str(rows[0]["id"]) if rows else None
    except Exception:
        return None


async def ingest_decision(
    title: str,
    rationale: str,
    decision_type: str,
    alternatives: list[str] | None,
    source_ref: str | None,
    source_created: str | None,
    product_id: str,
    pool=None,
) -> str | None:
    """Idempotently capture a decision: skip if a decision with this title exists."""
    existing = await _find_decision_by_title(title, product_id, pool=pool)
    if existing:
        return existing
    try:
        result = await create_decision(
            title=title,
            decision_type=decision_type,
            rationale=rationale,
            product_id=product_id,
            alternatives=alternatives,
            source=source_ref,
            pool=pool,
        )
        return str(result["id"]) if result and result.get("id") else None
    except Exception as exc:
        logger.warning("ingest_decision(%r) failed (non-fatal): %s", title[:40], exc)
        return None


async def seed_session_strategy(product_id: str = "product:platform", pool=None) -> dict:
    """Author this session's strategy into the graph. Idempotent — safe to re-run."""
    summary = {"phases": 0, "specs": 0, "decisions": 0, "supersedes": 0}
    dec_ids: dict[str, str] = {}

    for ordinal, title, status, summ in _seed.PHASES:
        if await ingest_phase(title, ordinal, status, summ, _seed.WC, None, product_id, pool=pool):
            summary["phases"] += 1

    for objective, status, priority, phase_ord, refs in _seed.SPECS:
        if await ingest_spec(objective, status, priority, phase_ord, None, refs, None, product_id, pool=pool):
            summary["specs"] += 1

    for title, rationale, dtype, alts, ref in _seed.DECISIONS:
        rid = await ingest_decision(title, rationale, dtype, alts, ref, None, product_id, pool=pool)
        if rid:
            dec_ids[title] = rid
            summary["decisions"] += 1
    for title, rationale in _seed.REJECTIONS:
        rid = await ingest_decision(title, rationale, "rejection", None, _seed.MX, None, product_id, pool=pool)
        if rid:
            dec_ids[title] = rid
            summary["decisions"] += 1

    for sup_title, sub_title in _seed.SUPERSEDES:
        a, b = dec_ids.get(sup_title), dec_ids.get(sub_title)
        if a and b and await create_edge("supersedes", a, b, {"source": "strategy_ingest"}, pool=pool):
            summary["supersedes"] += 1

    logger.info("seed_session_strategy: %s", summary)
    return summary

"""The forget erasure primitive (Phase 4).

Deliberate, single-target, reason-required, preview-then-confirm, audited
erasure of a captured insight. NOT automatic, NOT bulk — see the design spec.

A confirmed erase runs ONE SurrealDB transaction (query_raw BEGIN;...;COMMIT;):
write a content-free forget_log row, delete the insight's edges, delete the
insight row (its embedding lives in the row, so it leaves search immediately).
All-or-nothing.

See docs/superpowers/specs/2026-06-15-ace-forget-erasure-primitive-design.md
"""

from __future__ import annotations

import logging

from core.engine.capture.pattern_detector import _content_hash
from core.engine.core.db import parse_one, parse_rows
from core.engine.core.schema import _assert_no_stmt_error

logger = logging.getLogger(__name__)


async def _edge_count(db, insight_id: str) -> int:
    """Count the insight's outgoing edges. Takes an ALREADY-OPEN connection (db), not a pool.

    The insight is always the `in` endpoint — informed_by is insight->specialty
    and derived_from is insight->observation — so we match `in` only.
    """
    rows = await db.query(
        "SELECT count() AS n FROM informed_by WHERE in = <record>$id GROUP ALL",
        {"id": insight_id},
    )
    a = parse_one(rows)
    rows2 = await db.query(
        "SELECT count() AS n FROM derived_from WHERE in = <record>$id GROUP ALL",
        {"id": insight_id},
    )
    b = parse_one(rows2)
    return (int(a["n"]) if a else 0) + (int(b["n"]) if b else 0)


async def forget_insight(
    db_pool,
    insight_id: str,
    *,
    product_id: str,
    reason: str,
    actor: str,
    confirm: bool = False,
) -> dict:
    """Erase one insight by id. Dry-run preview unless confirm=True.

    Returns a preview dict (confirm=False) or an erasure result (confirm=True).
    Idempotent: erasing an already-absent id returns {erased: False} and writes
    no log row. Raises ValueError on a blank reason.
    """
    if not reason or not reason.strip():
        raise ValueError("forget requires a non-empty reason (recorded in the audit log)")

    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT content, product FROM <record>$id WHERE product = <record>$product",
                {"id": insight_id, "product": product_id},
            )
        )
        if not row:
            return {"erased": False, "would_erase": False, "reason": "not found", "insight_id": insight_id}

        content = row.get("content") or ""
        product = row.get("product")
        content_hash = _content_hash(content)
        edges = await _edge_count(db, insight_id)

        if not confirm:
            return {
                "would_erase": True,
                "confirmed": False,
                "insight_id": insight_id,
                "content_preview": content[:120],
                "content_hash": content_hash,
                "edges": edges,
                "hint": "re-call with confirm=True to erase (irreversible)",
            }

        # Bound params across the whole BEGIN..COMMIT block (proven in
        # atomic_write.py). Only the optional product CLAUSE is structural.
        set_product = "product = <record>$product, " if product else ""
        sql = f"""
        BEGIN;
        CREATE forget_log SET
            insight_id = $iid, {set_product}content_hash = $chash,
            reason = $reason, actor = $actor, source = 'ace_forget',
            edges_removed = $edges, deleted_at = time::now();
        DELETE informed_by WHERE in = <record>$iid;
        DELETE derived_from WHERE in = <record>$iid;
        DELETE <record>$iid;
        COMMIT;
        """
        params = {"iid": insight_id, "chash": content_hash, "reason": reason, "actor": actor, "edges": edges}
        if product:
            params["product"] = str(product)
        raw = await db.query_raw(sql, params)
        _assert_no_stmt_error(raw, source=f"forget_insight({insight_id})")

    logger.info("forget: erased %s (reason=%s, actor=%s, edges=%d)", insight_id, reason, actor, edges)
    return {"erased": True, "insight_id": insight_id, "content_hash": content_hash, "edges_removed": edges}


async def forget_by_hash(
    db_pool,
    content_hash: str,
    *,
    product_id: str,
    reason: str,
    actor: str,
    confirm: bool = False,
) -> dict:
    """Erase every insight whose content hashes to `content_hash`, REGARDLESS of
    status.

    The compliance 'forget this fact everywhere' verb. Scans ALL statuses (active,
    superseded, expired, contradicted, archived) — for erasure the content must be
    removed wherever it lives, including soft-retired rows that still hold it.
    Computes _content_hash over candidates in Python (forget is rare; a scan is
    cheap). Dry-run lists matches unless confirm=True.
    """
    if not reason or not reason.strip():
        raise ValueError("forget requires a non-empty reason (recorded in the audit log)")

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT id, content FROM insight WHERE product = <record>$product AND content != NONE",
                {"product": product_id},
            )
        )
    matches = [str(r["id"]) for r in rows if _content_hash(r.get("content") or "") == content_hash]

    if not confirm:
        return {"would_erase_count": len(matches), "confirmed": False, "insight_ids": matches}

    erased = 0
    for iid in matches:
        res = await forget_insight(
            db_pool,
            iid,
            product_id=product_id,
            reason=reason,
            actor=actor,
            confirm=True,
        )
        if res.get("erased"):
            erased += 1
    logger.info("forget_by_hash: erased %d insight(s) for hash=%s (actor=%s)", erased, content_hash, actor)
    return {"erased_count": erased, "content_hash": content_hash}

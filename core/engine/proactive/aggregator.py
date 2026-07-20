"""Proactive Line aggregator — ranks findings from all sources into one line.

Priority order (highest → lowest):
  1. Unresolved gates       — partner can't proceed without user input
  2. High-severity sentinel findings / decision conflicts
  3. New gap analyzer findings (last 24h)
  4. Top recommendation from prioritizer
  5. Briefing highlights    — when nothing more urgent exists
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from core.engine.core.db import (
    parse_one,
    parse_rows,
    pool,  # noqa: F401  — test-patch target for _gather_foresight_signals
)
from core.engine.proactive.models import ProactiveLine, ProactiveSource
from core.engine.proactive.voice import transform

logger = logging.getLogger(__name__)

_SIGNAL_CONFIDENCE_THRESHOLD = 0.7


async def _gather_unresolved_gates(product_id: str, db) -> list[dict]:
    try:
        result = await db.query(
            """SELECT id, entity_type, entity_id, risk_level, created_at
               FROM gate_evaluation
               WHERE product = <record>$product AND status = 'pending'
               ORDER BY created_at DESC LIMIT 5""",
            {"product": product_id},
        )
        return parse_rows(result)
    except Exception:
        return []


async def _gather_sentinel_findings(product_id: str, db) -> list[dict]:
    try:
        result = await db.query(
            """SELECT id, engine, capability_slug, dimension, description, severity, created_at
               FROM sentinel_finding
               WHERE product = <record>$product AND status = 'open'
               ORDER BY severity DESC, created_at DESC LIMIT 10""",
            {"product": product_id},
        )
        return parse_rows(result)
    except Exception:
        return []


async def _gather_gap_findings(product_id: str, db) -> list[dict]:
    """Gap analyzer findings from the last 24 hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        result = await db.query(
            """SELECT id, capability, dimension, score, gaps, assessed_at
               FROM capability_quality
               WHERE product = <record>$product AND score < 0.4 AND assessed_at > $since
               ORDER BY score ASC LIMIT 5""",
            {"product": product_id, "since": since},
        )
        return parse_rows(result)
    except Exception:
        return []


async def _gather_recommendation(product_id: str, db) -> dict | None:
    """Top recommendation from the prioritizer.

    Schema note: capability_quality fields are `score` + `capability` — the
    legacy field aliases `current_score` / `capability_slug` no longer exist
    in v105. The consumer (_recommendation_to_line) already falls back to
    the canonical names if the legacy keys are absent.
    """
    try:
        result = await db.query(
            """SELECT id, capability, dimension, score
               FROM capability_quality
               WHERE product = <record>$product AND score < 0.6
               ORDER BY score ASC LIMIT 1""",
            {"product": product_id},
        )
        row = parse_one(result)
        return row
    except Exception as exc:
        logger.warning("recommendation gather failed: %s", exc)
        return None


async def _gather_briefing_highlight(product_id: str, db) -> dict | None:
    try:
        result = await db.query(
            """SELECT id, content, created_at
               FROM briefing
               WHERE product = <record>$product
               ORDER BY created_at DESC LIMIT 1""",
            {"product": product_id},
        )
        row = parse_one(result)
        return row
    except Exception:
        return None


async def _gate_to_line(gate: dict, product_id: str) -> ProactiveLine:
    entity = gate.get("entity_type", "item")
    risk = gate.get("risk_level", "medium")
    line = await transform(
        source="unresolved_gate",
        capability=entity,
        discipline="process",
        description=f"{entity} gate is pending approval (risk: {risk})",
        severity=0.95,
    )
    return ProactiveLine(
        product_id=product_id,
        line=line,
        source=ProactiveSource.UNRESOLVED_GATE,
        source_artifact_id=str(gate.get("id", "")),
        drill_down_url=f"/gates/{gate.get('entity_type', 'item')}/{gate.get('entity_id', '')}",
        severity=0.95,
        generated_at=datetime.now(timezone.utc),
    )


async def _finding_to_line(finding: dict, product_id: str) -> ProactiveLine:
    severity = float(finding.get("severity", 0.5))
    cap_slug = str(finding.get("capability_slug", finding.get("capability", "unknown")))
    dimension = str(finding.get("dimension", "general"))
    description = str(finding.get("description", f"{dimension} gap in {cap_slug}"))
    line = await transform(
        source="sentinel_finding",
        capability=cap_slug,
        discipline=dimension,
        description=description,
        severity=severity,
    )
    return ProactiveLine(
        product_id=product_id,
        line=line,
        source=ProactiveSource.SENTINEL_FINDING,
        source_artifact_id=str(finding.get("id", "")),
        drill_down_url=f"/capabilities/{cap_slug}?dimension={dimension}",
        severity=severity,
        generated_at=datetime.now(timezone.utc),
    )


async def _gap_to_line(gap: dict, product_id: str) -> ProactiveLine:
    score = float(gap.get("score", 0.3))
    severity = round(1.0 - score, 2)
    cap = str(gap.get("capability", gap.get("capability_slug", "unknown")))
    dimension = str(gap.get("dimension", "general"))
    gaps_list = gap.get("gaps") or []
    first_gap = gaps_list[0] if gaps_list else f"{dimension} coverage"
    line = await transform(
        source="gap_analyzer",
        capability=cap,
        discipline=dimension,
        description=str(first_gap)[:120],
        severity=severity,
    )
    return ProactiveLine(
        product_id=product_id,
        line=line,
        source=ProactiveSource.SENTINEL_FINDING,
        source_artifact_id=str(gap.get("id", "")),
        drill_down_url=f"/capabilities/{cap}?dimension={dimension}",
        severity=severity,
        generated_at=datetime.now(timezone.utc),
    )


async def _recommendation_to_line(rec: dict, product_id: str) -> ProactiveLine:
    cap_slug = str(rec.get("capability_slug", rec.get("capability", "unknown")))
    dimension = str(rec.get("dimension", "general"))
    score = float(rec.get("current_score", rec.get("score", 0.5)))
    severity = round(0.5 + (0.5 - score), 2)
    line = await transform(
        source="prioritizer",
        capability=cap_slug,
        discipline=dimension,
        description=f"Low {dimension} score ({score:.2f}) — top priority improvement opportunity",
        severity=severity,
    )
    return ProactiveLine(
        product_id=product_id,
        line=line,
        source=ProactiveSource.RECOMMENDED_ACTION,
        source_artifact_id=str(rec.get("id", "")),
        drill_down_url=f"/capabilities/{cap_slug}",
        severity=severity,
        generated_at=datetime.now(timezone.utc),
    )


async def _briefing_to_line(briefing: dict, product_id: str) -> ProactiveLine:
    content = briefing.get("content", {})
    if isinstance(content, dict):
        highlights = content.get("highlights", [])
        first = highlights[0]["content"] if highlights else content.get("narrative", "")[:120]
    else:
        first = str(content)[:120]
    line = await transform(
        source="briefing",
        capability="product",
        discipline="overview",
        description=str(first)[:120],
        severity=0.2,
    )
    return ProactiveLine(
        product_id=product_id,
        line=line,
        source=ProactiveSource.BRIEFING_HIGHLIGHT,
        source_artifact_id=str(briefing.get("id", "")),
        drill_down_url="/briefings/latest",
        severity=0.2,
        generated_at=datetime.now(timezone.utc),
    )


async def _gather_foresight_signals(product_id: str, db) -> list[dict]:
    """Fetch recent high-confidence internal signals for the Proactive Line."""
    try:
        result = await db.query(
            """SELECT id, kind, description, subject, confidence, created_at
               FROM signal
               WHERE product = <record>$product
               AND confidence >= $threshold
               ORDER BY confidence DESC, created_at DESC LIMIT 3""",
            {"product": product_id, "threshold": _SIGNAL_CONFIDENCE_THRESHOLD},
        )
        rows = parse_rows(result)
        return [r for r in rows if float(r.get("confidence", 0)) >= _SIGNAL_CONFIDENCE_THRESHOLD]
    except Exception:
        return []


async def _foresight_signal_to_line(signal: dict, product_id: str) -> ProactiveLine:
    kind = str(signal.get("kind", "signal"))
    description = str(signal.get("description", ""))[:200]
    subject = str(signal.get("subject", ""))
    severity = float(signal.get("confidence", 0.7))

    line = await transform(
        source="foresight_signal",
        capability=subject.split(":")[-1] if ":" in subject else subject,
        discipline=kind,
        description=description,
        severity=severity,
    )
    return ProactiveLine(
        product_id=product_id,
        line=line,
        source=ProactiveSource.FORESIGHT_SIGNAL,
        source_artifact_id=str(signal.get("id", "")),
        drill_down_url=f"/signals/{signal.get('id', '')}",
        severity=severity,
        generated_at=datetime.now(timezone.utc),
    )


async def aggregate(product_id: str, db=None) -> list[ProactiveLine]:
    """Pull from all sources and return a ranked list of ProactiveLines.

    Performance contract: this function used to interleave DB queries with
    LLM transforms inside a single connection lease, holding a SurrealDB
    connection for the entire 25-30 second aggregate. That saturated the
    pool's 10 connections quickly and made unrelated GETs (e.g.
    /canvas/sessions/{id}) queue 18-84 seconds waiting for a connection.

    New shape:
      1. Acquire a DB connection internally, run all DB gathers in
       parallel, RELEASE the connection. (`db` param kept optional for
       legacy callers that still pass one — those use the provided
       connection for the read phase.)
      2. The LLM transforms below don't need DB; the connection has been
       returned to the pool by the time they start.
      3. Run all per-candidate _to_line LLM calls in parallel (gather)
       instead of sequentially. The Haiku transformer call latency is
       ~3-5s each; parallelizing turns N*3s into max(3s, ...) ≈ 3-5s.

    Net effect: cold aggregate goes from ~25-30s down to ~3-5s, and the
    DB pool spends ~milliseconds on this call instead of seconds. The
    proactive cache TTL stays at 60s.
    """
    import asyncio

    # Step 1: parallel DB queries — acquire a connection only for this
    # phase. If caller provided a db, use it; otherwise grab one ourselves
    # and release before doing LLM work.
    async def _gather_all(_db):
        return await asyncio.gather(
            _gather_unresolved_gates(product_id, _db),
            _gather_sentinel_findings(product_id, _db),
            _gather_gap_findings(product_id, _db),
            _gather_foresight_signals(product_id, _db),
            _gather_recommendation(product_id, _db),
            _gather_briefing_highlight(product_id, _db),
        )

    if db is not None:
        gates, findings, gaps, signals, rec, brf = await _gather_all(db)
    else:
        async with pool.connection() as _db:
            gates, findings, gaps, signals, rec, brf = await _gather_all(_db)
    # From here on, no DB connection is held.

    # Step 2: build the LLM-transform tasks. Each helper runs a Haiku call
    # internally; do them all in parallel.
    async def _safe(coro):
        try:
            return await coro
        except Exception:
            return None

    transform_tasks: list = []
    for gate in gates:
        transform_tasks.append(_safe(_gate_to_line(gate, product_id)))
    for finding in findings:
        transform_tasks.append(_safe(_finding_to_line(finding, product_id)))
    for gap in gaps:
        transform_tasks.append(_safe(_gap_to_line(gap, product_id)))
    for sig in signals:
        transform_tasks.append(_safe(_foresight_signal_to_line(sig, product_id)))
    if rec:
        transform_tasks.append(_safe(_recommendation_to_line(rec, product_id)))

    candidates: list[ProactiveLine] = []
    if transform_tasks:
        results = await asyncio.gather(*transform_tasks)
        candidates = [r for r in results if r is not None]

    # Tier 4: briefing highlight (only if nothing else)
    if not candidates and brf:
        try:
            candidates.append(await _briefing_to_line(brf, product_id))
        except Exception:
            pass

    candidates.sort(key=lambda p: p.rank_key())
    return candidates


async def compute_current(product_id: str, db=None) -> ProactiveLine | None:
    """Return the single highest-priority ProactiveLine, or None.

    `db` is optional — if omitted, aggregate() acquires and releases its
    own pool connection for the read phase. Kept for the WS handler which
    has a connection in scope already.
    """
    ranked = await aggregate(product_id, db)
    return ranked[0] if ranked else None

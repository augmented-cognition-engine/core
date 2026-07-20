"""ace_query_uncertainty syscall — structural primitive for "ask when uncertain".

When the OS's self-model has a gap, raise a query rather than silently default.
Renders to the Proactive Line.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.engine.core.db import parse_rows

VALID_SCOPES = {"state", "ambition", "contributors", "learnings"}
VALID_FALLBACKS = {
    "pause",
    "proceed_with_assumption",
    "dispatch_research",
    "default_safe",
}


@dataclass
class UncertaintyQuery:
    id: str
    product_id: str
    scope: str
    question: str
    fallback_action: str
    posed_at: datetime
    status: str = "open"
    answered_at: Optional[datetime] = None
    answer: Optional[str] = None


async def query_uncertainty(
    pool,
    product_id: str,
    scope: str,
    question: str,
    fallback_action: str,
) -> UncertaintyQuery:
    """Create an uncertainty query. Returns the persisted record."""
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of {VALID_SCOPES}; got {scope!r}")
    if fallback_action not in VALID_FALLBACKS:
        raise ValueError(f"fallback_action must be one of {VALID_FALLBACKS}; got {fallback_action!r}")

    async with pool.connection() as db:
        result = await db.query(
            """CREATE uncertainty_queries CONTENT {
                product: <record>$pid,
                scope: <string>$scope,
                question: <string>$q,
                fallback_action: <string>$fb,
                posed_at: time::now(),
                status: 'open'
            } RETURN AFTER""",
            {"pid": product_id, "scope": scope, "q": question, "fb": fallback_action},
        )
    rows = parse_rows(result)
    row = rows[0]
    query = UncertaintyQuery(
        id=str(row.get("id")),
        product_id=product_id,
        scope=scope,
        question=question,
        fallback_action=fallback_action,
        posed_at=row.get("posed_at"),
        status="open",
    )
    from core.engine.events.bus import bus

    await bus.emit(
        "canvas.uncertainty.opened",
        {
            "product_id": product_id,
            "query_id": query.id,
            "scope": scope,
            "question": question,
        },
    )
    return query


async def get_open_queries(pool, product_id: str) -> list[UncertaintyQuery]:
    async with pool.connection() as db:
        result = await db.query(
            """SELECT * FROM uncertainty_queries
               WHERE product = <record>$pid AND status = 'open'""",
            {"pid": product_id},
        )
    rows = parse_rows(result)
    return [
        UncertaintyQuery(
            id=str(r.get("id")),
            product_id=product_id,
            scope=r.get("scope", ""),
            question=r.get("question", ""),
            fallback_action=r.get("fallback_action", ""),
            posed_at=r.get("posed_at"),
            status=r.get("status", "open"),
            answered_at=r.get("answered_at"),
            answer=r.get("answer"),
        )
        for r in rows
    ]


async def answer_query(pool, query_id: str, answer: str, product_id: str | None = None) -> None:
    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$id SET
                status = 'answered',
                answered_at = time::now(),
                answer = <string>$ans""",
            {"id": query_id, "ans": answer},
        )
    from core.engine.events.bus import bus

    await bus.emit(
        "canvas.uncertainty.answered",
        {
            "product_id": product_id or "product:platform",
            "query_id": query_id,
            "answer": answer,
            "fallback_taken": False,
        },
    )

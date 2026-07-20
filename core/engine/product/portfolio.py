"""Portfolio aggregation — badge computation and project status summaries."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)

# Badge severity hierarchy: critical→red, actionable→yellow, informational→blue
_TIER_TO_SEVERITY = {
    "critical": "red",
    "actionable": "yellow",
    "informational": "blue",
}
_SEVERITY_RANK = {"red": 3, "yellow": 2, "blue": 1}


def compute_badge_severity(notifications: list[dict]) -> dict:
    """Compute badge severity from a list of unread notifications.

    Returns {"severity": "red"|"yellow"|"blue"|None, "count": int}.
    """
    unread = [n for n in notifications if not n.get("read", True)]
    if not unread:
        return {"severity": None, "count": 0}

    highest = None
    for n in unread:
        sev = _TIER_TO_SEVERITY.get(n.get("tier", ""), None)
        if sev and (highest is None or _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(highest, 0)):
            highest = sev

    return {"severity": highest, "count": len(unread)}


async def get_project_badges(product_id: str, user_id: str) -> dict[str, dict]:
    """Return badge data for all projects. Keyed by project slug.

    Also includes a "_tower" key with the aggregate badge across all projects.
    """
    async with pool.connection() as db:
        # Get all projects
        projects = parse_rows(
            await db.query(
                "SELECT id, slug, name, ecosystem FROM project WHERE product = <record>$product",
                {"product": product_id},
            )
        )

        # Get all unread notifications grouped by project
        notifications = parse_rows(
            await db.query(
                """SELECT tier, read, project FROM notification
               WHERE product = <record>$product AND user = <record>$user
                 AND read = false AND dismissed = false""",
                {"product": product_id, "user": user_id},
            )
        )

    # Group notifications by project
    by_project: dict[str | None, list[dict]] = {}
    for n in notifications:
        proj = str(n.get("project", "")) or None
        by_project.setdefault(proj, []).append(n)

    # Compute per-project badges
    badges: dict[str, dict] = {}
    all_unread: list[dict] = []

    for p in projects:
        slug = p.get("slug", "")
        pid = str(p.get("id", ""))
        proj_notifs = by_project.get(pid, [])
        badges[slug] = {
            **compute_badge_severity(proj_notifs),
            "name": p.get("name", slug),
            "ecosystem": str(p.get("ecosystem", "")) or None,
        }
        all_unread.extend(proj_notifs)

    # Unscoped notifications (no project) count toward tower aggregate
    all_unread.extend(by_project.get(None, []))

    badges["_tower"] = compute_badge_severity(all_unread)

    return badges


async def get_cross_product_alerts(product_id: str) -> list[dict]:
    """Return alerts that span multiple products or are org-wide.

    Returns notifications that have no project (org-wide) or patterns
    detected across products.
    """
    async with pool.connection() as db:
        # Org-wide unread notifications (no project scope)
        org_alerts = parse_rows(
            await db.query(
                """SELECT id, tier, category, title, body, link, created_at
                   FROM notification
                   WHERE product = <record>$product
                     AND project IS NONE
                     AND read = false
                     AND dismissed = false
                     AND tier IN ['critical', 'actionable']
                   ORDER BY created_at DESC
                   LIMIT 10""",
                {"product": product_id},
            )
        )

    return [serialize_record(a) for a in org_alerts]


async def get_portfolio_summary(product_id: str) -> list[dict]:
    """Return summary cards for all projects in the portfolio.

    Each card: name, slug, ecosystem, description, agent_count, updated_at.
    """
    async with pool.connection() as db:
        projects = parse_rows(
            await db.query(
                """SELECT id, slug, name, ecosystem, description, active_disciplines, icon_url, updated_at
               FROM project WHERE product = <record>$product ORDER BY updated_at DESC""",
                {"product": product_id},
            )
        )

        # Active agent counts per project
        agents = parse_rows(
            await db.query(
                """SELECT project, count() as cnt FROM agent_session
               WHERE product = <record>$product AND state NOT IN ['done', 'failed', 'abandoned']
               GROUP BY project""",
                {"product": product_id},
            )
        )

    agent_counts = {str(a.get("project", "")): a.get("cnt", 0) for a in agents}

    cards = []
    for p in projects:
        pid = str(p.get("id", ""))
        cards.append(
            serialize_record(
                {
                    "slug": p.get("slug", ""),
                    "name": p.get("name", ""),
                    "ecosystem": p.get("ecosystem"),
                    "description": p.get("description", ""),
                    "active_disciplines": p.get("active_disciplines", []),
                    "agent_count": agent_counts.get(pid, 0),
                    "icon_url": p.get("icon_url"),
                    "updated_at": p.get("updated_at"),
                }
            )
        )

    return cards

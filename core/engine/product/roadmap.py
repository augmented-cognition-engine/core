"""The Living Roadmap — roadmap computed as a projection over the graph.

Spine: the StrategicPrioritizer's ranked recs (the 'what's next'), enriched with
spec status + staleness, bucketed into lanes. Read-only, fully non-fatal — a
failing sub-reader degrades an item/lane, never the whole roadmap.
"""

from __future__ import annotations

import logging

from core.engine.core.db import pool
from core.engine.product.roadmap_models import LANES, Roadmap, RoadmapItem, RoadmapStaleness
from core.engine.product.strategic_prioritizer import StrategicPrioritizer

logger = logging.getLogger(__name__)


def _get(rec, attr: str, default=None):
    """Duck-typed getter — works for both dataclass instances and dicts."""
    if isinstance(rec, dict):
        return rec.get(attr, default)
    return getattr(rec, attr, default)


_TIER = {"phase": 2, "spec": 1, "gap": 0}
_GAP_FLOOR = 5  # reserved roadmap slots so capability gaps still surface below decided work


def _tier(item) -> int:
    return _TIER.get(item.kind, 0)


def _merge_intent_first(strategy_items, gap_items, max_items):
    """Merge the two roadmap sources honoring the picked "both, intent-first" rule.

    Decided work (phase > spec) leads, but we always reserve up to `_GAP_FLOOR`
    slots so the top capability gaps still surface below it — never starved out
    when the strategy item count exceeds the cap.
    """
    strat = sorted(strategy_items, key=lambda i: (_tier(i), i.rank), reverse=True)
    gaps = sorted(gap_items, key=lambda i: i.rank, reverse=True)
    strat_keep = max(max_items - _GAP_FLOOR, 0)
    kept = strat[:strat_keep]
    kept += gaps[: max(0, max_items - len(kept))]
    return sorted(kept, key=lambda i: (_tier(i), i.rank), reverse=True)


def _lane_for_strategy_item(kind: str, status: str | None) -> str:
    """Lane from a strategy item's own status (not gap-severity)."""
    if kind == "phase":
        return {"active": "now", "next": "next", "done": "done", "parked": "parked"}.get(status or "next", "next")
    # specs
    return {
        "shipped": "done",
        "building": "now",
        "approved": "next",
        "draft": "next",
        "blocked": "blocked",
        "superseded": "parked",
        "built": "review",
    }.get(status or "draft", "next")


async def _project_strategy_items(db, product_id: str) -> list[RoadmapItem]:
    """Second roadmap source: roadmap_phase + non-superseded agent_spec nodes."""
    from core.engine.core.db import parse_record_id, parse_rows

    items: list[RoadmapItem] = []
    prod = parse_record_id(product_id)
    try:
        phases = parse_rows(
            await db.query(
                "SELECT title, ordinal, status, summary, source_ref FROM roadmap_phase "
                "WHERE product = $p ORDER BY ordinal",
                {"p": prod},
            )
        )
        for ph in phases:
            items.append(
                RoadmapItem(
                    title=str(ph.get("title", "")),
                    pillar="",
                    discipline=None,
                    rank=2.0 + (1.0 - (int(ph.get("ordinal", 9)) / 100.0)),  # earlier phase ranks higher
                    rationale=str(ph.get("summary", "") or ""),
                    kind="phase",
                    source_ref=ph.get("source_ref"),
                    lane=_lane_for_strategy_item("phase", ph.get("status")),
                )
            )
    except Exception as exc:
        logger.warning("_project_strategy_items: phases failed (non-fatal): %s", exc)
    try:
        specs = parse_rows(
            await db.query(
                "SELECT id, objective, status, priority, source_ref FROM agent_spec "
                "WHERE product = $p AND source = 'strategy_ingest' AND status != 'superseded'",
                {"p": prod},
            )
        )
        prio = {"high": 1.0, "medium": 0.6, "low": 0.3}
        for sp in specs:
            refs = sp.get("source_ref") or []
            item = RoadmapItem(
                title=str(sp.get("objective", "")),
                pillar="",
                discipline=None,
                rank=1.0 + prio.get(str(sp.get("priority", "medium")), 0.6),
                kind="spec",
                source_ref=(refs[0] if isinstance(refs, list) and refs else None),
                lane=_lane_for_strategy_item("spec", sp.get("status")),
                spec_status=sp.get("status"),
            )
            if sp.get("status") == "built" and sp.get("id"):
                try:
                    ao = parse_rows(
                        await db.query(
                            "SELECT workspace_branch, diff_summary, created_at FROM action_outcome "
                            "WHERE spec = $s ORDER BY created_at DESC LIMIT 1",
                            {"s": parse_record_id(str(sp["id"]))},
                        )
                    )
                    if ao:
                        branch = ao[0].get("workspace_branch") or "?"
                        diff = ao[0].get("diff_summary") or ""
                        item.rationale = f"arm-built · {branch} · {diff} · approve to ship".strip()
                except Exception as exc:
                    logger.warning("roadmap: action_outcome join failed (non-fatal): %s", exc)
            items.append(item)
    except Exception as exc:
        logger.warning("_project_strategy_items: specs failed (non-fatal): %s", exc)
    return items


def _bucket_lane(item: RoadmapItem, is_top: bool) -> str:
    """v1 lane rule. Staleness/spec-status refine this before bucketing."""
    if item.kind in ("phase", "spec"):
        return item.lane  # strategy items carry their own status-derived lane
    if item.staleness in (RoadmapStaleness.SUPERSEDED, RoadmapStaleness.DECAYED):
        return "parked"
    if item.spec_status == "shipped":
        return "done"
    if item.blocking_patterns:
        return "blocked"
    if item.spec_status == "building" or is_top:
        return "now"
    return "next"


async def _assess_item(item: RoadmapItem, db) -> RoadmapItem:
    """Enrich an item with spec status + staleness via decay + Graph Tensions supersession."""
    from core.engine.product.roadmap_staleness import assess_decay, lookup_spec_status

    if item.kind in ("phase", "spec"):
        # Strategy items carry their own status/lane from _project_strategy_items;
        # gap-enrichment (keyed on capability_slug) would null their status. Skip it.
        return item

    status, superseded = await lookup_spec_status(item, db)
    item.spec_status = status
    if superseded:
        item.staleness = RoadmapStaleness.SUPERSEDED
    elif assess_decay(item) is RoadmapStaleness.DECAYED:
        item.staleness = RoadmapStaleness.DECAYED
    return item


async def compute_roadmap(product_id: str = "product:platform", now_count: int = 3, max_items: int = 25) -> Roadmap:
    """Compute the current roadmap from the graph. Always fresh; never hand-edited."""
    roadmap = Roadmap(product_id=product_id, lanes={lane: [] for lane in LANES})
    try:
        recs = await StrategicPrioritizer(pool).prioritize(product_id)
    except Exception as exc:
        logger.warning("compute_roadmap: prioritizer failed (non-fatal): %s", exc)
        return roadmap

    items: list[RoadmapItem] = []
    for r in recs:
        if _get(r, "type", "gap") != "gap":
            continue  # skip non-gap recs (e.g. innovate-mode rows)
        cap_slug = _get(r, "capability_slug", "") or ""
        dimension = _get(r, "dimension", None)
        current = float(_get(r, "current_score", 0.0) or 0.0)
        gaps_list = _get(r, "gaps", []) or []
        title = f"{cap_slug}.{dimension}" if dimension else cap_slug
        items.append(
            RoadmapItem(
                title=title,
                pillar="",  # prioritizer dicts have no pillar; keep blank
                discipline=dimension,
                capability_slug=cap_slug,
                gap=round(1.0 - current, 3),  # severity proxy: lower score → bigger gap
                rank=float(_get(r, "priority_score", 0.0) or 0.0),
                rationale="; ".join(str(g) for g in gaps_list[:2]),
                blocking_patterns=list(_get(r, "blocking_patterns", []) or []),
                spec_status=None,
                staleness=RoadmapStaleness.FRESH,
                lane="next",
                cbt=int(_get(r, "consecutive_briefings_at_top", 0) or 0),
            )
        )
    # Second source: our intentional strategy (phases + specs).
    strategy_items: list[RoadmapItem] = []
    try:
        async with pool.connection() as db:
            strategy_items = await _project_strategy_items(db, product_id)
    except Exception as exc:
        logger.warning("compute_roadmap: strategy projection failed (non-fatal): %s", exc)

    # Intent-first, but honor "both": decided work leads, with a reserved gap floor.
    items = _merge_intent_first(strategy_items, items, max_items)

    try:
        async with pool.connection() as db:
            items = [await _assess_item(it, db) for it in items]
    except Exception as exc:
        logger.warning("compute_roadmap: enrichment failed (non-fatal): %s", exc)

    ranked = sorted(items, key=lambda i: i.rank, reverse=True)
    top_titles = {i.title for i in ranked[:now_count]}
    for it in ranked:
        it.lane = _bucket_lane(it, is_top=it.title in top_titles)
        roadmap.lanes[it.lane].append(it)
    return roadmap

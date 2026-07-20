"""ROI detection — post-task hook that identifies value delivered by intelligence.

Runs after utilization tracking in the executor. For each reflected insight,
checks what type of value it provided (mistake prevented, gap filled, etc.)
and writes roi_event records with estimated time savings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.engine.intelligence.attribution import AttributionResult

logger = logging.getLogger(__name__)

# Estimated time saved per event type (minutes)
TIME_SAVED = {
    "mistake_prevented": 30,
    "gap_filled": 45,
    "knowledge_reused": 15,
    "connection_surfaced": 120,
    "correction_propagated": 20,
}


async def detect_roi_events(
    task_record: dict,
    utilization: dict,
    product_id: str,
    db,
) -> list[dict]:
    """Detect ROI events from a completed task's intelligence utilization.

    Args:
        task_record: The completed task record with id, domain_path, etc.
        utilization: The utilization dict from track() with reflected_ids.
        product_id: The org ID.
        db: SurrealDB connection (already acquired).

    Returns:
        List of created roi_event dicts.
    """
    reflected_ids = utilization.get("reflected_ids", [])
    if not reflected_ids:
        return []

    task_id = task_record.get("id", "")
    snapshot = task_record.get("intelligence_loaded", {})
    insights = snapshot.get("insights", [])
    cross_domain = snapshot.get("cross_domain", [])

    # Build lookup: insight_id -> insight dict
    insight_map = {}
    for ins in insights:
        iid = str(ins.get("id", ""))
        if iid:
            insight_map[iid] = ins
    for cd in cross_domain:
        iid = str(cd.get("insight_id", ""))
        if iid:
            insight_map[iid] = cd

    events = []

    # Check each reflected insight
    for rid in reflected_ids:
        rid_str = str(rid)
        insight = insight_map.get(rid_str, {})
        insight_type = insight.get("insight_type", "")
        source = insight.get("source_domain", "") or insight.get("source", "")

        if insight_type == "correction":
            events.append(
                {
                    "event_type": "mistake_prevented",
                    "insight_ids": [rid_str],
                    "estimated_time_saved_minutes": TIME_SAVED["mistake_prevented"],
                    "description": f"Correction insight reflected in task output — prevented repeating: {str(insight.get('content', ''))[:100]}",
                }
            )
        elif "gap_researcher" in source:
            events.append(
                {
                    "event_type": "gap_filled",
                    "insight_ids": [rid_str],
                    "estimated_time_saved_minutes": TIME_SAVED["gap_filled"],
                    "description": f"Gap-researched insight used: {str(insight.get('content', ''))[:100]}",
                }
            )
        elif "knowledge_verifier" in source:
            events.append(
                {
                    "event_type": "knowledge_reused",
                    "insight_ids": [rid_str],
                    "estimated_time_saved_minutes": TIME_SAVED["knowledge_reused"],
                    "description": f"Verified knowledge reused: {str(insight.get('content', ''))[:100]}",
                }
            )

    # Check cross-domain reflected insights
    cross_domain_reflected = []
    for cd in cross_domain:
        cd_id = str(cd.get("insight_id", ""))
        if cd_id in [str(r) for r in reflected_ids]:
            cross_domain_reflected.append(cd_id)

    if cross_domain_reflected:
        events.append(
            {
                "event_type": "connection_surfaced",
                "insight_ids": cross_domain_reflected,
                "estimated_time_saved_minutes": TIME_SAVED["connection_surfaced"],
                "description": f"Cross-domain intelligence from synaptic graph reflected in output ({len(cross_domain_reflected)} insights)",
            }
        )

    # Write events to DB
    created = []
    for event in events:
        try:
            result = await db.query(
                """
                CREATE roi_event SET
                    product = <record>$product,
                    event_type = $event_type,
                    task_id = $task_id,
                    insight_ids = $insight_ids,
                    estimated_time_saved_minutes = $time_saved,
                    description = $description,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "event_type": event["event_type"],
                    "task_id": task_id,
                    "insight_ids": event["insight_ids"],
                    "time_saved": event["estimated_time_saved_minutes"],
                    "description": event["description"],
                },
            )
            rows = result[0] if result and isinstance(result[0], list) else (result or [])
            if rows:
                created.append(rows[0])
        except Exception as exc:
            logger.warning("Failed to write roi_event: %s", exc)

    if created:
        logger.info("ROI detection: %d events for task %s", len(created), task_id)

    return created


async def detect_roi_events_from_attribution(
    task_record: dict,
    attribution_result: AttributionResult | None,
    product_id: str,
    db,
) -> list[dict]:
    """Detect ROI events from attribution-based insight scoring.

    Replaces the heuristic reflected_ids approach for the single-agent path.
    Uses attribution weights to determine event_type:
      - weight=5 (correction) → mistake_prevented
      - weight=2 (pattern/convention/preference) → knowledge_reused
      - weight=1 (other) → knowledge_reused with halved time estimate

    Args:
        task_record: Completed task record (must have 'id').
        attribution_result: Result from attribute_structural / attribute_llm.
        product_id: Product record ID.
        db: SurrealDB connection (already acquired).

    Returns:
        List of created roi_event dicts.
    """
    if attribution_result is None or not attribution_result.attributed_ids:
        return []

    task_id = task_record.get("id", "")
    events = []

    for insight_id in attribution_result.attributed_ids:
        weight = attribution_result.weights.get(insight_id, 1)
        if weight >= 5:
            event_type = "mistake_prevented"
            time_saved = TIME_SAVED["mistake_prevented"]
            description = f"Correction insight attributed in output — prevented error: {insight_id}"
        else:
            event_type = "knowledge_reused"
            # Higher weight (2) → full rate; lower weight (1) → half rate
            base_time = TIME_SAVED["knowledge_reused"]
            time_saved = base_time if weight >= 2 else base_time // 2
            description = f"Knowledge insight attributed in output: {insight_id}"

        events.append(
            {
                "event_type": event_type,
                "insight_ids": [insight_id],
                "estimated_time_saved_minutes": time_saved,
                "description": description,
            }
        )

    created = []
    for event in events:
        try:
            result = await db.query(
                """
                CREATE roi_event SET
                    product = <record>$product,
                    event_type = $event_type,
                    task_id = $task_id,
                    insight_ids = $insight_ids,
                    estimated_time_saved_minutes = $time_saved,
                    description = $description,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "event_type": event["event_type"],
                    "task_id": task_id,
                    "insight_ids": event["insight_ids"],
                    "time_saved": event["estimated_time_saved_minutes"],
                    "description": event["description"],
                },
            )
            rows = result[0] if result and isinstance(result[0], list) else (result or [])
            if rows:
                created.append(rows[0])
        except Exception as exc:
            logger.warning("Failed to write roi_event from attribution: %s", exc)

    if created:
        logger.info("Attribution ROI detection: %d events for task %s", len(created), task_id)

    return created

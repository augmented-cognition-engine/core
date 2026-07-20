"""Notification trigger definitions — what events create which tier.

10 trigger types mapped to tiers. Each trigger is a simple function
that calls dispatcher.dispatch() with the right parameters.
"""

from __future__ import annotations

from core.engine.notifications.dispatcher import dispatch

# Trigger → tier mapping
TRIGGER_TIERS = {
    "milestone_completed": "actionable",
    "approval_needed": "critical",
    "conflict_detected": "critical",
    "briefing_ready": "actionable",
    "idea_ready": "actionable",
    "job_paused": "actionable",
    "cost_approaching": "actionable",
    "synapse_proposal": "informational",
    "engine_error": "critical",
    "handoff_assigned": "actionable",
    "live_conflict_detected": "critical",
    "cross_pollination_winner": "informational",
}


async def notify_milestone_completed(product_id: str, user_id: str, milestone_title: str, initiative_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "actionable",
        "milestone_completed",
        f"Milestone completed: {milestone_title}",
        link=f"/initiatives/{initiative_id}",
        **kwargs,
    )


async def notify_approval_needed(product_id: str, user_id: str, milestone_title: str, milestone_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "critical",
        "approval_needed",
        f"Approval needed: {milestone_title}",
        body="A milestone is waiting for your approval.",
        link=f"/initiatives/{milestone_id}",
        **kwargs,
    )


async def notify_conflict_detected(product_id: str, user_id: str, conflict_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "critical",
        "conflict_detected",
        "Intelligence conflict detected",
        body="Two insights appear to contradict each other.",
        link="/conflicts",
        source_record=conflict_id,
        **kwargs,
    )


async def notify_briefing_ready(product_id: str, user_id: str, briefing_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "actionable",
        "briefing_ready",
        "Weekly briefing ready",
        link="/briefings",
        source_record=briefing_id,
        **kwargs,
    )


async def notify_idea_ready(product_id: str, user_id: str, idea_title: str, idea_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "actionable",
        "idea_ready",
        f"Idea ready: {idea_title}",
        body="Incubation complete. Review the brief and activate.",
        link="/ideas",
        source_record=idea_id,
        **kwargs,
    )


async def notify_job_paused(product_id: str, user_id: str, reason: str, initiative_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "actionable",
        "job_paused",
        f"Initiative paused: {reason}",
        link=f"/initiatives/{initiative_id}",
        **kwargs,
    )


async def notify_cost_approaching(product_id: str, user_id: str, pct: float, initiative_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "actionable",
        "cost_approaching",
        f"Cost budget at {pct:.0f}%",
        body="Approaching the cost limit. Consider pausing or increasing the budget.",
        link=f"/initiatives/{initiative_id}",
        **kwargs,
    )


async def notify_synapse_proposal(product_id: str, user_id: str, synapse_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "informational",
        "synapse_proposal",
        "New synapse proposal",
        link="/graph",
        source_record=synapse_id,
        **kwargs,
    )


async def notify_engine_error(product_id: str, user_id: str, engine_name: str, error: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "critical",
        "engine_error",
        f"Engine error: {engine_name}",
        body=error[:200],
        link="/sentinel",
        **kwargs,
    )


async def notify_handoff_assigned(product_id: str, user_id: str, work_item_title: str, work_item_id: str, **kwargs):
    return await dispatch(
        product_id,
        user_id,
        "actionable",
        "handoff_assigned",
        f"Handoff: {work_item_title}",
        body="A work item has been assigned to you for manual completion.",
        source_record=work_item_id,
        **kwargs,
    )


async def notify_live_conflict_detected(
    product_id: str,
    user_id: str,
    files: list[str],
    severity: str,
    initiative_id: str = "",
    **kwargs,
):
    file_list = ", ".join(files[:5])
    return await dispatch(
        product_id,
        user_id,
        "critical",
        "live_conflict_detected",
        f"Live conflict detected ({severity}): {file_list}",
        body="Multiple work items modified overlapping code. Review before merging.",
        link=f"/initiatives/{initiative_id}" if initiative_id else "/execute",
        **kwargs,
    )


async def notify_cross_pollination_winner(
    product_id: str,
    user_id: str,
    origin_specialty: str,
    target_specialty: str,
    improvement: float,
    **kwargs,
):
    return await dispatch(
        product_id,
        user_id,
        "informational",
        "cross_pollination_winner",
        f"Intelligence propagated: {origin_specialty} -> {target_specialty} (+{improvement:.1%})",
        body=f"A winning insight from {origin_specialty} was successfully validated in {target_specialty}.",
        link="/experiments",
        **kwargs,
    )

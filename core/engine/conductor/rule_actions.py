# engine/conductor/rule_actions.py
"""Rule action executors — the "hands" of the conductor.

Each action type has an async executor function. Actions are dispatched
by type string from the rule's actions array.  The conductor calls
execute_action() for each action sequentially.

13 action types:
  transition, notify, emit_event, escalate, update_track,
  assess_risk, generate_spec, decompose_spec, execute_plan,
  verify_spec, reassess_quality, wait_for_human, run_rule
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.engine.conductor.rule_conditions import _interpolate
from core.engine.conductor.state_machine import CapabilityLifecycleMachine
from core.engine.events.bus import bus
from core.engine.notifications.dispatcher import dispatch
from core.engine.pm.risk_assessor import assess_risk

logger = logging.getLogger(__name__)

# Fields allowed in update_track to prevent injection
ALLOWED_TRACK_FIELDS = {"metadata", "stuck_since", "current_score", "target_score", "active_spec_id"}


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------


async def _action_transition(action: dict, context: dict, db_pool) -> dict:
    """Validate transition via state machine, update DB, emit event."""
    track = context.get("track", {})
    current_state = track.get("state", "unassessed")
    target_state = action["target_state"]
    track_id = track.get("id", "")

    # Validate via state machine
    machine = CapabilityLifecycleMachine(current_state)
    machine.transition(target_state)  # raises InvalidLifecycleTransition if bad

    # Build SET clauses
    now = datetime.now(timezone.utc).isoformat()
    set_clauses = [
        "state = $target_state",
        "updated_at = $now",
    ]

    # Increment attempt_count on entry to spec_pending
    if target_state == "spec_pending":
        set_clauses.append("attempt_count = attempt_count + 1")

    # Reset attempt_count when target is met
    if target_state == "met":
        set_clauses.append("attempt_count = 0")

    # Clear stuck_since on any forward transition
    set_clauses.append("stuck_since = NONE")

    set_str = ", ".join(set_clauses)

    async with db_pool.connection() as db:
        await db.query(
            f"UPDATE <record>$track_id SET {set_str}",
            {"track_id": track_id, "target_state": target_state, "now": now},
        )

    # Update context in-place so subsequent actions see new state
    track["state"] = target_state

    # Emit track_changed event
    await bus.emit(
        "conductor.track_changed",
        {
            "track_id": track_id,
            "old_state": current_state,
            "new_state": target_state,
            "product_id": context.get("payload", {}).get("product_id"),
        },
    )

    return {"new_state": target_state, "old_state": current_state}


async def _action_notify(action: dict, context: dict, db_pool) -> dict:
    """Send a tiered notification via the dispatcher."""
    tier = action.get("tier", "informational")
    category = action.get("category", "conductor")
    title_template = action.get("title_template", "")
    body_template = action.get("body_template", "")

    title = _interpolate(title_template, context)
    body = _interpolate(body_template, context) if body_template else None

    product_id = context.get("payload", {}).get("product_id", "")
    user_id = context.get("payload", {}).get("user_id", "")

    await dispatch(
        product_id=product_id,
        user_id=user_id,
        tier=tier,
        category=category,
        title=str(title),
        body=body,
        source_record=context.get("track", {}).get("id"),
    )

    return {"notified": True, "tier": tier, "title": title}


async def _action_emit_event(action: dict, context: dict, db_pool) -> dict:
    """Emit an event on the bus with merged payload."""
    event_name = action["event"]
    payload_merge = action.get("payload_merge", {})

    payload = {
        "product_id": context.get("payload", {}).get("product_id"),
        **payload_merge,
    }

    await bus.emit(event_name, payload)

    return {"emitted": event_name}


async def _action_escalate(action: dict, context: dict, db_pool) -> dict:
    """Mark track as stuck + send actionable notification."""
    track = context.get("track", {})
    track_id = track.get("id", "")
    now = datetime.now(timezone.utc).isoformat()

    # Set stuck_since on the track
    async with db_pool.connection() as db:
        await db.query(
            "UPDATE <record>$track_id SET stuck_since = $now",
            {"track_id": track_id, "now": now},
        )

    track["stuck_since"] = now

    title_template = action.get("title_template", "Track stuck: ${track.id}")
    title = str(_interpolate(title_template, context))

    product_id = context.get("payload", {}).get("product_id", "")
    user_id = context.get("payload", {}).get("user_id", "")

    await dispatch(
        product_id=product_id,
        user_id=user_id,
        tier="actionable",
        category=action.get("category", "conductor_escalation"),
        title=title,
        source_record=track_id,
    )

    return {"escalated": True, "stuck_since": now}


async def _action_update_track(action: dict, context: dict, db_pool) -> dict:
    """Update whitelisted fields on the track record."""
    track = context.get("track", {})
    track_id = track.get("id", "")
    raw_fields = action.get("fields", {})

    # Whitelist filter
    safe_fields = {k: v for k, v in raw_fields.items() if k in ALLOWED_TRACK_FIELDS}

    if not safe_fields:
        return {"updated": False, "fields": {}}

    # Build SET clauses using parameterized queries
    set_parts = []
    params = {"track_id": track_id}
    for key, value in safe_fields.items():
        param_name = f"f_{key}"
        set_parts.append(f"{key} = ${param_name}")
        params[param_name] = value

    set_str = ", ".join(set_parts)

    async with db_pool.connection() as db:
        await db.query(f"UPDATE <record>$track_id SET {set_str}", params)

    return {"updated": True, "fields": list(safe_fields.keys())}


async def _action_assess_risk(action: dict, context: dict, db_pool) -> dict:
    """Run risk assessment, emit gate_cleared or gate_pending."""
    track = context.get("track", {})
    spec = context.get("spec", {})
    capability = context.get("capability", {})

    risk_context = {
        "file_count": len(spec.get("estimated_files", [])),
        "disciplines": [track.get("dimension", "")],
        "complexity": spec.get("metadata", {}).get("complexity", "simple")
        if isinstance(spec.get("metadata"), dict)
        else "simple",
        "capability_count": 1,
    }

    result = assess_risk("work_item", risk_context)

    product_id = context.get("payload", {}).get("product_id", "")
    dimension = track.get("dimension", "")

    if result.get("auto_approve"):
        await bus.emit(
            "conductor.gate_cleared",
            {
                "track_id": track.get("id"),
                "spec_id": track.get("active_spec_id"),
                "risk": result,
                "product_id": product_id,
            },
        )
    else:
        # Needs human review
        await bus.emit(
            "conductor.gate_pending",
            {
                "track_id": track.get("id"),
                "spec_id": track.get("active_spec_id"),
                "risk": result,
                "product_id": product_id,
            },
        )

        # Notify about pending gate
        await dispatch(
            product_id=context.get("payload", {}).get("product_id", ""),
            user_id=context.get("payload", {}).get("user_id", ""),
            tier="actionable",
            category="risk_gate",
            title=f"Risk gate pending for {capability.get('slug', 'unknown')}: {result.get('reason', '')}",
            source_record=track.get("id"),
        )

    # Emit risk assessment result into capture pipeline
    if product_id:
        try:
            from core.engine.capture.service import capture_service
            from core.engine.capture.watchers import StreamEvent

            gate_status = "auto_approved" if result.get("auto_approve") else "requires_review"
            cap_slug = capability.get("slug", "unknown")
            content = (
                f"Risk gate [{gate_status}] for capability '{cap_slug}' ({dimension}): "
                f"{result.get('reason', '')}. "
                f"Score: {result.get('score', '?')}, Complexity: {risk_context['complexity']}"
            )
            await capture_service.emit(
                StreamEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="tool_result",
                    content=content,
                    session_id=str(track.get("id", "")),
                    metadata={
                        "product_id": product_id,
                        "source": "conductor_risk_gate",
                        "discipline_hint": dimension or "architecture",
                    },
                )
            )
        except Exception as exc:
            logger.debug("Capture emit failed for risk gate: %s", exc)

    return {"risk": result}


async def _action_generate_spec(action: dict, context: dict, db_pool) -> dict:
    """Generate a spec from a gap and link to track."""
    from core.engine.product.spec_generator import SpecGenerator

    track = context.get("track", {})
    gap = context.get("gap", {})
    capability = context.get("capability", {})
    product_id = context.get("payload", {}).get("product_id", "")

    generator = SpecGenerator(db_pool)
    spec = await generator.from_gap(
        gap=gap,
        capability_slug=capability.get("slug", ""),
        product_id=product_id,
    )

    spec_id = spec.get("id", "")

    # Link spec to track
    if spec_id:
        async with db_pool.connection() as db:
            await db.query(
                "UPDATE <record>$track_id SET active_spec_id = $spec_id",
                {"track_id": track.get("id", ""), "spec_id": spec_id},
            )
        track["active_spec_id"] = spec_id

    return {"spec_id": spec_id, "spec": spec}


async def _action_decompose_spec(action: dict, context: dict, db_pool) -> dict:
    """Decompose a spec into a DAG of work units."""
    from core.engine.product.smart_decompose import SmartDecomposer

    track = context.get("track", {})
    product_id = context.get("payload", {}).get("product_id", "")
    spec_id = track.get("active_spec_id", "")

    decomposer = SmartDecomposer(db_pool)
    plan = await decomposer.decompose(spec_id=spec_id, product_id=product_id)

    # Convert to dict for downstream consumers
    plan_dict = plan.to_dict()
    context["plan"] = plan_dict

    return {"plan": plan_dict}


async def _action_execute_plan(action: dict, context: dict, db_pool) -> dict:
    """Execute a decomposition plan via the agent orchestrator."""
    from core.engine.product.agent_orchestrator import AgentOrchestrator

    plan_dict = context.get("plan", {})
    product_id = context.get("payload", {}).get("product_id", "")

    orchestrator = AgentOrchestrator(db_pool)
    result = await orchestrator.execute_plan(plan_dict=plan_dict, product_id=product_id)

    return {"execution_result": result}


async def _action_verify_spec(action: dict, context: dict, db_pool) -> dict:
    """Verify completed work against spec acceptance criteria."""
    from core.engine.product.acceptance import AcceptanceVerifier

    track = context.get("track", {})
    product_id = context.get("payload", {}).get("product_id", "")
    spec_id = track.get("active_spec_id", "")

    verifier = AcceptanceVerifier(db_pool)
    result = await verifier.verify(spec_id=spec_id, product_id=product_id)

    return {"verification": result}


async def _action_reassess_quality(action: dict, context: dict, db_pool) -> dict:
    """Re-run gap analysis for a single capability x dimension."""
    track = context.get("track", {})
    capability = context.get("capability", {})
    dimension = track.get("dimension", "")
    slug = capability.get("slug", "")

    try:
        from core.engine.sentinel.engines.gap_analyzer import _batch_assess, _load_code_evidence

        async with db_pool.connection() as db:
            code_evidence = await _load_code_evidence(db, capability.get("file_glob", f"**/{slug}*"))

        # Minimal batch assess for single dim
        assessments = await _batch_assess(
            slug=slug,
            description=capability.get("description", slug),
            file_text=capability.get("file_glob", ""),
            code_evidence=code_evidence,
            disciplines=[dimension],
            practices_by_dim={},
        )

        new_score = assessments[0].get("score", 0.0) if assessments else None

        if new_score is not None:
            await bus.emit(
                "quality.score_changed",
                {
                    "capability_slug": slug,
                    "dimension": dimension,
                    "score": new_score,
                    "product_id": context.get("payload", {}).get("product_id"),
                },
            )

        return {"reassessed": True, "dimension": dimension, "score": new_score}

    except (ImportError, AttributeError) as exc:
        logger.warning("reassess_quality: gap_analyzer functions not available: %s", exc)
        return {"reassessed": False, "reason": str(exc)}


async def _action_wait_for_human(action: dict, context: dict, db_pool) -> dict:
    """Emit a gate_pending event to pause the track until human input."""
    track = context.get("track", {})

    await bus.emit(
        "conductor.gate_pending",
        {
            "track_id": track.get("id"),
            "reason": action.get("reason", "Human review required"),
            "product_id": context.get("payload", {}).get("product_id"),
        },
    )

    return {"waiting": True, "reason": action.get("reason", "Human review required")}


async def _action_run_rule(action: dict, context: dict, db_pool) -> dict:
    """Return rule_name for the conductor to handle (composition).

    The conductor interprets this result and re-evaluates the named rule.
    """
    rule_name = action.get("rule_name", "")
    return {"run_rule": rule_name}


async def _action_run_innovate(action: dict, context: dict, db_pool) -> dict:
    """Run innovation engine when all quality gaps are closed.

    Executes the four innovation modes (frontier, cross_domain, emerging_tech,
    compounding), then emits innovation.candidates_ready so downstream
    rules or notifications can surface the results.
    """
    from core.engine.events.bus import bus
    from core.engine.product.innovate import run_all_modes

    product_id = context.get("product_id") or context.get("payload", {}).get("product_id", "")
    modes = action.get("modes", ["cross_domain", "emerging_tech", "compounding"])

    try:
        result = await run_all_modes()
        await bus.emit(
            "innovation.candidates_ready",
            {
                "product_id": product_id,
                "candidate_count": result.get("total_count", 0),
                "top_impact": result.get("top_impact", 0.0),
                "modes_run": modes,
            },
        )
        return {
            "total_count": result.get("total_count", 0),
            "top_impact": result.get("top_impact", 0.0),
        }
    except Exception as exc:
        logger.warning("run_innovate action failed: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Action registry + dispatcher
# ---------------------------------------------------------------------------

_ACTION_REGISTRY: dict[str, Any] = {
    "transition": _action_transition,
    "notify": _action_notify,
    "emit_event": _action_emit_event,
    "escalate": _action_escalate,
    "update_track": _action_update_track,
    "assess_risk": _action_assess_risk,
    "generate_spec": _action_generate_spec,
    "decompose_spec": _action_decompose_spec,
    "execute_plan": _action_execute_plan,
    "verify_spec": _action_verify_spec,
    "reassess_quality": _action_reassess_quality,
    "wait_for_human": _action_wait_for_human,
    "run_rule": _action_run_rule,
    "run_innovate": _action_run_innovate,
}


async def execute_action(action: dict, context: dict, db_pool) -> dict:
    """Dispatch a single action by type.

    Args:
        action: Action dict with at least {"type": "..."} plus type-specific fields.
        context: Shared context dict (track, payload, capability, spec, etc).
        db_pool: Database connection pool.

    Returns:
        Result dict from the executor.

    Raises:
        ValueError: If action type is not in the registry.
    """
    action_type = action.get("type", "")
    executor = _ACTION_REGISTRY.get(action_type)

    if executor is None:
        raise ValueError(f"Unknown action type: {action_type!r}")

    logger.debug("Executing action: %s", action_type)
    result = await executor(action, context, db_pool)
    logger.debug("Action %s completed: %s", action_type, result)
    return result

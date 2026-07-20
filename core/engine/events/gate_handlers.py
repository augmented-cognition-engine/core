"""Event handlers for gate lifecycle events."""

from __future__ import annotations

import logging

from core.engine.notifications.dispatcher import dispatch

logger = logging.getLogger(__name__)


async def on_gate_pending(event_type: str, payload: dict) -> None:
    """Notify PM that a gate is waiting for review."""
    try:
        entity_type = payload.get("entity_type", "entity")
        gate_state = payload.get("gate_state", "review")
        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="actionable",
            category="gate_pending",
            title=f"Review needed: {entity_type} {gate_state}",
            body=f"{entity_type} {payload.get('entity_id', '?')} is waiting for {gate_state} approval.",
            link="/gates",
        )
    except Exception as exc:
        logger.warning("on_gate_pending handler failed: %s", exc)


async def on_gate_approved(event_type: str, payload: dict) -> None:
    """Confirm gate approval."""
    try:
        entity_type = payload.get("entity_type", "entity")
        gate_state = payload.get("gate_state", "review")
        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="informational",
            category="gate_approved",
            title=f"Gate approved: {entity_type} {gate_state}",
            body=f"{entity_type} {payload.get('entity_id', '?')} passed {gate_state}.",
        )
    except Exception as exc:
        logger.warning("on_gate_approved handler failed: %s", exc)


async def on_gate_rejected(event_type: str, payload: dict) -> None:
    """Notify that a gate was rejected."""
    try:
        entity_type = payload.get("entity_type", "entity")
        gate_state = payload.get("gate_state", "review")
        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="actionable",
            category="gate_rejected",
            title=f"Gate rejected: {entity_type} {gate_state}",
            body=f"Reason: {payload.get('reason', 'No reason given')}",
            link="/gates",
        )
    except Exception as exc:
        logger.warning("on_gate_rejected handler failed: %s", exc)


async def on_gate_auto_approved(event_type: str, payload: dict) -> None:
    """Log auto-approval (silent notification tier)."""
    try:
        entity_type = payload.get("entity_type", "entity")
        gate_state = payload.get("gate_state", "review")
        risk_level = payload.get("risk_level", "low")
        await dispatch(
            product_id=payload.get("product_id", ""),
            user_id="user:default",
            tier="silent",
            category="gate_auto_approved",
            title=f"Auto-approved: {entity_type} {gate_state} ({risk_level} risk)",
            body=f"{entity_type} {payload.get('entity_id', '?')} auto-approved.",
        )
    except Exception as exc:
        logger.warning("on_gate_auto_approved handler failed: %s", exc)

"""Gate engine — centralized quality gate evaluation for all lifecycle transitions.

Every state transition that involves a review gate goes through here. The engine:
1. Loads entity context (files, disciplines, complexity)
2. Runs risk assessment (pure scoring)
3. Auto-approves low-risk or queues for human review
4. On approval/rejection: creates decision record + edges, transitions entity, emits events
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_one, parse_rows
from core.engine.events.bus import bus
from core.engine.pm.risk_assessor import assess_risk
from core.engine.product.decisions import create_decision

logger = logging.getLogger(__name__)

# Gate state -> approval target state
_APPROVAL_TARGETS: dict[str, dict[str, str]] = {
    "idea": {
        "spec_review": "planned",
        "plan_review": "promoted",
    },
    "initiative": {
        "review": "completed",
    },
    "milestone": {
        "review": "approved",
    },
    "work_item": {
        "review": "completed",
    },
}

# Gate state -> rejection target state
_REJECTION_TARGETS: dict[str, dict[str, str]] = {
    "idea": {
        "spec_review": "ready",
        "plan_review": "planned",
    },
    "initiative": {
        "review": "active",
    },
    "milestone": {
        "review": "active",
    },
    "work_item": {
        "review": "running",
    },
}

# Gate state -> decision type
_GATE_DECISION_TYPES: dict[str, str] = {
    "spec_review": "architecture",
    "plan_review": "prioritization",
    "review": "trade_off",
}

# Which statuses represent a pending gate, per entity table
_PENDING_STATUSES: dict[str, list[str]] = {
    "idea": ["spec_review", "plan_review"],
    "initiative": ["review"],
    "milestone": ["review"],
    "work_item": ["review"],
}


class GateEngine:
    """Evaluate, approve, and reject quality gates across all entity types."""

    def __init__(self, db_pool):
        self._pool = db_pool

    async def evaluate_gate(
        self,
        entity_type: str,
        entity_id: str,
        from_state: str,
        to_state: str,
        product_id: str,
    ) -> dict:
        """Evaluate whether a transition should be auto-approved or needs review."""
        context = await self._load_entity_context(entity_type, entity_id, product_id)
        result = assess_risk(entity_type, context)
        return result

    async def approve_gate(
        self,
        entity_type: str,
        entity_id: str,
        gate_state: str,
        rationale: str,
        product_id: str,
        user_id: str,
    ) -> dict:
        """PM approves a gate. Creates decision, transitions entity, emits event."""
        target_state = _APPROVAL_TARGETS.get(entity_type, {}).get(gate_state)
        if not target_state:
            return {"error": f"No approval target for {entity_type}.{gate_state}"}

        decision_type = _GATE_DECISION_TYPES.get(gate_state, "trade_off")

        decision = await create_decision(
            title=f"Gate approved: {entity_type} {gate_state}",
            decision_type=decision_type,
            rationale=rationale,
            product_id=product_id,
            source="gate_review",
            led_to_ids=[entity_id],
            pool=self._pool,
        )

        entity = await self._transition_entity(entity_type, entity_id, target_state, product_id)

        await bus.emit(
            "gate.approved",
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "gate_state": gate_state,
                "decision_id": str(decision.get("id", "")),
                "product_id": product_id,
            },
        )

        return {"decision": decision, "entity": entity}

    async def reject_gate(
        self,
        entity_type: str,
        entity_id: str,
        gate_state: str,
        reason: str,
        product_id: str,
        user_id: str,
    ) -> dict:
        """PM rejects a gate. Creates rejection decision, transitions entity back."""
        target_state = _REJECTION_TARGETS.get(entity_type, {}).get(gate_state)
        if not target_state:
            return {"error": f"No rejection target for {entity_type}.{gate_state}"}

        decision = await create_decision(
            title=f"Gate rejected: {entity_type} {gate_state}",
            decision_type="rejection",
            rationale=reason,
            product_id=product_id,
            source="gate_review",
            led_to_ids=[entity_id],
            pool=self._pool,
        )

        entity = await self._transition_entity(entity_type, entity_id, target_state, product_id)

        await bus.emit(
            "gate.rejected",
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "gate_state": gate_state,
                "decision_id": str(decision.get("id", "")),
                "reason": reason,
                "product_id": product_id,
            },
        )

        return {"decision": decision, "entity": entity}

    async def auto_approve_gate(
        self,
        entity_type: str,
        entity_id: str,
        gate_state: str,
        risk_result: dict,
        product_id: str,
    ) -> dict:
        """System auto-approves a low-risk gate."""
        target_state = _APPROVAL_TARGETS.get(entity_type, {}).get(gate_state)
        if not target_state:
            return {"error": f"No approval target for {entity_type}.{gate_state}"}

        decision = await create_decision(
            title=f"Gate auto-approved: {entity_type} {gate_state}",
            decision_type=_GATE_DECISION_TYPES.get(gate_state, "trade_off"),
            rationale=risk_result.get("reason", "Auto-approved: low risk"),
            product_id=product_id,
            source="auto_gate",
            led_to_ids=[entity_id],
            pool=self._pool,
        )

        entity = await self._transition_entity(entity_type, entity_id, target_state, product_id)

        await bus.emit(
            "gate.auto_approved",
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "gate_state": gate_state,
                "decision_id": str(decision.get("id", "")),
                "risk_level": risk_result.get("risk_level", "low"),
                "product_id": product_id,
            },
        )

        return {"decision": decision, "entity": entity}

    async def list_pending(self, product_id: str) -> list[dict]:
        """List all entities waiting for human review, including risk assessment."""
        pending = []
        async with self._pool.connection() as db:
            for table, statuses in _PENDING_STATUSES.items():
                for status in statuses:
                    result = await db.query(
                        f"SELECT * FROM {table} WHERE product = <record>$product AND status = <string>$status ORDER BY created_at",
                        {"product": product_id, "status": status},
                    )
                    for row in parse_rows(result):
                        entity_id = str(row.get("id", ""))
                        context = await self._load_entity_context(table, entity_id, product_id)
                        risk = assess_risk(table, context)
                        pending.append(
                            {
                                "entity_type": table,
                                "entity_id": entity_id,
                                "gate_state": status,
                                "title": row.get("title", ""),
                                "created_at": str(row.get("created_at", "")),
                                "risk_level": risk.get("risk_level", "low"),
                                "risk_factors": risk.get("risk_factors", []),
                                "risk_reason": risk.get("reason", ""),
                            }
                        )
        return pending

    async def _load_entity_context(self, entity_type: str, entity_id: str, product_id: str) -> dict:
        """Load context for risk assessment."""
        context: dict = {"complexity": "simple", "disciplines": [], "file_count": 0}
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    "SELECT * FROM <record>$id",
                    {"id": entity_id},
                )
                entity = parse_one(result)
                if not entity:
                    return context
                context["entity"] = entity

                classification = entity.get("classification", {}) or {}
                context["complexity"] = classification.get("complexity", entity.get("complexity", "simple"))

                disciplines = []
                if classification.get("discipline"):
                    disciplines.append(classification["discipline"])
                spec_id = entity.get("spec_id") or entity.get("capability")
                if spec_id:
                    spec_result = await db.query("SELECT * FROM <record>$id", {"id": str(spec_id)})
                    spec = parse_one(spec_result)
                    if spec:
                        for f in spec.get("estimated_files", []):
                            context["file_count"] += 1
                        for d in spec.get("disciplines", []):
                            if d not in disciplines:
                                disciplines.append(d)
                context["disciplines"] = disciplines
        except Exception as exc:
            logger.debug("Failed to load entity context: %s", exc)

        return context

    async def _transition_entity(self, entity_type: str, entity_id: str, target_state: str, product_id: str) -> dict:
        """Transition an entity to a new state in the DB."""
        timestamp_field = {
            "planned": "planned_at",
            "promoted": "activated_at",
            "completed": "completed_at",
            "cancelled": "completed_at",
            "ready": "ready_at",
            "active": None,
            "approved": "completed_at",
            "blocked": "blocked_at",
            "completing": "completing_at",
            "decomposing": "decomposed_at",
            "review": "reviewed_at",
            "speccing": "speccing_at",
            "spec_review": "spec_review_at",
            "plan_review": "plan_review_at",
        }.get(target_state)

        timestamp_clause = f", {timestamp_field} = time::now()" if timestamp_field else ""

        async with self._pool.connection() as db:
            result = await db.query(
                f"UPDATE <record>$id SET status = <string>$status{timestamp_clause}",
                {"id": entity_id, "status": target_state},
            )
            return parse_one(result) or {"id": entity_id, "status": target_state}

# engine/pm/approvals.py
"""Milestone approval gates, human handoff workflows, and blocker escalation.

Milestones with requires_approval=true pause execution until a human approves.
Work items with requires_human=true create handoff context packages.
Blocker runtime_events → human escalation (reflective replanning is deferred).

Escalation timers: remind after 24h, escalate after 72h.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

REMIND_AFTER_HOURS = 24
ESCALATE_AFTER_HOURS = 72


def check_escalation(
    requested_at: datetime,
    now: datetime | None = None,
) -> str | None:
    """Check if an approval request needs escalation.

    Returns: None (no action), 'remind' (24h), or 'escalate' (72h).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    elapsed = now - requested_at
    hours = elapsed.total_seconds() / 3600

    if hours >= ESCALATE_AFTER_HOURS:
        return "escalate"
    elif hours >= REMIND_AFTER_HOURS:
        return "remind"
    return None


class ApprovalManager:
    """Manage milestone approvals, handoffs, and blocker escalation."""

    def __init__(self, db_pool=None):
        self._db_pool = db_pool

    def _pool(self):
        if self._db_pool:
            return self._db_pool
        from core.engine.core.db import pool

        return pool

    async def request_approval(
        self,
        milestone_id: str,
        product_id: str,
    ) -> dict:
        """Pause a milestone and request approval from the designated approver."""
        async with self._pool().connection() as db:
            result = await db.query(
                "SELECT * FROM $ms_id",
                {"ms_id": milestone_id},
            )
            rows = result[0] if result and isinstance(result[0], list) else (result or [])
            ms = rows[0] if rows else {}

            await db.query(
                """
                UPDATE <record>$ms_id SET
                    status = 'review',
                    review_requested_at = time::now()
                """,
                {"ms_id": milestone_id},
            )

            logger.info("Approval requested for milestone %s by approver %s", milestone_id, ms.get("approver"))

            return {
                "status": "awaiting_approval",
                "milestone_id": milestone_id,
                "approver": ms.get("approver"),
                "title": ms.get("title"),
            }

    async def approve_milestone(
        self,
        milestone_id: str,
        approver_id: str,
        product_id: str,
    ) -> dict:
        """Approve a milestone. Triggers next milestone decomposition."""
        async with self._pool().connection() as db:
            await db.query(
                """
                UPDATE <record>$ms_id SET
                    status = 'approved',
                    approved_by = <record>$approver,
                    approved_at = time::now()
                """,
                {"ms_id": milestone_id, "approver": approver_id},
            )

            logger.info("Milestone %s approved by %s", milestone_id, approver_id)

            return {
                "action": "approved",
                "milestone_id": milestone_id,
                "approver": approver_id,
            }

    async def reject_milestone(
        self,
        milestone_id: str,
        rejector_id: str,
        feedback: str,
        product_id: str,
    ) -> dict:
        """Reject a milestone with feedback. Returns to previous work state."""
        async with self._pool().connection() as db:
            await db.query(
                """
                UPDATE <record>$ms_id SET
                    status = 'active',
                    rejection_feedback = $feedback,
                    rejected_by = <record>$rejector,
                    rejected_at = time::now()
                """,
                {"ms_id": milestone_id, "feedback": feedback, "rejector": rejector_id},
            )

            logger.info("Milestone %s rejected by %s: %s", milestone_id, rejector_id, feedback[:100])

            return {
                "action": "rejected",
                "milestone_id": milestone_id,
                "feedback": feedback,
            }

    async def create_handoff(
        self,
        work_item_id: str,
        assigned_to: str,
        product_id: str,
    ) -> dict:
        """Create a human handoff context package for a requires_human work item."""
        async with self._pool().connection() as db:
            result = await db.query(
                "SELECT * FROM $wi_id",
                {"wi_id": work_item_id},
            )
            rows = result[0] if result and isinstance(result[0], list) else (result or [])
            wi = rows[0] if rows else {}

            # Update work item with handoff info
            await db.query(
                """
                UPDATE <record>$wi_id SET
                    status = 'blocked',
                    assigned_to = <record>$assigned,
                    handoff_created_at = time::now()
                """,
                {"wi_id": work_item_id, "assigned": assigned_to},
            )

            context = {
                "work_item": wi,
                "description": wi.get("description", ""),
                "domain_path": wi.get("domain_path", ""),
            }

            logger.info("Handoff created for %s → %s", work_item_id, assigned_to)

            return {
                "type": "handoff",
                "work_item_id": work_item_id,
                "assigned_to": assigned_to,
                "context": context,
            }

    async def escalate_blocker(
        self,
        work_item_id: str,
        reason: str,
        product_id: str,
    ) -> dict:
        """Escalate a blocker to human attention.

        In Phase 5a, blockers → human escalation.
        Reflective replanning is a follow-up.
        """
        async with self._pool().connection() as db:
            await db.query(
                """
                UPDATE <record>$wi_id SET
                    status = 'blocked',
                    blocker_reason = $reason,
                    blocked_at = time::now()
                """,
                {"wi_id": work_item_id, "reason": reason},
            )

            logger.info("Blocker escalation for %s: %s", work_item_id, reason[:100])

            return {
                "type": "blocker_escalation",
                "work_item_id": work_item_id,
                "reason": reason,
            }

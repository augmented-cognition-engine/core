"""Feedback Handler — PM's automatic responses to agent feedback.

6 feedback types, each with specific handling logic:
- blocker: research alternatives, replan if critical
- discovery: update product map with new information
- trade_off: decide based on direction + priorities
- scope_question: clarify from spec + product map + best practices
- completion: trigger acceptance verification
- progress: update tracking, no action needed
"""

import logging

from core.engine.core.db import parse_one
from core.engine.product.spec_models import AgentFeedbackCreate

logger = logging.getLogger(__name__)


class FeedbackHandler:
    """Process structured feedback from agent-engineers."""

    def __init__(self, db_pool):
        self._pool = db_pool

    async def handle(self, feedback: AgentFeedbackCreate, product_id: str) -> dict:
        """Route feedback to the appropriate handler.

        Persists the feedback, then processes based on type.
        Returns action taken.
        """
        # Persist feedback
        async with self._pool.connection() as db:
            result = await db.query(
                """CREATE agent_feedback SET
                    product = <record>$product,
                    spec = <record>$spec_id,
                    work_unit = $work_unit,
                    feedback_type = $feedback_type,
                    content = $content,
                    context = $context,
                    resolved = false""",
                {
                    "product": product_id,
                    "spec_id": feedback.spec_id,
                    "work_unit": feedback.work_unit,
                    "feedback_type": feedback.feedback_type,
                    "content": feedback.content,
                    "context": feedback.context,
                },
            )
            fb_record = parse_one(result)
            fb_id = str(fb_record["id"]) if fb_record else None

        # Route to handler
        handler_map = {
            "blocker": self._handle_blocker,
            "discovery": self._handle_discovery,
            "trade_off": self._handle_trade_off,
            "scope_question": self._handle_scope_question,
            "completion": self._handle_completion,
            "progress": self._handle_progress,
        }

        handler = handler_map.get(feedback.feedback_type, self._handle_progress)
        action = await handler(feedback, product_id)

        # Feed composition scorer: map feedback types to quality signals
        await self._write_composition_signal(feedback, product_id)

        return {
            "feedback_id": fb_id,
            "feedback_type": feedback.feedback_type,
            "action": action,
        }

    async def _handle_blocker(self, feedback: AgentFeedbackCreate, product_id: str) -> dict:
        """Agent is stuck. Log the blocker and flag for PM attention.

        Future: research alternatives, attempt replan.
        For now: persist and flag as needing human/PM review.
        """
        logger.warning(f"Agent blocker on spec {feedback.spec_id}: {feedback.content}")

        # Create a product question about the blocker
        async with self._pool.connection() as db:
            await db.query(
                """CREATE product_question SET
                    product = <record>$product,
                    question = $question,
                    category = 'inward',
                    source = 'agent',
                    priority = 'critical',
                    status = 'open'""",
                {
                    "product": product_id,
                    "question": f"Agent blocker: {feedback.content}",
                    "priority": "critical",
                },
            )

        return {"action": "blocker_flagged", "escalated": True}

    async def _handle_discovery(self, feedback: AgentFeedbackCreate, product_id: str) -> dict:
        """Agent found something new. Update product intelligence.

        Discoveries feed the intelligence pipeline as observations.
        """
        logger.info(f"Agent discovery on spec {feedback.spec_id}: {feedback.content}")

        # Persist as an observation in the capture pipeline
        async with self._pool.connection() as db:
            await db.query(
                """CREATE observation SET
                    product = <record>$product,
                    content = $content,
                    observation_type = 'learning',
                    source = 'agent_discovery',
                    confidence = 0.7,
                    created_at = time::now()""",
                {
                    "product": product_id,
                    "content": feedback.content,
                },
            )

        return {"action": "discovery_captured", "fed_to_intelligence": True}

    async def _handle_trade_off(self, feedback: AgentFeedbackCreate, product_id: str) -> dict:
        """Agent presents a trade-off decision.

        Future: PM reasons about it using direction + priorities.
        For now: flag for human review.
        """
        logger.info(f"Agent trade-off on spec {feedback.spec_id}: {feedback.content}")

        async with self._pool.connection() as db:
            await db.query(
                """CREATE product_question SET
                    product = <record>$product,
                    question = $question,
                    category = 'forward',
                    source = 'agent',
                    priority = 'high',
                    status = 'open'""",
                {
                    "product": product_id,
                    "question": f"Trade-off decision needed: {feedback.content}",
                    "priority": "high",
                },
            )

        return {"action": "trade_off_escalated", "needs_decision": True}

    async def _handle_scope_question(self, feedback: AgentFeedbackCreate, product_id: str) -> dict:
        """Agent needs clarification on scope.

        Future: check spec + product map + best practices to answer automatically.
        For now: flag for human clarification.
        """
        logger.info(f"Agent scope question on spec {feedback.spec_id}: {feedback.content}")

        async with self._pool.connection() as db:
            await db.query(
                """CREATE product_question SET
                    product = <record>$product,
                    question = $question,
                    category = 'inward',
                    source = 'agent',
                    priority = 'high',
                    status = 'open'""",
                {
                    "product": product_id,
                    "question": f"Scope clarification needed: {feedback.content}",
                    "priority": "high",
                },
            )

        return {"action": "scope_question_escalated", "needs_clarification": True}

    async def _handle_completion(self, feedback: AgentFeedbackCreate, product_id: str) -> dict:
        """Agent reports work is done. Trigger acceptance verification.

        Updates spec status to 'verifying' and queues verification.
        """
        logger.info(f"Agent completed spec {feedback.spec_id}")

        async with self._pool.connection() as db:
            await db.query(
                "UPDATE <record>$spec_id SET status = 'verifying', updated_at = time::now()",
                {"spec_id": feedback.spec_id},
            )

        return {"action": "completion_received", "verification_queued": True}

    async def _handle_progress(self, feedback: AgentFeedbackCreate, product_id: str) -> dict:
        """Agent reports progress. No action needed — just logged."""
        logger.info(f"Agent progress on spec {feedback.spec_id}: {feedback.content}")
        return {"action": "progress_noted"}

    async def _write_composition_signal(self, feedback: AgentFeedbackCreate, product_id: str) -> None:
        """Write a composition_signal so the scorer has fresh data from agent feedback.

        Maps feedback types to equivalent human-feedback signals:
        - completion → 'accepted' (work finished successfully)
        - blocker → 'rejected' (work could not proceed)
        - Others → no signal (neutral, doesn't affect scorer weights)
        """
        signal_map = {
            "completion": "accepted",
            "blocker": "rejected",
        }
        feedback_value = signal_map.get(feedback.feedback_type)
        if not feedback_value:
            return

        try:
            async with self._pool.connection() as db:
                await db.query(
                    """CREATE composition_signal SET
                        product = <record>$product,
                        feedback = $feedback,
                        source = 'agent_feedback',
                        spec_id = <record>$spec_id,
                        created_at = time::now()""",
                    {
                        "product": product_id,
                        "feedback": feedback_value,
                        "spec_id": feedback.spec_id,
                    },
                )
        except Exception as exc:
            logger.warning("Failed to write composition_signal from feedback: %s", exc)

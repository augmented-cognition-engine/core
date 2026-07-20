"""FailureCategory enum + FailureClassifier for capturing reasoning loop failures.

This module provides structured failure classification for the Token Intelligence
& Adaptive Reasoning Loop system. It captures failures in a way that feeds the
intelligence pipeline, enabling the system to learn from its own errors.
"""

from __future__ import annotations

import json
import logging
from enum import Enum

from core.engine.core.db import pool

logger = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """Enumeration of failure categories in the reasoning loop."""

    MISSING_EDGE_CASE = "missing_edge_case"
    INCOMPLETE_IMPL = "incomplete_implementation"
    LOGIC_ERROR = "logic_error"
    OFF_SPEC = "off_spec"
    SECURITY_GAP = "security_gap"
    MISSING_ERROR_HANDLING = "missing_error_handling"
    CONTEXT_LOSS = "context_loss"
    OVERCOMPLICATED = "overcomplicated"
    OTHER = "other"


class FailureClassifier:
    """Captures and records reasoning loop failures to the intelligence graph.

    This classifier writes observations to SurrealDB that feed the intelligence
    pipeline. Failures are marked as corrections so they surface in briefings
    and help the system improve future reasoning.

    Non-fatal — database errors are logged but don't crash the caller.
    """

    def __init__(self, product_id: str = "product:platform") -> None:
        """Initialize the classifier with an optional product scope.

        Args:
            product_id: SurrealDB record ID for the product (default: "product:platform")
        """
        self._product_id = product_id

    async def capture(
        self,
        discipline: str,
        task_type: str,
        category: FailureCategory,
        issues: list[str],
        other_text: str = "",
        product_id: str | None = None,
    ) -> None:
        """Capture a reasoning loop failure.

        Writes an observation record to the intelligence graph with the failure
        category, discipline, task type, and specific issues.

        Args:
            discipline: Domain (e.g., "coding", "api_design", "testing")
            task_type: Type of task (e.g., "implementation", "review")
            category: FailureCategory enum value
            issues: List of specific issues that caused the failure
            other_text: Additional detail (used when category == OTHER)
            product_id: Override the default product_id for this capture

        Non-fatal — logs exceptions and continues.
        """
        effective_product_id = product_id or self._product_id
        try:
            parts = [
                f"Reasoning loop failure [{category.value}] in {discipline}/{task_type}.",
                f"Issues: {json.dumps(issues)}",
            ]
            if category == FailureCategory.OTHER and other_text:
                parts.append(f"Detail: {other_text}")
            content = " ".join(parts)

            async with pool.connection() as db:
                await db.query(
                    """
                    CREATE observation SET
                        product = <record>$product,
                        observation_type = $type,
                        content = $content,
                        domain_path = $domain_path,
                        discipline_hint = $domain_path,
                        confidence = $confidence,
                        source = 'reasoning_loop',
                        status = 'pending',
                        created_at = time::now()
                """,
                    {
                        "product": effective_product_id,
                        "type": "correction",
                        "content": content,
                        "domain_path": discipline,
                        "confidence": 0.85,
                    },
                )
        except Exception:
            logger.exception("FailureClassifier.capture failed (non-fatal)")

    async def capture_opus_success(
        self,
        discipline: str,
        task_type: str,
        sonnet_output: str,
        opus_output: str,
        product_id: str | None = None,
    ) -> None:
        """Capture when Opus succeeds where Sonnet failed (complexity signal).

        This writes a learning observation indicating that the task requires
        more sophisticated reasoning. The intelligence pipeline uses this to
        route similar future tasks to the COMPLEX tier.

        Args:
            discipline: Domain (e.g., "coding", "api_design")
            task_type: Type of task (e.g., "implementation")
            sonnet_output: Output from Sonnet attempt (usually shorter)
            opus_output: Output from Opus attempt (usually longer/more complete)
            product_id: Override the default product_id for this capture

        Non-fatal — logs exceptions and continues.
        """
        effective_product_id = product_id or self._product_id
        try:
            content = (
                f"complexity_signal: Opus succeeded where Sonnet failed in "
                f"{discipline}/{task_type}. Sonnet output length: {len(sonnet_output)}, "
                f"Opus output length: {len(opus_output)}. Route similar tasks to COMPLEX tier."
            )

            async with pool.connection() as db:
                await db.query(
                    """
                    CREATE observation SET
                        product = <record>$product,
                        observation_type = $type,
                        content = $content,
                        domain_path = $domain_path,
                        discipline_hint = $domain_path,
                        confidence = $confidence,
                        source = 'reasoning_loop',
                        status = 'pending',
                        created_at = time::now()
                """,
                    {
                        "product": effective_product_id,
                        "type": "correction",
                        "content": content,
                        "domain_path": discipline,
                        "confidence": 0.9,
                    },
                )
        except Exception:
            logger.exception("FailureClassifier.capture_opus_success failed (non-fatal)")

# engine/product/question_engine.py
import logging
from datetime import datetime, timedelta

from core.engine.core.db import parse_rows
from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class QuestionEngine:
    """Generate and manage product questions across 5 categories."""

    def __init__(self, db_pool):
        self._pool = db_pool

    def _validate_product_id(self, product_id: str) -> None:
        """Validate product_id format before running question generation queries.

        Raises ValidationError for empty or malformed product IDs so callers get
        a clear error rather than a confusing DB query failure.
        """
        if not product_id or ":" not in product_id:
            raise ValidationError(f"Invalid product_id: {product_id!r}")

    async def generate_questions(self, product_id: str) -> list[dict]:
        """Generate questions from all sources. Called by overnight engine.

        Raises ValidationError if product_id is malformed.
        """
        self._validate_product_id(product_id)
        questions = []
        for name, coro in [
            ("inward", self._inward_questions(product_id)),
            ("downward", self._downward_questions(product_id)),
            ("temporal", self._temporal_questions(product_id)),
        ]:
            try:
                batch = await coro
                logger.debug("Question source %r produced %d questions for %s", name, len(batch), product_id)
                questions += batch
            except Exception as exc:
                logger.warning("Question source %r failed for %s: %s", name, product_id, exc)
        # outward and forward are placeholders for now
        result = self._deduplicate_and_prioritize(questions)
        logger.info("Generated %d questions for product=%s", len(result), product_id)
        return result

    async def _inward_questions(self, product_id: str) -> list[dict]:
        """Files with high change frequency but no capability mapping."""
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT path, change_frequency FROM graph_file
                WHERE graph_id = 'default'
                AND id NOT IN (SELECT in FROM realizes)
                AND change_frequency > 5
                ORDER BY change_frequency DESC LIMIT 10""",
                {},
            )
            orphans = parse_rows(result)

        questions = []
        for f in orphans:
            questions.append(
                {
                    "question": f"Unmapped file '{f['path']}' has high change frequency ({f.get('change_frequency', 0)}). What capability does it belong to?",
                    "category": "inward",
                    "source": "question_engine",
                    "priority": "medium",
                }
            )
        return questions

    async def _downward_questions(self, product_id: str) -> list[dict]:
        """Capabilities with low quality scores."""
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT capability, dimension, score, gaps
                   FROM capability_quality
                   WHERE product = <record>$product
                     AND score < 0.5
                   ORDER BY score ASC
                   LIMIT 20""",
                {"product": product_id},
            )
            low_quality = parse_rows(result)

        questions = []
        for q in low_quality:
            gaps = q.get("gaps", [])
            gap_text = gaps[0] if gaps else f"low {q.get('dimension', '?')} score ({q.get('score', 0):.1f})"
            questions.append(
                {
                    "question": f"Quality gap: {gap_text}",
                    "category": "downward",
                    "source": "question_engine",
                    "capability_id": str(q.get("capability", "")),
                    "priority": "high" if q.get("score", 1) < 0.2 else "medium",
                }
            )
        return questions

    async def _temporal_questions(self, product_id: str) -> list[dict]:
        """Capabilities with stale decisions (older than 90 days)."""
        async with self._pool.connection() as db:
            result = await db.query(
                "SELECT * FROM capability WHERE product = <record>$product AND intent IS NOT NONE",
                {"product": product_id},
            )
            capabilities = parse_rows(result)

        questions = []
        cutoff = datetime.now() - timedelta(days=90)
        for cap in capabilities:
            intent = cap.get("intent", {})
            decisions = intent.get("decisions", []) if intent else []
            for d in decisions:
                decision_date = d.get("date", "")
                try:
                    dt = datetime.fromisoformat(decision_date)
                    if dt < cutoff:
                        questions.append(
                            {
                                "question": f"Decision '{d.get('decision', '?')}' in {cap.get('slug', '?')} is {(datetime.now() - dt).days} days old. Still valid?",
                                "category": "temporal",
                                "source": "question_engine",
                                "capability_id": str(cap.get("id", "")),
                                "priority": "medium",
                            }
                        )
                except (ValueError, TypeError):
                    pass
        return questions

    async def _outward_questions(self, product_id: str) -> list[dict]:
        """Placeholder — will be populated by research agent integration."""
        return []

    async def _forward_questions(self, product_id: str) -> list[dict]:
        """Placeholder — requires product direction to be set."""
        return []

    def _deduplicate_and_prioritize(self, questions: list[dict]) -> list[dict]:
        """Remove duplicates (by question text), keep highest priority version."""
        seen = {}
        for q in questions:
            key = q["question"]
            if key not in seen or PRIORITY_ORDER.get(q["priority"], 3) < PRIORITY_ORDER.get(seen[key]["priority"], 3):
                seen[key] = q
        result = list(seen.values())
        result.sort(key=lambda q: PRIORITY_ORDER.get(q["priority"], 3))
        return result

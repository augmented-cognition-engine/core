# engine/sentinel/engines/question_generator.py
"""Question Generator — generate product-level questions nightly."""

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.product.question_engine import QuestionEngine
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


def _validate_question_generator_inputs(product_id: str, budget: int = 100) -> None:
    """Validate question generator inputs before running QuestionEngine.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the nightly question generation job fails fast with a clear error.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for question generator: {product_id!r}")
    if not (1 <= budget <= 500):
        raise ValidationError(f"budget must be in [1, 500], got {budget}")


@register_engine(
    name="question_generator",
    cron="15 3 * * *",
    description="Generate product questions from all 5 categories. Runs after gap analyzer.",
)
async def run_question_generator(product_id: str, budget: int = 50) -> dict:
    """Generate and persist product questions."""
    _validate_question_generator_inputs(product_id, budget)
    qe = QuestionEngine(pool)
    questions = await qe.generate_questions(product_id)

    created = 0
    async with pool.connection() as db:
        for q in questions[:budget]:
            # Skip if similar question already open
            existing = await db.query(
                "SELECT id FROM product_question WHERE product = <record>$product AND question = $question AND status IN ['open', 'researching']",
                {"product": product_id, "question": q["question"]},
            )
            if parse_rows(existing):
                continue

            await db.query(
                """CREATE product_question SET
                    category = $category, source = $source,
                    capability = $capability,
                    priority = $priority, status = 'open'""",
                {
                    "product": product_id,
                    "question": q["question"],
                    "category": q["category"],
                    "source": q.get("source", "question_engine"),
                    "capability": q.get("capability_id"),
                    "priority": q.get("priority", "medium"),
                },
            )
            created += 1

    return {"generated": len(questions), "created": created, "deduplicated": len(questions) - created}

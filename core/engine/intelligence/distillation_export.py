"""Distillation corpus export — STaR traces → fine-tune-ready JSONL.

ACE's STaR table captures reasoning traces that passed VerificationGate.
This module emits them as OpenAI-style prompt/completion JSONL suitable for
fine-tuning a smaller model on a team's accumulated reasoning patterns.

Downstream consumer: run through Anthropic batch API, OpenAI fine-tune CLI,
HuggingFace trl, etc. ACE doesn't do the training itself — it emits the data.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


async def export_distillation_jsonl(
    db,
    product_id: str,
    discipline: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 1000,
) -> str:
    """Return a JSONL string where each line is one training record.

    Args:
        db: SurrealDB connection (caller manages lifecycle)
        product_id: Scope to a single product
        discipline: Optional filter — omit to get every discipline's traces
        min_confidence: Filter out low-confidence traces (recommended ≥0.7 for training)
        limit: Max traces to include (default 1000 — keeps exports bounded)

    Returns:
        Newline-separated JSONL. Empty string on no data or any error.
    """
    try:
        from core.engine.core.db import parse_rows

        sql_parts = [
            "SELECT task_description, final_output, discipline, confidence",
            "FROM star_trace",
            "WHERE product = <record>$product",
        ]
        params: dict = {"product": product_id, "limit": limit, "min_confidence": min_confidence}
        if min_confidence > 0.0:
            sql_parts.append("AND (confidence >= $min_confidence OR confidence IS NONE)")
        if discipline:
            sql_parts.append("AND discipline = $discipline")
            params["discipline"] = discipline
        sql_parts.append("ORDER BY created_at DESC LIMIT $limit")

        rows = parse_rows(await db.query(" ".join(sql_parts), params))
        if not rows:
            return ""

        lines: list[str] = []
        for row in rows:
            prompt = (row.get("task_description") or "").strip()
            completion = (row.get("final_output") or "").strip()
            if not prompt or not completion:
                continue
            record = {
                "prompt": prompt,
                "completion": completion,
                "metadata": {
                    "discipline": row.get("discipline") or "",
                    "confidence": float(row.get("confidence") or 0.0),
                    "product_id": product_id,
                },
            }
            lines.append(json.dumps(record, ensure_ascii=False))
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("export_distillation_jsonl failed (non-fatal): %s", exc)
        return ""

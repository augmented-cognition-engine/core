"""REST API for webhook ingestion — generic external source intake."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter(tags=["webhooks"])


class WebhookPayload(BaseModel):
    source: str = Field(max_length=100)
    source_id: str | None = None
    content: str = Field(max_length=50_000)
    metadata: dict | None = None
    domain_hint: str | None = None
    timestamp: datetime | None = None


@router.post("/webhooks/ingest", status_code=202)
async def ingest_webhook(body: WebhookPayload, user=Depends(get_current_user)):
    """Ingest a webhook payload into the capture pipeline.

    Deduplicates on source + source_id. Routes content through
    the observation pipeline as a webhook_fragment memory record.
    """
    product_id = user.get("product", "")

    async with pool.connection() as db:
        # Dedup check
        if body.source_id:
            existing = await db.query(
                """
                SELECT id FROM memory
                WHERE product = <record>$product AND source = $source AND source_id = <string>$source_id
                LIMIT 1
                """,
                {"product": product_id, "source": body.source, "source_id": body.source_id},
            )
            rows = parse_rows(existing)
            if rows:
                return {"id": str(rows[0].get("id", "")), "status": "duplicate", "message": "Already ingested"}

        # Write to memory table
        result = await db.query(
            """
            CREATE memory SET
                product = <record>$product,
                type = 'webhook_fragment',
                source = $source,
                source_id = $source_id,
                content = $content,
                metadata = $metadata,
                domain_hint = $domain_hint,
                created_at = time::now()
            """,
            {
                "product": product_id,
                "source": body.source,
                "source_id": body.source_id,
                "content": body.content,
                "metadata": body.metadata,
                "domain_hint": body.domain_hint,
            },
        )
        record = parse_one(result)
        memory_id = str(record.get("id", "")) if record else ""

    # Fire-and-forget: observer will pick this up in next batch
    # (or we could trigger immediately — but batch is simpler for v1)

    return {"id": memory_id, "status": "processing"}

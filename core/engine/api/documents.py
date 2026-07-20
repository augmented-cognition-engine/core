# engine/api/documents.py

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.core.tasks import logged_task

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentCreate(BaseModel):
    title: str = Field(max_length=500)
    content: str = Field(max_length=500_000)
    doc_type: str = "other"
    product_id: str
    workspace_id: str | None = None
    tags: list[str] = []


@router.post("", status_code=201)
async def create_document(body: DocumentCreate, user: dict = Depends(get_current_user)):
    async with pool.connection() as db:
        result = await db.query(
            """
            CREATE document SET
                title = $title,
                content = $content,
                doc_type = $doc_type,
                tags = $tags,
                version = 1,
                created_by = $user,
                created_at = time::now(),
                updated_at = time::now()
            """,
            {
                "product": body.product_id,
                "workspace": body.workspace_id,
                "title": body.title,
                "content": body.content,
                "doc_type": body.doc_type,
                "tags": body.tags,
                "user": user.get("sub", "user:default"),
            },
        )
        row = parse_one(result)
        doc_id = row.get("id") if row else None

    # Trigger async ingestion
    logged_task(
        _ingest_document(str(doc_id), body.content, body.product_id, body.workspace_id), label="documents.ingest"
    )

    return {"id": str(doc_id), "status": "created", "ingestion_status": "processing"}


@router.get("")
async def list_documents(
    product: str = Query(...),
    user: dict = Depends(get_current_user),
):
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT id, title, doc_type, tags, created_at, last_ingested
            FROM document
            WHERE product = <record>$product
            ORDER BY created_at DESC
            """,
            {"product": product},
        )
        rows = parse_rows(result)
    return {"documents": rows}


@router.get("/{doc_id}")
async def get_document(doc_id: str, user: dict = Depends(get_current_user)):
    from fastapi import HTTPException

    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": doc_id})
        rows = parse_rows(result)
        if not rows:
            raise HTTPException(status_code=404, detail="Document not found")
    return rows[0]


async def _ingest_document(doc_id: str, content: str, product_id: str, workspace_id: str | None) -> None:
    """Ingest a document through the capture pipeline."""
    from core.engine.capture.document_chunker import chunk_document
    from core.engine.capture.observer import Observer
    from core.engine.capture.synthesizer import Synthesizer

    sections = chunk_document(content)
    observer = Observer(product_id=product_id, workspace_id=workspace_id)
    synthesizer = Synthesizer(product_id=product_id, workspace_id=workspace_id)
    synthesizer._db_pool = pool

    async with pool.connection() as db:
        for section in sections:
            # Write to memory table
            mem_result = await db.query(
                """
                CREATE memory SET
                    content = $content,
                    memory_type = 'document_fragment',
                    source = 'document_ingestion',
                    source_ref = $doc_id,
                    processed = false,
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "workspace": workspace_id,
                    "content": section["content"],
                    "doc_id": doc_id,
                },
            )
            mem_row = parse_one(mem_result)
            memory_id = mem_row.get("id") if mem_row else None

            # Create a synthetic chunk for the observer
            from datetime import datetime

            from core.engine.capture.watchers import Chunk, StreamEvent

            chunk = Chunk(
                content=section["content"],
                chunk_type="reasoning",
                events=[StreamEvent(timestamp=datetime.now(), event_type="text", content=section["content"])],
                start_time=datetime.now(),
                end_time=datetime.now(),
                token_count=len(section["content"]) // 4,
            )

            observations = await observer.evaluate_chunk(chunk, memory_id=memory_id)
            for obs in observations:
                # Write observation
                await db.query(
                    """
                    CREATE observation SET
                        content = $content,
                        observation_type = $type,
                        confidence = $conf,
                        domain_hint = $domain_hint,
                        source_memory = $source_memory,
                        synthesized = false,
                        created_at = time::now()
                    """,
                    {
                        "product": obs["product"],
                        "workspace": obs.get("workspace"),
                        "content": obs["content"],
                        "type": obs["observation_type"],
                        "conf": obs["confidence"],
                        "domain_hint": obs.get("domain_hint"),
                        "source_memory": memory_id,
                    },
                )
                await synthesizer.add_observation(obs)

        await synthesizer.flush()

        # Mark document as ingested
        await db.query(
            "UPDATE <record>$id SET last_ingested = time::now()",
            {"id": doc_id},
        )

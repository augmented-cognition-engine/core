# engine/api/codebase_qa.py
"""REST API for codebase Q&A — ask questions about the codebase."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.engine.core.auth import get_current_user
from core.engine.mcp.tools import ace_ask_product

logger = logging.getLogger(__name__)

router = APIRouter(tags=["codebase"])


class QARequest(BaseModel):
    question: str = Field(description="Natural language question about the codebase")
    context: str | None = Field(default=None, description="Optional additional context")


class QAResponse(BaseModel):
    answer: str
    sources: list[dict] = Field(default_factory=list)
    capabilities_referenced: list[str] = Field(default_factory=list)


@router.post("/codebase/ask", response_model=QAResponse)
async def ask_codebase(body: QARequest, user=Depends(get_current_user)):
    """Ask a natural language question about the codebase.

    Uses ACE's product map, code graph, and intelligence to answer questions
    like "how does authentication work?" or "what capabilities depend on the database?"
    """
    product_id = user.get("product", "product:default")
    result = await ace_ask_product(question=body.question, product_id=product_id)

    return QAResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources", result.get("relevant_files", [])),
        capabilities_referenced=result.get("capabilities", []),
    )

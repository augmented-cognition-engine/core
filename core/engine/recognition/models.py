"""Recognition models — RecognitionResult and DecisionDraft."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class RecognitionResult(BaseModel):
    is_decision: bool
    confidence: float = Field(ge=0.0, le=1.0)
    decision_type: Literal["architecture", "convention", "trade_off", "direction", "rejection"] | None = None
    extracted_title: str | None = None
    extracted_rationale: str | None = None
    extracted_alternatives: list[str] = Field(default_factory=list)
    likely_affected_capability: str | None = None
    classifier_reasoning: str = ""

    model_config = {"frozen": True}


class DecisionDraft(BaseModel):
    draft_id: str
    recognition: RecognitionResult
    product_id: str
    title: str
    rationale: str
    alternatives: list[str]
    decision_type: str
    likely_capability: str | None
    source: str = "recognition"
    confirm_url: str
    dismiss_url: str
    edit_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"frozen": True}

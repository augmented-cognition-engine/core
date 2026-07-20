"""Pydantic models for structured LLM outputs in the capture pipeline.

These models guarantee schema-conformant JSON from Observer and Synthesizer
LLM calls. Used with llm.complete_structured() for both Claude and OpenAI.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# --- Observer schemas ---


class ObservationItem(BaseModel):
    content: str
    type: Literal["decision", "correction", "discovery", "pattern", "preference", "failure", "fact"]
    confidence: float = Field(ge=0.0, le=1.0)
    discipline_hint: str | None = None
    domain_hint: str | None = None  # backward compat alias — prefer discipline_hint

    @model_validator(mode="after")
    def _backfill_discipline_hint(self) -> "ObservationItem":
        """Backfill discipline_hint from domain_hint when only the old field is present."""
        if self.discipline_hint is None and self.domain_hint is not None:
            self.discipline_hint = self.domain_hint
        return self


class ObserverOutput(BaseModel):
    has_intelligence: bool
    observations: list[ObservationItem] = Field(default_factory=list)


# --- Synthesizer schemas ---


class NewInsight(BaseModel):
    content: str
    tier: Literal["specialty", "subdomain", "domain", "org"]
    discipline: str = ""
    domain_path: str = ""  # backward compat — prefer discipline
    insight_type: Literal["fact", "pattern", "decision", "correction", "preference", "convention", "discovery"]
    confidence: float = Field(ge=0.0, le=1.0)
    clearance: str = "open"
    source_observations: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _backfill_discipline(self) -> "NewInsight":
        """Backfill discipline from domain_path when only the old field is present."""
        if not self.discipline and self.domain_path:
            self.discipline = self.domain_path.split(".")[0]
        return self


class InsightUpdate(BaseModel):
    existing_insight_id: str
    updated_content: str
    updated_confidence: float = Field(ge=0.0, le=1.0)


class ConflictRecord(BaseModel):
    existing_insight_id: str
    conflicting_observation: str
    explanation: str


class SynthesizerOutput(BaseModel):
    new_insights: list[NewInsight] = Field(default_factory=list)
    updates: list[InsightUpdate] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    skipped: list[int] = Field(default_factory=list)

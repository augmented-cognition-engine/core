"""Pydantic models for structured LLM outputs in the idea pipeline.

These models guarantee schema-conformant JSON from capture classification,
qualification assessment, and incubation brief generation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class IdeaClassification(BaseModel):
    domain_path: str
    type: Literal["feature", "project", "process", "research", "experiment", "other"]
    complexity: Literal["simple", "moderate", "complex", "ambitious"]
    title: str
    summary: str


class QualificationResult(BaseModel):
    status: Literal["ready", "needs_questions"]
    questions: list[str] = Field(default_factory=list)

    @field_validator("questions")
    @classmethod
    def max_two_questions(cls, v: list[str]) -> list[str]:
        if len(v) > 2:
            raise ValueError("Qualification must ask at most 2 questions")
        return v


class IncubationBrief(BaseModel):
    what: str
    why: str
    what_we_know: str
    open_questions: list[str] = Field(default_factory=list)
    approach: str
    effort: str
    risks: list[str] = Field(default_factory=list)
    first_step: str


class IdeaConnection(BaseModel):
    insight_id: str
    content_preview: str
    relevance: Literal["direct", "related"]


class IdeaPhase(BaseModel):
    name: str
    description: str
    archetype: str
    mode: str
    estimated_hours: float | None = None
    depends_on: list[int] = Field(default_factory=list)
    requires_human: bool = False

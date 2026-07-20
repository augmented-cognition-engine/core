# engine/worker/models.py
"""Pydantic models for the ACE Session Intelligence Worker API."""

from __future__ import annotations

from pydantic import BaseModel


class MessagePayload(BaseModel):
    session_id: str
    message: str
    product_id: str = "product:platform"


class SessionCompletePayload(BaseModel):
    session_id: str
    product_id: str = "product:platform"


class SessionContext(BaseModel):
    session_id: str
    discipline: str = "architecture"
    archetype: str = "executor"
    mode: str = "reactive"
    perspective: str = "practitioner"
    specialties: list[str] = []
    rolling_summary: str = ""
    message_count: int = 0
    compact_index: str = ""


class SessionEndPayload(BaseModel):
    session_id: str
    transcript_path: str
    reason: str = "exit"
    product_id: str = "product:platform"


class ObservationPayload(BaseModel):
    content: str
    type: str = "pattern"
    domain_path: str = "general"
    confidence: float = 0.75
    source: str = "hook"
    product_id: str = "product:platform"
    file_path: str | None = None  # primary file this observation is about (from signal refs)


class SignalDecisionPayload(BaseModel):
    """Promote an ace-signal of type 'decision' to a proper decision record."""

    summary: str  # signal summary → decision title
    rationale: str = ""
    decision_type: str = "convention"  # default: most signals are conventions
    discipline_hint: str | None = None
    confidence: float = 0.75
    refs: list[str] = []  # file refs from the signal
    product_id: str = "product:platform"


class ObserveTurnPayload(BaseModel):
    """Agent or user conversation turn → recognition pipeline (A5).

    The PostToolUse hook POSTs the agent's last message here so the A5
    classifier can detect decisions in agent work the same way it does
    for user sessions. Both flow into the same recognition pipeline.
    """

    text: str
    product_id: str = "product:platform"
    actor: str = "agent"  # "agent" or "user"
    capabilities: list[str] = []


class HarnessContext(BaseModel):
    """Structured context for harness hook rendering.

    All voice strings follow partner-voice rules: we/our/us, no Alert/Warning,
    ≤200 chars each. Hooks render these directly — no hook generates voice text.
    """

    session_id: str
    product_id: str = "product:platform"
    greeting: str  # 1-2 sentences, colleague opener
    status_pulse: str  # "watching: {discipline} · {n} ideas ready"
    proactive_line: str | None = None  # top-ranked finding in partner voice
    proactive_drill_down: str | None = None  # URL to source artifact
    recent_decisions: list[dict] = []  # last 3 decisions for reflection cards
    worker_health: str | None = None
    generated_at: str = ""

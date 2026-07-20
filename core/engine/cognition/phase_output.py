"""Typed inter-phase contract for the cognitive composition pipeline.

Every phase produces a PhaseOutput. The confidence score drives downstream
behaviour: high → proceed, medium → corroborate, low → flag before synthesis.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PhaseOutput(BaseModel):
    """Structured output from a single cognitive phase."""

    output: str
    confidence: float = Field(ge=0.0, le=1.0, description="0.0=uncertain, 1.0=certain")
    evidence: list[str] = Field(default_factory=list, description="Supporting facts used")
    gaps: list[str] = Field(default_factory=list, description="What remains unresolved")

    @classmethod
    def schema_prompt(cls) -> str:
        """Return the JSON schema instruction injected into every phase prompt."""
        return (
            "Output JSON matching this schema:\n"
            '{"output": "<your analysis>", "confidence": 0.0-1.0, '
            '"evidence": ["fact used", ...], "gaps": ["unresolved item", ...]}'
        )

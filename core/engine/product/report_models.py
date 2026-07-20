# engine/product/report_models.py
"""Data models for MSP discovery sprint reports.

SpecStub            — minimal spec passable directly to ace_create_spec
AutomationCandidate — an automation opportunity with grounded ROI estimate
DiscoveryReport     — full client-ready deliverable from a discovery sprint
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

_VALID_EFFORT_TIERS = {"low", "medium", "high"}
_VALID_SCOPES = {"low", "medium", "high"}

# Words that must not appear in executive summaries (non-technical stakeholder rule)
_EXEC_SUMMARY_JARGON = [
    "discipline",
    "graph node",
    "archetype",
    "synthesis",
]


@dataclass
class SpecStub:
    """A minimal spec ready to pass directly to ace_create_spec without modification.

    estimated_scope maps to effort: low (<1 week), medium (1-2 weeks), high (>2 weeks).
    """

    title: str
    acceptance_criteria: List[str]
    estimated_scope: str  # "low" | "medium" | "high"

    def __post_init__(self) -> None:
        if self.estimated_scope not in _VALID_SCOPES:
            raise ValueError(
                f"SpecStub estimated_scope must be one of {sorted(_VALID_SCOPES)!r} — got {self.estimated_scope!r}"
            )

    def to_dict(self) -> dict:
        """Return a dict compatible with ace_create_spec (objective + acceptance_criteria)."""
        return {
            "objective": self.title,
            "acceptance_criteria": self.acceptance_criteria,
            "estimated_scope": self.estimated_scope,
        }


@dataclass
class AutomationCandidate:
    """An automation opportunity with grounded ROI estimate.

    annual_value = hours_per_week_saved × loaded_hourly_rate × 52
    This is computed — never provided by the user.
    """

    title: str
    description: str
    hours_per_week_saved: float
    loaded_hourly_rate: float
    effort_tier: str  # "low" | "medium" | "high"
    spec_stub: Optional[SpecStub]

    def __post_init__(self) -> None:
        if self.effort_tier not in _VALID_EFFORT_TIERS:
            raise ValueError(
                f"AutomationCandidate effort_tier must be one of {sorted(_VALID_EFFORT_TIERS)!r} "
                f"— got {self.effort_tier!r}"
            )

    @property
    def annual_value(self) -> float:
        """Annual value recovered: hours/week × loaded rate × 52 weeks."""
        return self.hours_per_week_saved * self.loaded_hourly_rate * 52

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "hours_per_week_saved": self.hours_per_week_saved,
            "loaded_hourly_rate": self.loaded_hourly_rate,
            "annual_value": self.annual_value,
            "effort_tier": self.effort_tier,
            "spec_stub": self.spec_stub.to_dict() if self.spec_stub else None,
        }


@dataclass
class DiscoveryReport:
    """Full client-ready deliverable from a discovery sprint.

    Designed for non-technical stakeholders (COO, VP Ops) — zero jargon.
    Exportable as markdown and JSON.
    """

    product_id: str
    client_name: str
    executive_summary: str  # ≤ 300 words, no jargon
    automation_candidates: List[AutomationCandidate]
    systems_map_summary: str
    preliminary: bool = False  # True when synthesizer output was absent

    def validate_exec_summary(self) -> None:
        """Raise ValueError if executive_summary contains technical jargon."""
        lowered = self.executive_summary.lower()
        for word in _EXEC_SUMMARY_JARGON:
            if word in lowered:
                raise ValueError(
                    f"Executive summary contains jargon word {word!r} — "
                    "must use plain language for non-technical stakeholders"
                )

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "client_name": self.client_name,
            "executive_summary": self.executive_summary,
            "automation_candidates": [c.to_dict() for c in self.automation_candidates],
            "systems_map_summary": self.systems_map_summary,
            "preliminary": self.preliminary,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        """Render report as markdown suitable for Notion, Google Docs, or email."""
        from core.engine.product.report_generator import ReportGenerator

        return ReportGenerator(self).to_markdown()

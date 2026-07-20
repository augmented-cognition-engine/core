"""Per-repo review configuration via .ace.yaml files."""

from __future__ import annotations

import logging

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GateConfig(BaseModel):
    """Quality gate thresholds."""

    critical_threshold: int = 0  # max critical findings allowed
    high_threshold: int = 3  # max high findings allowed
    min_discipline_score: float = 0.5  # minimum per-discipline score


class ReviewConfig(BaseModel):
    """Per-repo review configuration from .ace.yaml."""

    disciplines: list[str] | None = None  # override auto-detection
    exclude_paths: list[str] = Field(default_factory=list)  # glob patterns to skip
    gate: GateConfig = Field(default_factory=GateConfig)
    post_review: bool = True  # post review comments to GitHub
    post_status: bool = True  # post commit status checks

    @classmethod
    def from_yaml(cls, content: str) -> ReviewConfig:
        """Parse .ace.yaml content."""
        try:
            data = yaml.safe_load(content) or {}
            review_data = data.get("review", {})
            return cls(**review_data)
        except Exception as exc:
            logger.warning("Failed to parse .ace.yaml: %s", exc)
            return cls()

    @classmethod
    def default(cls) -> ReviewConfig:
        return cls()

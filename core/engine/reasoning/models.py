# engine/reasoning/models.py
"""Reasoning framework data models.

Frameworks are reasoning strategies injected into LLM prompts to shape
how the model thinks about a problem. Selected based on task classification
(archetype + mode) and activation signals.
"""

from __future__ import annotations

from pydantic import BaseModel


class Framework(BaseModel):
    """A reasoning framework definition."""

    slug: str
    name: str
    family: str  # diagnostic, systemic, generative, evaluative, predictive, adversarial
    tier: str = "built-in"  # built-in, domain, advanced
    description: str = ""
    system_prompt: str = ""
    activation_signals: list[str] = []
    archetype_affinity: dict[str, float] = {}  # archetype -> weight 0.0-1.0
    mode_affinity: dict[str, float] = {}  # mode -> weight 0.0-1.0
    task_type_affinity: dict[str, float] = {}  # task_type -> weight 0.0-1.0; empty = universal
    composability: dict[str, list[str]] = {}  # conflicts: [...], complements: [...]


class FrameworkSelection(BaseModel):
    """Result of framework selection — the chosen frameworks and composition pattern."""

    frameworks: list[Framework]
    composition_pattern: str  # stacked (1), layered (2-3 same phase), iterative (generate+evaluate)
    scores: list[float] = []

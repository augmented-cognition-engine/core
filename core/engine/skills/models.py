# engine/skills/models.py
"""Skill data models — Pydantic schemas for skill definitions and execution.

Hierarchy:
  Skill   — reusable execution template (the procedure)
  Phase   — one step in the procedure, with its own orchestration pattern
  Slot    — one agent within a phase (archetype + mode + frameworks + specialties)
  PhaseExit — inter-phase routing rules (state machine transitions)

A Phase with pattern="solo" and one Slot is equivalent to the old Job model.
Job is kept for backward compatibility with existing DB records.
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator

# ---------------------------------------------------------------------------
# Slot — one agent within a phase
# ---------------------------------------------------------------------------


class Slot(BaseModel):
    """A single agent slot within a phase."""

    archetype: str  # creator, analyst, executor, researcher, advisor, sentinel
    mode: str  # deliberative, reactive, exploratory, conversational, procedural, reflective
    frameworks: list[str] = []
    specialties: list[str] = []  # specialty slugs to load for this slot
    model_tier: str = "default"  # default | budget | premium
    description: str = ""


# ---------------------------------------------------------------------------
# PhaseExit — inter-phase routing (state machine transitions)
# ---------------------------------------------------------------------------


class PhaseExit(BaseModel):
    """Exit criteria and routing rules for a phase."""

    # What to do on success
    on_success: str = "next"  # next | <phase_name> | done

    # What to do on failure
    on_failure: str = "abort"  # loop | jump:<phase_name> | request_context | escalate | abort

    # How many attempts before treating as failure
    max_attempts: int = 1

    # Confidence below this threshold = failure
    confidence_threshold: float = 0.5

    # Model tier to upgrade to on escalate (None = same tier)
    escalation_tier: str | None = None


# ---------------------------------------------------------------------------
# Phase — one step in the skill, with its own orchestration pattern
# ---------------------------------------------------------------------------


class Phase(BaseModel):
    """A single phase within a skill execution plan."""

    name: str
    pattern: str = "solo"  # solo | pipeline | parallel | hierarchical | iterative | adversarial | router

    # Agent slots — 1 for solo, N for parallel/adversarial/etc.
    slots: list[Slot]

    # How to combine outputs from multiple slots
    aggregation: str = "last"  # last | vote | rank | synthesize | merge | diff | compete | accumulate

    # When to stop iterating (for iterative/adversarial patterns)
    termination: str = "single"  # single | max_rounds | convergence | approval | quality_threshold

    output_format: str = "prose"  # prose | structured | list | table
    description: str = ""

    # State machine exit rules
    exit: PhaseExit = PhaseExit()

    # Optional sentinel slot that evaluates phase output quality
    evaluator: Slot | None = None

    @classmethod
    def from_job(cls, job: "Job") -> "Phase":
        """Migrate a legacy Job to a Phase (solo pattern, single slot)."""
        slot = Slot(
            archetype=job.archetype,
            mode=job.mode,
            frameworks=job.frameworks,
            description=job.description,
        )
        return cls(
            name=job.name,
            pattern="solo",
            slots=[slot],
            output_format=job.output_format,
            description=job.description,
        )


# ---------------------------------------------------------------------------
# Skill — the full execution template
# ---------------------------------------------------------------------------


class Skill(BaseModel):
    """A complete skill definition — an ordered sequence of phases."""

    slug: str
    name: str
    description: str
    discipline: str | None = None  # primary discipline slug
    domain_path: str | None = None  # backward compat alias
    tier: str = "built-in"  # built-in, domain, custom
    phases: list[Phase] = []
    activation_signals: list[str] = []

    # Backward compat: old DB records store phases as "jobs"
    jobs: list["Job"] = []

    @model_validator(mode="after")
    def migrate_jobs(self) -> "Skill":
        """If phases is empty but jobs exists, convert jobs → phases."""
        if not self.phases and self.jobs:
            self.phases = [Phase.from_job(j) for j in self.jobs]
        return self

    @property
    def effective_discipline(self) -> str | None:
        return self.discipline or self.domain_path


# ---------------------------------------------------------------------------
# Job — legacy model kept for backward compatibility
# ---------------------------------------------------------------------------


class Job(BaseModel):
    """Legacy single-step job model. Kept for backward compat with old DB records.

    Use Phase + Slot for new skill definitions.
    """

    name: str
    archetype: str
    mode: str
    frameworks: list[str] = []
    output_format: str = "prose"
    description: str = ""


# ---------------------------------------------------------------------------
# SkillMatch — result of skill selection
# ---------------------------------------------------------------------------


class SkillMatch(BaseModel):
    """Result of skill selection — the matched skill with a relevance score."""

    skill: Skill
    score: float
    matched_signals: list[str]

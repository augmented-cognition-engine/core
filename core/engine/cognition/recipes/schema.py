"""Pydantic schema for YAML-authored recipes.

Mirrors core.engine.cognition.models — MetaSkill, MetaSkillRecipe,
RecipePhase, InstrumentSpec — and converts validated YAML into the
existing dataclass tree. extra="forbid" rejects unknown fields so
YAML format drift is caught at load time.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.engine.cognition.models import (
    CaptureSpec,
    ContextQuery,
    InstrumentSpec,
    MetaSkill,
    MetaSkillRecipe,
    RecipePhase,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InstrumentSchema(_Strict):
    fallback_slug: str
    slug: str | None = None
    family_hint: str | None = None
    task_affinity: dict = Field(default_factory=dict)
    bindings: dict[str, str] | None = None
    output_key: str | None = None

    def to_dataclass(self) -> InstrumentSpec:
        return InstrumentSpec(
            fallback_slug=self.fallback_slug,
            slug=self.slug,
            family_hint=self.family_hint,
            task_affinity=self.task_affinity,
            bindings=self.bindings,
            output_key=self.output_key,
        )


class ContextQuerySchema(_Strict):
    queries: list[str]
    inject_as: str

    def to_dataclass(self) -> ContextQuery:
        return ContextQuery(
            queries=self.queries,
            inject_as=self.inject_as,
        )


class CaptureSpecSchema(_Strict):
    type: str
    discipline_hint: str
    extract_fields: list[str]

    def to_dataclass(self) -> CaptureSpec:
        return CaptureSpec(
            type=self.type,
            discipline_hint=self.discipline_hint,
            extract_fields=self.extract_fields,
        )


class PhaseSchema(_Strict):
    cognitive_function: str
    instruments: list[InstrumentSchema] = Field(min_length=1)
    min_depth: int
    output_schema: str
    pattern: str = "solo"
    must_not: list[str] = Field(default_factory=list)
    must_verify: list[str] = Field(default_factory=list)
    load_context: ContextQuerySchema | None = None
    capture_as: CaptureSpecSchema | None = None

    def to_dataclass(self) -> RecipePhase:
        return RecipePhase(
            cognitive_function=self.cognitive_function,
            instruments=[i.to_dataclass() for i in self.instruments],
            min_depth=self.min_depth,
            output_schema=self.output_schema,
            pattern=self.pattern,
            must_not=self.must_not,
            must_verify=self.must_verify,
            load_context=self.load_context.to_dataclass() if self.load_context else None,
            capture_as=self.capture_as.to_dataclass() if self.capture_as else None,
        )


class RecipeBlockSchema(_Strict):
    phases: list[PhaseSchema] = Field(min_length=1)

    def to_dataclass(self) -> MetaSkillRecipe:
        return MetaSkillRecipe(phases=[p.to_dataclass() for p in self.phases])


class RoutingSchema(_Strict):
    disciplines: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)


class RecipeYAMLSchema(_Strict):
    """Top-level schema for one YAML recipe file."""

    slug: str
    name: str
    description: str
    domain_intelligences: list[str]
    min_execution_depth: int = 1
    recipe: RecipeBlockSchema
    routing: RoutingSchema | None = None
    # Self-nomination fields — mirror MetaSkill model. Optional for backward
    # compat with YAML files authored before problem-derived composition shipped.
    activation_signals: list[str] = Field(default_factory=list)
    archetype_affinity: dict[str, float] = Field(default_factory=dict)
    mode_affinity: dict[str, float] = Field(default_factory=dict)
    composability: dict[str, list[str]] = Field(default_factory=dict)

    def to_meta_skill(self) -> MetaSkill:
        return MetaSkill(
            slug=self.slug,
            name=self.name,
            description=self.description,
            domain_intelligences=self.domain_intelligences,
            recipe=self.recipe.to_dataclass(),
            min_execution_depth=self.min_execution_depth,
            activation_signals=self.activation_signals,
            archetype_affinity=self.archetype_affinity,
            mode_affinity=self.mode_affinity,
            composability=self.composability,
        )

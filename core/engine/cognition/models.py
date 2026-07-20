"""Data models for the cognitive composition layer.

InstrumentSpec    → one instrument slot in a recipe phase
ContextQuery      → what to load from the graph before a phase runs
CaptureSpec       → how to persist a phase's output to the product graph
RecipePhase       → one cognitive step (frame/prioritize/choose/validate/allocate/critique)
MetaSkillRecipe   → ordered list of RecipePhases for one meta-skill
MetaSkill         → named intelligence type with a recipe
CognitiveComposition → resolved output of CognitiveComposer.compose()
derive_depth()    → maps mode + complexity to depth 1-4
"""

from __future__ import annotations

from dataclasses import dataclass, field


def derive_depth(mode: str, complexity: str) -> int:
    """Map cognitive mode + task complexity to execution depth.

    Depth controls how many recipe phases activate and whether
    they are fused into one prompt (1-2) or executed sequentially (3-4).
    """
    if mode in ("reactive", "conversational"):
        return 1
    if mode == "procedural":
        return 2
    if mode == "deliberative":
        return 3 if complexity != "simple" else 2
    if mode in ("reflective", "exploratory"):
        return 4
    return 2


@dataclass
class ContextQuery:
    """What to load from the product graph before a phase runs.

    queries: list of SurrealQL SELECT statements to execute
    inject_as: key name injected into the phase's system prompt context block
    """

    queries: list[str]
    inject_as: str


@dataclass
class CaptureSpec:
    """How to persist a phase's output to the product graph.

    type: observation type (decision, pattern, preference, learning)
    discipline_hint: which discipline this capture belongs to
    extract_fields: which output_schema fields to extract from the PhaseOutput

    The extractor looks for these field names inside PhaseOutput.output (JSON)
    or falls back to the full output text if not JSON-parseable.
    """

    type: str  # "decision" | "pattern" | "preference" | "learning"
    discipline_hint: str
    extract_fields: list[str]


@dataclass
class InstrumentSpec:
    """One instrument slot in a recipe phase.

    Either `slug` (explicit framework to use) or `family_hint` (dynamic:
    let the classifier pick the best framework from that family).
    `fallback_slug` is always required — used when dynamic resolution fails
    or when the explicit slug is not found in the DB.

    Python-instrument dispatch fields (optional; ignored by DB-framework path):
    bindings:   maps instrument kwarg names → phase-context keys.
                e.g. {"context": "audit_context", "workload": "workload"}
    output_key: where in the phase context to store the instrument's return value.
    """

    fallback_slug: str
    slug: str | None = None
    family_hint: str | None = None
    task_affinity: dict = field(default_factory=dict)
    bindings: dict[str, str] | None = None
    output_key: str | None = None


@dataclass
class ToolSpec:
    """One tool slot in a recipe phase — ADVISORY (surfaced in the phase prompt,
    not enforced). Mirrors InstrumentSpec resolution: an explicit `slug`, or a
    `family_hint` for learned selection, with a required `fallback_slug`.

    Tools run in the outer agent / orchestrator, never inside the pure-computation
    phase LLM call, so there are no bindings/output_key fields.
    """

    fallback_slug: str
    slug: str | None = None
    family_hint: str | None = None


@dataclass
class RecipePhase:
    """One cognitive step in a meta-skill recipe.

    cognitive_function: what kind of thinking happens here
      frame | prioritize | choose | validate | allocate | critique

    min_depth: the minimum execution depth at which this phase activates.
      Phase is skipped entirely when the task's depth < min_depth.

    output_schema: describes what this phase produces (constrains next phase
      input in multi-phase / depth 3-4 execution).

    pattern: how instruments in this phase relate to each other
      solo | pipeline | adversarial | parallel

    load_context: if set, queries are run before this phase and results are
      injected into the system prompt as a context block.

    capture_as: if set, the phase output is extracted and persisted to the
      product graph as an observation (decision, pattern, preference, etc.)

    signature: how signature this cognitive_function is to this skill (0..1).
      The composer's best-fit-per-slot blend awards each slot to the skill
      with the highest (relevance + SIGNATURE_WEIGHT * signature). Default 0.5
      is neutral: when every phase is 0.5 the term is constant and selection
      collapses to highest-relevance.
    """

    cognitive_function: str
    instruments: list[InstrumentSpec]
    min_depth: int
    output_schema: str
    pattern: str = "solo"
    must_not: list[str] = field(default_factory=list)
    must_verify: list[str] = field(default_factory=list)
    load_context: ContextQuery | None = None
    capture_as: CaptureSpec | None = None
    tools: list["ToolSpec"] = field(default_factory=list)
    signature: float = 0.5


@dataclass
class MetaSkillRecipe:
    """The full phased recipe for one meta-skill.

    Standard recipe follows the 6-phase cognitive pattern:
      1. frame (min_depth=1)
      2. prioritize (min_depth=1)
      3. choose (min_depth=2)
      4. validate (min_depth=3)
      5. allocate (min_depth=2 or 3)
      6. critique (min_depth=4)
    """

    phases: list[RecipePhase]


@dataclass
class MetaSkill:
    """A named intelligence type with a phased recipe.

    slug: unique identifier, e.g. "coding_intelligence"
    domain_intelligences: the taxonomy types this meta-skill covers
    recipe: phased instrument composition
    min_execution_depth: recipe-level floor — even if the classifier returns a
      lower depth, this meta-skill will always run at least this deep.
      Useful for skills like creative_intelligence that are inherently deliberative.

    Self-nomination fields (problem-derived selection):
      The composer queries each meta-skill for relevance to a task instead of
      consulting hardcoded routing dicts. Each meta-skill declares the signals,
      affinities, and composability that make it relevant — mirroring how the
      181 instruments in seed.py already self-describe.

    activation_signals: semantic triggers in task descriptions that suggest this
      meta-skill is relevant. Composer matches against task text + classification.
    archetype_affinity: {archetype_slug: 0.0-1.0} — how strongly this meta-skill
      pairs with each archetype. Higher = more likely to fire when that archetype
      is active.
    mode_affinity: {mode_slug: 0.0-1.0} — affinity per cognitive mode. Some
      meta-skills (like creative) are inherently deliberative and shouldn't fire
      in reactive mode.
    composability: {"complements": [slugs], "conflicts": [slugs]} — which other
      meta-skills this one pairs well with, and which it should not co-fire with.
      Used by the composer to assemble coherent meta-skill sets.
    """

    slug: str
    name: str
    description: str
    domain_intelligences: list[str]
    recipe: MetaSkillRecipe
    min_execution_depth: int = 1
    activation_signals: list[str] = field(default_factory=list)
    archetype_affinity: dict[str, float] = field(default_factory=dict)
    mode_affinity: dict[str, float] = field(default_factory=dict)
    composability: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class CognitiveComposition:
    """Resolved output of CognitiveComposer.compose().

    Stored at classification["cognitive_composition"].
    Consumed by ShellComposer to restructure the system prompt.

    meta_skills: active intelligence types for this task
    depth: 1-4, determined by mode + complexity
    active_phases: RecipePhases that survived depth filtering
    resolved_instruments: phase_idx (str) → list of framework slugs resolved
    prompt_sections: pre-built prompt fragments (one per active phase)
    fusion_mode: True when depth <= 2 (fuse all sections into one prompt)
    """

    meta_skills: list[str]
    depth: int
    active_phases: list[RecipePhase]
    resolved_instruments: dict[str, list[str]]
    prompt_sections: list[dict]
    fusion_mode: bool
    roster: list[dict] = field(default_factory=list)
    # TALE per-phase token cap. None means use the LLM provider default.
    max_tokens_per_phase: int | None = None
    # Loop context that grounded this composition (prior decisions + calibration).
    # Empty dict when the stateless path was used (no DB, no loader).
    loop_context: dict = field(default_factory=dict)
    # phase_idx (str) → list of resolved tool slugs (advisory; mirrors resolved_instruments)
    resolved_tools: dict[str, list[str]] = field(default_factory=dict)

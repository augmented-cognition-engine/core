# engine/cognition/composer.py
"""CognitiveComposer — the main entry point for the cognitive composition layer.

Given a classification dict, returns a CognitiveComposition:
  - Selects active meta-skills from discipline + task_type + mode
  - Derives depth from mode + complexity
  - Filters recipe phases by min_depth <= depth
  - Resolves instrument slots via FrameworkClassifier
  - Builds prompt_sections (one dict per active phase) for ShellComposer
  - Sets fusion_mode=True if depth <= 2 (zero extra LLM calls)
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from core.engine.cognition.classifier import FrameworkClassifier
from core.engine.cognition.models import (
    CognitiveComposition,
    MetaSkill,
    RecipePhase,
    derive_depth,
)

logger = logging.getLogger(__name__)

# Feature flag for problem-derived meta-skill selection.
# When True, the composer queries each meta-skill's self-described relevance
# (activation_signals + affinities + composability) instead of consulting the
# hardcoded _TASK_TYPE_META / _DISCIPLINE_META / _AGENTIC_META_BY_MODE dicts.
# Validated against 12 realistic classifications on 2026-05-27 (see
# scripts/compare_selectors.py). Now canonical.
ENABLE_PROBLEM_DERIVED_SELECTION = True

# Best-fit-per-slot weighting: each cognitive_function slot goes to the skill with
# the highest (relevance_score + SIGNATURE_WEIGHT * phase.signature). Small enough
# that signature only flips a CLOSE relevance race, never an overwhelming one.
SIGNATURE_WEIGHT = 0.25

# Canonical cognitive_function emission order (design spec
# docs/superpowers/specs/2026-07-15-coding-intelligence-best-fit-composer-design.md
# §1). Ensures `review` always precedes `critique` — critique is designed to
# consume review's findings — regardless of which skill's phase order the
# functions were first seen in during winner selection.
_CANONICAL_FUNCTION_ORDER = ["frame", "prioritize", "choose", "validate", "review", "allocate", "critique"]


# Most-recent composition per product_id. Populated on every successful
# CognitiveComposer.compose(). Powers introspection surfaces (MCP tool
# ace_active_composition, the canvas orchestra view, AI partner queries)
# that want to read "what's the orchestra doing right now" without
# subscribing to the canvas event stream.
#
# In-memory only — small per-product footprint, lost on restart, which is
# fine because the next compose() repopulates it. Keep this lightweight;
# heavier introspection should query the canvas event log directly.
_recent_compositions: dict[str, dict] = {}


def get_recent_composition(product_id: str) -> dict | None:
    """Return the most recent composition emitted for product_id, or None.

    Returns a dict snapshot (not the live CognitiveComposition object) so
    introspection consumers can't accidentally mutate the substrate state.
    """
    snapshot = _recent_compositions.get(product_id)
    return dict(snapshot) if snapshot is not None else None


def _score_meta_skill_relevance(
    meta_skill: MetaSkill,
    classification: dict,
    task_text: str = "",
) -> float:
    """Score a meta-skill's self-described relevance to a classified task.

    Returns a value in [0.0, 1.0] computed from four weighted components:

      0.30 activation_signal match
           Fraction of the meta-skill's signals found in synthesized task text
           (description + discipline + task_type + complexity + specialties).
           Normalized so that ~4 signal hits = full credit.

      0.30 archetype_affinity
           Meta-skill's declared affinity for the classified archetype.
           Defaults to 0.5 (neutral) when the archetype isn't listed.

      0.30 mode_affinity
           Meta-skill's declared affinity for the classified cognitive mode.
           Defaults to 0.5 (neutral) when the mode isn't listed.

      0.10 domain_match
           1.0 if the classified discipline appears in the meta-skill's
           domain_intelligences, else 0.0. Bridges to legacy classification
           dimensions while activation_signals take primary weight.

    Pure function — no I/O. Used by CognitiveComposer._rank_meta_skills_dynamic.
    """
    # Synthesize text from everything we know about the task
    parts: list[str] = []
    if task_text:
        parts.append(task_text)
    for key in ("discipline", "task_type", "complexity"):
        value = classification.get(key, "")
        if value:
            parts.append(str(value))
    for spec in classification.get("specialties", []) or []:
        if spec:
            parts.append(str(spec))
    synthesized = " ".join(parts).lower()

    # 1. Activation signal match — 4 hits = full credit
    signals = meta_skill.activation_signals or []
    if signals and synthesized:
        hits = sum(1 for sig in signals if sig.lower() in synthesized)
        signal_score = min(1.0, hits / 4.0)
    else:
        signal_score = 0.0

    # 2. Archetype affinity
    archetype = classification.get("archetype", "")
    archetype_score = (meta_skill.archetype_affinity or {}).get(archetype, 0.5)

    # 3. Mode affinity
    mode = classification.get("mode", "reactive")
    mode_score = (meta_skill.mode_affinity or {}).get(mode, 0.5)

    # 4. Domain match — legacy discipline bridge
    discipline = classification.get("discipline", "") or classification.get("domain_path", "")
    domain_match = 1.0 if discipline and discipline in (meta_skill.domain_intelligences or []) else 0.0

    # Weights: signals dominate so meta-skills without signal evidence don't
    # ride on affinity alone. Mode and archetype still matter (they encode
    # how-this-skill-thinks), but signal evidence anchors relevance.
    total = 0.45 * signal_score + 0.20 * archetype_score + 0.25 * mode_score + 0.10 * domain_match

    # Discipline-anchor floor: when the meta-skill explicitly claims this
    # discipline in its domain_intelligences, ensure it crosses the default
    # threshold (~0.45). Preserves legacy dict-routing intent ("discipline X
    # selects meta-skill Y") via the meta-skill's own self-declaration of
    # domains — no kernel routing dict required.
    if domain_match == 1.0:
        total = max(total, 0.50)

    return total


# ---------------------------------------------------------------------------
# Meta-skill selection tables
# ---------------------------------------------------------------------------

# Maps 23 ACE disciplines to primary domain meta-skill
_DISCIPLINE_META: dict[str, str] = {
    "architecture": "systems_intelligence",
    "api_design": "coding_intelligence",
    "data_modeling": "data_intelligence",
    "business_logic": "coding_intelligence",
    "integration": "systems_intelligence",
    "security": "evaluation_intelligence",
    "testing": "evaluation_intelligence",
    "ux": "creative_intelligence",
    "performance": "systems_intelligence",
    "devops": "operational_intelligence",
    "observability": "data_intelligence",
    "documentation": "communication_intelligence",
    "code_conventions": "coding_intelligence",
    "dependency_management": "systems_intelligence",
    "error_handling": "coding_intelligence",
    "accessibility": "evaluation_intelligence",
    "configuration": "operational_intelligence",
    "deployment": "operational_intelligence",
    "versioning": "coding_intelligence",
    "data": "data_intelligence",  # classifier emits "data" as a valid discipline
    "ai_ml": "evaluation_intelligence",  # safety, model quality, output assessment
    "scale": "systems_intelligence",  # distributed systems, capacity, backpressure
    "product_strategy": "strategic_intelligence",  # product-market fit, positioning, roadmap, growth
    # Extension disciplines (e.g. "marketing" -> marketing_audit_intelligence) are NOT
    # listed here — extensions declare their routing via register_recipe(disciplines=...)
    # and it is merged in _select_meta_skills().
}

# Maps task_type (from classification) to primary domain meta-skill
_TASK_TYPE_META: dict[str, str] = {
    "research": "research_intelligence",
    "design": "creative_intelligence",
    "implement": "coding_intelligence",
    "code": "coding_intelligence",
    "review": "evaluation_intelligence",
    "evaluate": "evaluation_intelligence",
    "analyze": "data_intelligence",
    "plan": "planning_intelligence",
    "debug": "coding_intelligence",
    "create": "creative_intelligence",
    "strategic": "strategic_intelligence",
    "communicate": "communication_intelligence",
    "build": "coding_intelligence",
    "refactor": "coding_intelligence",
    "test": "evaluation_intelligence",
}

# Agentic meta-skills added based on cognitive mode
_AGENTIC_META_BY_MODE: dict[str, list[str]] = {
    "reactive": ["verification_intelligence"],
    "conversational": ["retrieval_intelligence", "verification_intelligence", "communication_agentic_intelligence"],
    "procedural": ["planning_intelligence", "verification_intelligence", "tool_intelligence"],
    "deliberative": [
        "planning_intelligence",
        "risk_intelligence",
        "verification_intelligence",
        "delegation_intelligence",
        "tool_intelligence",
    ],
    "reflective": [
        "planning_intelligence",
        "risk_intelligence",
        "verification_intelligence",
        "memory_intelligence",
        "feedback_intelligence",
        "tool_intelligence",
    ],
    "exploratory": [
        "research_intelligence",
        "gap_intelligence",
        "verification_intelligence",
        "memory_intelligence",
        "tool_intelligence",
    ],
}

# Slug → module path
_RECIPE_MODULES: dict[str, str] = {
    "creative_intelligence": "core.engine.cognition.recipes.creative",
    "research_intelligence": "core.engine.cognition.recipes.research",
    "coding_intelligence": "core.engine.cognition.recipes.coding",
    "evaluation_intelligence": "core.engine.cognition.recipes.evaluation",
    "strategic_intelligence": "core.engine.cognition.recipes.strategic",
    "communication_intelligence": "core.engine.cognition.recipes.communication",
    "systems_intelligence": "core.engine.cognition.recipes.systems",
    "data_intelligence": "core.engine.cognition.recipes.data",
    "retrieval_intelligence": "core.engine.cognition.recipes.retrieval",
    "planning_intelligence": "core.engine.cognition.recipes.planning",
    "delegation_intelligence": "core.engine.cognition.recipes.delegation",
    "risk_intelligence": "core.engine.cognition.recipes.risk",
    "gap_intelligence": "core.engine.cognition.recipes.gap",
    "feedback_intelligence": "core.engine.cognition.recipes.feedback",
    "verification_intelligence": "core.engine.cognition.recipes.verification",
    "memory_intelligence": "core.engine.cognition.recipes.memory",
    "coordination_intelligence": "core.engine.cognition.recipes.coordination",
    "tool_intelligence": "core.engine.cognition.recipes.tool",
    "communication_agentic_intelligence": "core.engine.cognition.recipes.communication_agentic",
    "operational_intelligence": "core.engine.cognition.recipes.operational",
    "domain_specific_intelligence": "core.engine.cognition.recipes.domain_specific",
    # Extension recipes (e.g. marketing_audit_intelligence) are NOT listed here —
    # they are contributed by extensions via register_recipe() and resolved through
    # the extension registry in _load_recipe().
}

# Slug → already-parsed MetaSkill, populated by
# core.engine.cognition.recipes.loader.discover_core_yaml_recipes() at
# recipes-package import time. Sibling to _RECIPE_MODULES; precedence
# is checked in _load_recipe().
_RECIPE_YAML: dict[str, MetaSkill] = {}

# Trigger core YAML recipe discovery at module load. Discovery requires
# _RECIPE_YAML to exist, so the call sits below the declaration. The
# loader lazy-imports composer to avoid a circular import.
from core.engine.cognition.recipes.loader import discover_core_yaml_recipes  # noqa: E402

discover_core_yaml_recipes()


def _flavor_recipe_module(slug: str) -> str | MetaSkill | None:
    """Resolve an extension-contributed recipe slug to a module path string OR
    a MetaSkill object (YAML path), or None.

    Extensions register recipes as ``slug -> module path`` (the original
    convention; modules expose ``get_meta_skill()``) OR as
    ``slug -> MetaSkill`` (the YAML loader convention). Either form
    flows through CognitiveComposer._load_recipe() which handles both.
    Lazy import keeps the extension chain out of module-import time.
    """
    from core.engine.extensions.registry import registered_recipes

    return registered_recipes().get(slug)


def _flavor_recipe_for_classification(task_type: str, discipline: str) -> str | None:
    """Resolve an extension recipe slug for a classification's task_type/discipline.

    Mirrors the kernel precedence (task_type before discipline). Lazy import keeps
    the extension chain out of module-import time.
    """
    from core.engine.extensions.registry import registered_recipe_disciplines, registered_recipe_task_types

    return registered_recipe_task_types().get(task_type) or registered_recipe_disciplines().get(discipline)


# ---------------------------------------------------------------------------
# Roster hints — color + idle-zone metadata per archetype/perspective
# ---------------------------------------------------------------------------
# Keep in lockstep with frontend/src/canvas/agents/archetypeColors.ts.
# Used to materialize the canvas agent-roster on session open.

ARCHETYPE_COLOR_HINTS: dict[str, str] = {
    "pm": "blue",
    "skeptic": "red",
    "technical_architect": "purple",
    "ux_designer": "green",
    "researcher": "yellow",
    "business_strategist": "orange",
    "data_scientist": "cyan",
    "security_engineer": "pink",
    "analyst": "yellow",
    "advisor": "blue",
    "sentinel": "red",
    "creator": "green",
    "executor": "purple",
}

ARCHETYPE_IDLE_ZONES: dict[str, str] = {
    "pm": "center",
    "skeptic": "right",
    "technical_architect": "left",
    "ux_designer": "bottom-left",
    "researcher": "bottom-right",
    "business_strategist": "top-right",
    "data_scientist": "top-left",
    "security_engineer": "right",
    "analyst": "left",
    "advisor": "right",
    "sentinel": "bottom-right",
    "creator": "bottom-left",
    "executor": "center",
}


def _build_roster(classification: dict[str, Any]) -> list[dict]:
    """Build the canvas agent roster from classification's perspectives.

    Returns one roster entry per perspective in `classification.engagement.perspectives`,
    with color + idle-zone hints. If no perspectives are present (e.g., reactive mode),
    falls back to the single archetype on the classification itself.
    """
    engagement = classification.get("engagement") or {}
    perspectives = engagement.get("perspectives") or []
    if not perspectives:
        primary = classification.get("archetype")
        perspectives = [primary] if primary else []
    roster: list[dict] = []
    for archetype in perspectives[:5]:
        if not archetype:
            continue
        roster.append(
            {
                "archetype": archetype,
                "color_hint": ARCHETYPE_COLOR_HINTS.get(archetype, "neutral"),
                "idle_zone_hint": ARCHETYPE_IDLE_ZONES.get(archetype, "center"),
            }
        )
    return roster


def _blend_best_fit(
    skills_with_scores: list[tuple[str, "MetaSkill", float]],
    depth: int,
    signature_weight: float = SIGNATURE_WEIGHT,
) -> list[tuple[str, "RecipePhase"]]:
    """Award each cognitive_function slot to the best-fit phase.

    slot_score = relevance_score + signature_weight * phase.signature.
    Phases with min_depth > depth are gated out. Winner selection uses
    first-seen-then-strict-greater (an equal slot_score never displaces the
    incumbent). Emission order is CANONICAL (_CANONICAL_FUNCTION_ORDER), not
    first-seen — so e.g. `review` always precedes `critique` regardless of
    which skill's phases were scanned first. Functions outside the canonical
    list (agentic/extension functions) are appended afterward in their
    original first-seen order.
    """
    best_by_function: dict[str, tuple[float, str, "RecipePhase"]] = {}
    function_order: list[str] = []
    for slug, skill, score in skills_with_scores:
        if not skill:
            continue
        for phase in skill.recipe.phases:
            if phase.min_depth > depth:
                continue
            fn = phase.cognitive_function
            slot_score = score + signature_weight * phase.signature
            cur = best_by_function.get(fn)
            if cur is None:
                function_order.append(fn)
                best_by_function[fn] = (slot_score, slug, phase)
            elif slot_score > cur[0]:
                best_by_function[fn] = (slot_score, slug, phase)

    canonical = [fn for fn in _CANONICAL_FUNCTION_ORDER if fn in best_by_function]
    remainder = [fn for fn in function_order if fn not in _CANONICAL_FUNCTION_ORDER]
    emission_order = canonical + remainder
    return [(best_by_function[fn][1], best_by_function[fn][2]) for fn in emission_order]


class CognitiveComposer:
    """Produces a CognitiveComposition from a task classification."""

    def __init__(self) -> None:
        self._classifier = FrameworkClassifier()
        from core.engine.cognition.tool_classifier import ToolClassifier

        self._tool_classifier = ToolClassifier()
        self._recipe_cache: dict[str, MetaSkill] = {}

    def _load_recipe(self, slug: str) -> MetaSkill | None:
        """Load a meta-skill recipe by slug. Cached after first load.

        Resolution order:
          1. _recipe_cache (already resolved)
          2. _RECIPE_YAML (core YAML recipes, parsed at import)
          3. _RECIPE_MODULES (core Python recipes, imported lazily)
          4. _flavor_recipe_module (extension recipes — module path string
             OR MetaSkill object, depending on how the extension registered)
        """
        if slug in self._recipe_cache:
            return self._recipe_cache[slug]
        if slug in _RECIPE_YAML:
            skill = _RECIPE_YAML[slug]
            self._recipe_cache[slug] = skill
            return skill
        module_path = _RECIPE_MODULES.get(slug)
        if module_path is None:
            flavor_value = _flavor_recipe_module(slug)
            if isinstance(flavor_value, MetaSkill):
                self._recipe_cache[slug] = flavor_value
                return flavor_value
            if isinstance(flavor_value, str):
                module_path = flavor_value
        if not module_path:
            return None
        try:
            mod = importlib.import_module(module_path)
            skill = mod.get_meta_skill()
            self._recipe_cache[slug] = skill
            return skill
        except Exception as exc:
            logger.warning("Failed to load recipe for %s: %s", slug, exc)
            return None

    def _select_meta_skills(self, classification: dict[str, Any]) -> list[str]:
        """Select active meta-skill slugs from classification.

        Dispatches to the problem-derived selector when ENABLE_PROBLEM_DERIVED_SELECTION
        is True; otherwise uses the legacy dict-based selector.
        """
        if ENABLE_PROBLEM_DERIVED_SELECTION:
            return self._select_meta_skills_dynamic(classification)
        return self._select_meta_skills_legacy(classification)

    def _select_meta_skills_legacy(self, classification: dict[str, Any]) -> list[str]:
        """Legacy dict-based selection. Preserved for safe rollout; deprecated once
        the dynamic selector is validated and made canonical."""
        discipline = classification.get("discipline", "") or classification.get("domain_path", "")
        task_type = classification.get("task_type", "")
        mode = classification.get("mode", "reactive")

        slugs: list[str] = []

        # Primary domain meta-skill: task_type takes precedence over discipline.
        # Kernel maps first, then extension-contributed routing as a fallback so an
        # extension recipe is selected without the kernel naming it.
        domain_meta = (
            _TASK_TYPE_META.get(task_type)
            or _DISCIPLINE_META.get(discipline)
            or _flavor_recipe_for_classification(task_type, discipline)
        )
        if domain_meta:
            slugs.append(domain_meta)

        # Agentic meta-skills by mode
        for agentic in _AGENTIC_META_BY_MODE.get(mode, ["verification_intelligence"]):
            if agentic not in slugs:
                slugs.append(agentic)

        # Always include domain_specific for discipline-grounded context loading
        if "domain_specific_intelligence" not in slugs:
            slugs.append("domain_specific_intelligence")

        return slugs

    def _rank_meta_skills_dynamic(
        self,
        classification: dict[str, Any],
        threshold: float = 0.45,
        max_skills: int | None = None,
    ) -> list[tuple[str, float]]:
        """Problem-derived meta-skill selection, returning (slug, relevance_score) pairs.

        Queries every meta-skill for its self-described relevance to the task via
        activation_signals + archetype_affinity + mode_affinity + composability,
        then ranks and picks all that exceed the threshold.

        Mirrors the problem-derived selection patterns already used by L2 classifier,
        L4 deep committee resolve_lenses, L5 FrameworkClassifier, L9 reconciler.
        Replaces the hardcoded _TASK_TYPE_META / _DISCIPLINE_META / _AGENTIC_META_BY_MODE
        dicts so extensions and core both compose against the same selection logic.

        max_skills defaults to depth-derived cap so simple/reactive tasks don't
        cascade through every meta-skill in the system.

        Identical selection logic to the prior _select_meta_skills_dynamic; the
        score is now carried out so the composer's best-fit blend can weigh slots.
        """
        task_text = (
            classification.get("description", "")
            or classification.get("task", "")
            or classification.get("task_description", "")
            or ""
        )

        # Depth-derived cap: prevents over-selection on low-depth tasks.
        # Mirrors the depth derivation used elsewhere in the composer.
        if max_skills is None:
            mode = classification.get("mode", "reactive")
            complexity = classification.get("complexity", "moderate")
            depth = derive_depth(mode, complexity)
            max_skills = {1: 4, 2: 5, 3: 7, 4: 8}.get(depth, 6)

        # Enumerate every meta-skill the system knows about: core Python + core YAML + extensions
        all_slugs: set[str] = set(_RECIPE_MODULES.keys()) | set(_RECIPE_YAML.keys())
        try:
            from core.engine.extensions.registry import registered_recipes

            all_slugs |= set(registered_recipes().keys())
        except Exception as exc:
            logger.debug("Extension registry unavailable during dynamic selection: %s", exc)

        # Score every candidate
        candidates: list[tuple[MetaSkill, float]] = []
        for slug in all_slugs:
            ms = self._load_recipe(slug)
            if ms is None:
                continue
            score = _score_meta_skill_relevance(ms, classification, task_text)
            candidates.append((ms, score))

        if not candidates:
            # Substrate-empty fallback: still emit domain_specific so the runtime
            # has something to ground on.
            return [("domain_specific_intelligence", 0.0)]

        # First pass: rank, identify anchor set (top 3 by raw score)
        candidates.sort(key=lambda x: -x[1])
        anchor_slugs = {ms.slug for ms, _ in candidates[:3]}

        # Second pass: composability boost — meta-skills that complement the anchors
        # get a +0.10 boost; ones that conflict with anchors are eliminated.
        boosted: list[tuple[MetaSkill, float]] = []
        anchor_conflicts: set[str] = set()
        for ms, _ in candidates[:3]:
            for conflict in ms.composability.get("conflicts", []) or []:
                anchor_conflicts.add(conflict)

        for ms, s in candidates:
            if ms.slug in anchor_conflicts:
                continue
            adjusted = s
            if ms.slug not in anchor_slugs:
                complements = set(ms.composability.get("complements", []) or [])
                if complements & anchor_slugs:
                    adjusted = min(1.0, s + 0.10)
            boosted.append((ms, adjusted))

        # Third pass: apply threshold, then sort
        above = [(ms, s) for ms, s in boosted if s >= threshold]
        above.sort(key=lambda x: -x[1])

        # Fourth pass: walk in score order, exclude conflicts as we go
        selected: list[tuple[str, float]] = []
        excluded_slugs: set[str] = set()
        for ms, s in above:
            if ms.slug in excluded_slugs:
                continue
            selected.append((ms.slug, s))
            for conflict in ms.composability.get("conflicts", []) or []:
                excluded_slugs.add(conflict)
            if len(selected) >= max_skills:
                break

        # Always include domain_specific for discipline-grounded context loading
        # (matches legacy behavior; safe fallback when nothing else fires)
        if "domain_specific_intelligence" not in {slug for slug, _ in selected}:
            selected.append(("domain_specific_intelligence", 0.0))

        return selected

    def _select_meta_skills_dynamic(
        self,
        classification: dict[str, Any],
        threshold: float = 0.45,
        max_skills: int | None = None,
    ) -> list[str]:
        """Slug-only view of _rank_meta_skills_dynamic (preserves the prior API)."""
        return [slug for slug, _ in self._rank_meta_skills_dynamic(classification, threshold, max_skills)]

    def _selected_with_scores(self, classification: dict[str, Any]) -> tuple[list[str], dict[str, float]]:
        """Selected slugs plus per-task relevance scores for best-fit blending.

        Dynamic path: real relevance scores. Legacy path: synthesized rank-dominant
        scores ((n-i)*100) so best-fit reduces to the legacy first-wins order.
        """
        if ENABLE_PROBLEM_DERIVED_SELECTION:
            ranked = self._rank_meta_skills_dynamic(classification)
            return [s for s, _ in ranked], {s: sc for s, sc in ranked}
        slugs = self._select_meta_skills_legacy(classification)
        n = len(slugs)
        return slugs, {slug: float((n - i) * 100) for i, slug in enumerate(slugs)}

    async def compose(
        self,
        classification: dict[str, Any],
        product_id: str,
    ) -> CognitiveComposition:
        """Produce a CognitiveComposition for a classified task.

        All exceptions are caught — returns a minimal (empty) composition
        that causes ShellComposer to fall back to the pre-cognition behavior.
        """
        try:
            return await self._compose_inner(classification, product_id)
        except Exception as exc:
            # Audit fix (decision:6szaqhgbb55bt20s3b2f): escalate to ERROR with
            # traceback. The fallback to empty composition silently degrades
            # engagement quality — failures must be visible in logs.
            logger.error(
                "CognitiveComposer failed — falling back to pre-cognition behavior: %s",
                exc,
                exc_info=True,
            )
            return CognitiveComposition(
                meta_skills=[],
                depth=1,
                active_phases=[],
                resolved_instruments={},
                prompt_sections=[],
                fusion_mode=True,
                roster=_build_roster(classification),
            )

    async def _compose_inner(
        self,
        classification: dict[str, Any],
        product_id: str,
    ) -> CognitiveComposition:
        mode = classification.get("mode", "reactive")
        complexity = classification.get("complexity", "moderate")
        discipline = classification.get("discipline", "") or classification.get("domain_path", "")
        task_type = classification.get("task_type", "")

        depth = derive_depth(mode, complexity)
        fusion_mode = depth <= 2

        meta_skill_slugs, meta_skill_scores = self._selected_with_scores(classification)

        # Recipe depth override (unchanged): raise depth to any skill's min_execution_depth
        for slug in meta_skill_slugs:
            skill = self._load_recipe(slug)
            if skill and skill.min_execution_depth > depth:
                depth = skill.min_execution_depth
                fusion_mode = depth <= 2

        # Best-fit-per-slot: each cognitive_function goes to the highest slot_score phase.
        skills_with_scores = [
            (slug, self._load_recipe(slug), meta_skill_scores.get(slug, 0.0)) for slug in meta_skill_slugs
        ]
        all_phases_with_skill = _blend_best_fit(
            [(slug, skill, score) for slug, skill, score in skills_with_scores if skill],
            depth,
        )
        all_phases = [phase for _, phase in all_phases_with_skill]

        # Resolve instruments for each active phase
        resolved: dict[str, list[str]] = {}
        resolved_tools: dict[str, list[str]] = {}
        prompt_sections: list[dict] = []

        for i, (meta_skill_slug, phase) in enumerate(all_phases_with_skill):
            slugs_for_phase: list[str] = []
            for inst in phase.instruments:
                resolved_slug = await self._classifier.resolve_instrument(
                    spec=inst,
                    task_type=task_type,
                    discipline=discipline,
                    product_id=product_id,
                    cognitive_function=phase.cognitive_function,
                    meta_skill=meta_skill_slug,
                )
                slugs_for_phase.append(resolved_slug)

            resolved[str(i)] = slugs_for_phase

            tool_slugs_for_phase: list[str] = []
            for tspec in phase.tools:
                resolved_tool = await self._tool_classifier.resolve_tool(
                    spec=tspec,
                    task_type=task_type,
                    discipline=discipline,
                    product_id=product_id,
                    cognitive_function=phase.cognitive_function,
                    meta_skill=meta_skill_slug,
                )
                tool_slugs_for_phase.append(resolved_tool)
            resolved_tools[str(i)] = tool_slugs_for_phase

            prompt_sections.append(
                {
                    "phase_idx": str(i),
                    "cognitive_function": phase.cognitive_function,
                    "framework_slugs": slugs_for_phase,
                    "tool_slugs": tool_slugs_for_phase,
                    "output_schema": phase.output_schema,
                    "pattern": phase.pattern,
                    "fusion_label": f"[{phase.cognitive_function.upper()}]",
                }
            )

        # Loop context — prior decisions and archetype calibration loaded by the
        # orchestration layer (fail-open, stateless from the composer's perspective).
        # Design rule: decision lines are suppressed ONLY when the shell will
        # actually render them — i.e., recent_decisions is present AND this is a
        # fused (depth 1-2) composition, where ShellComposer._build_layer5_section
        # appends the "## Prior Decisions" block. On the deep path (depth 3-4,
        # MultiPhaseExecutor) the shell never runs, so the composer must render
        # decisions itself even when recent_decisions is present. Accepted
        # trade-off: duplicate rendering on the rare multiphase-failure →
        # shell-fallback path. Calibration is always rendered because nothing
        # else in the prompt pipeline surfaces it.
        loop_ctx = classification.get("loop_context") or {}
        if loop_ctx:
            lines: list[str] = []
            recent_decisions_present = bool(classification.get("recent_decisions")) and fusion_mode
            if not recent_decisions_present:
                for d in loop_ctx.get("prior_decisions", []):
                    lines.append(f"- Prior decision: {d['title']} ({d['decision_type']}) — {d['rationale']}")
            for archetype, cal in (loop_ctx.get("calibration") or {}).items():
                lines.append(
                    f"- Calibration: {archetype} has scored {cal['score']:.2f} over"
                    f" {cal['samples']} closed predictions in this discipline"
                )
            if lines:
                closing = (
                    "Weigh these: do not re-litigate settled decisions without naming why; "
                    "lean on archetypes with stronger calibration."
                    if not recent_decisions_present
                    else "Lean on archetypes with stronger calibration."
                )
                prompt_sections.append(
                    {
                        "title": "What we already know",
                        "body": "\n".join(lines) + "\n" + closing,
                    }
                )

        composition = CognitiveComposition(
            meta_skills=meta_skill_slugs,
            depth=depth,
            active_phases=all_phases,
            resolved_instruments=resolved,
            prompt_sections=prompt_sections,
            fusion_mode=fusion_mode,
            roster=_build_roster(classification),
            max_tokens_per_phase=classification.get("token_budget"),
            loop_context=loop_ctx,
            resolved_tools=resolved_tools,
        )

        # Composition visibility: emit a canvas event so the orchestra becomes
        # legible. Renders on the Living Canvas as "which intelligences are
        # weighing in" for this task. Fire-and-forget; failure does not block
        # the composition return.
        try:
            from core.engine.events.canvas import emit_composition_selected

            await emit_composition_selected(
                product_id=product_id,
                meta_skills=meta_skill_slugs,
                depth=depth,
                fusion_mode=fusion_mode,
                classification=classification,
            )
        except Exception as exc:
            logger.debug("composition.selected emit failed (non-fatal): %s", exc)

        # Cache the composition snapshot for introspection consumers (MCP
        # ace_active_composition tool, canvas refresh, AI partner queries).
        _recent_compositions[product_id] = {
            "meta_skills": list(meta_skill_slugs),
            "depth": depth,
            "fusion_mode": fusion_mode,
            "classification": {
                "task_type": classification.get("task_type", ""),
                "discipline": classification.get("discipline", ""),
                "mode": classification.get("mode", ""),
                "archetype": classification.get("archetype", ""),
                "complexity": classification.get("complexity", ""),
            },
            "phases": [p.cognitive_function for p in all_phases],
        }

        return composition

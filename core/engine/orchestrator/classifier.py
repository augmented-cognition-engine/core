# engine/orchestrator/classifier.py
"""Classify a task description into discipline, archetype, mode, and complexity."""

from __future__ import annotations

import logging
import re

from core.engine.cognition.handoff import should_handoff
from core.engine.core.config import settings
from core.engine.core.llm import llm

logger = logging.getLogger(__name__)

DISCIPLINES = [
    "security",
    "testing",
    "ux",
    "performance",
    "devops",
    "data",
    "accessibility",
    "documentation",
    "ai_ml",
    "architecture",
    "api_design",
    "data_modeling",
    "business_logic",
    "integration",
    "product_strategy",
    "error_handling",
    "observability",
    "configuration",
    "deployment",
    "versioning",
    "scale",
    "code_conventions",
    "dependency_management",
    "marketing",
]

ARCHETYPES = {"creator", "analyst", "executor", "researcher", "advisor", "sentinel"}
MODES = {"deliberative", "reactive", "exploratory", "conversational", "procedural", "reflective"}
COMPLEXITIES = {"simple", "moderate", "complex", "ambiguous"}
PERSPECTIVES = {"theorist", "practitioner", "strategist", "operator"}

# Engagement slots accept both legacy perspective names and archetype names.
# Archetype names are preferred for new call sites; perspective names are
# accepted for backward compat.  Both sets are valid values in the
# ``engagement.perspectives`` list.
ENGAGEMENT_SLOTS = PERSPECTIVES | ARCHETYPES

TASK_TYPES = {
    "debug",
    "implement",
    "plan",
    "review",
    "explain",
    "analyze",
    "verify",
    "design",
    "research",
    "write",
}

QUALITY_BARS = {"draft", "production", "critical"}

_DEFAULT = {
    "discipline": "architecture",
    "discipline_confidence": 0.5,
    "archetype": "executor",
    "archetype_confidence": 0.5,
    "mode": "deliberative",  # safer default: activates multi-phase reasoning on parse failures
    "mode_confidence": 0.5,
    "perspective": "practitioner",
    "perspective_confidence": 0.5,
    "complexity": "moderate",  # safer default: avoids depth:1 short-circuit on ambiguous tasks
    "complexity_confidence": 0.5,
    "task_type": "analyze",
    "task_type_confidence": 0.5,
    "quality_bar": "production",
    "quality_bar_confidence": 0.5,
    "specialties": [],
    "org_context": [],
    "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
    "token_budget": 2048,
}


def _to_kebab(s: str) -> str:
    """Convert a string to kebab-case."""
    s = s.strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s


def _clip_confidence(value: object, default: float = 0.7) -> float:
    """Clip a confidence value to [0.0, 1.0]; return default if missing or invalid."""
    try:
        f = float(value)  # type: ignore[arg-type]
        if not (0.0 <= f <= 1.0):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _validate_engagement(engagement: dict | None, primary_perspective: str) -> dict:
    """Validate and sanitize the engagement object.

    ``perspectives`` may contain either legacy perspective names
    (theorist, strategist, practitioner, operator) or archetype names
    (creator, analyst, executor, researcher, advisor, sentinel).  Both are
    valid; archetype names are preferred for new classifier outputs.
    """
    if not engagement or not isinstance(engagement, dict):
        return {"perspectives": [primary_perspective], "adversarial_pair": None, "rationale": ""}

    perspectives = engagement.get("perspectives", [])
    if not isinstance(perspectives, list) or not perspectives:
        perspectives = [primary_perspective]
    # Accept both perspective names (backward compat) and archetype names (preferred)
    perspectives = [p for p in perspectives if p in ENGAGEMENT_SLOTS][:4]
    if not perspectives:
        perspectives = [primary_perspective]

    adversarial_pair = engagement.get("adversarial_pair")
    if adversarial_pair:
        if not isinstance(adversarial_pair, list) or len(adversarial_pair) != 2:
            adversarial_pair = None
        elif "operator" in adversarial_pair:
            # operator never debates — they coordinate after decisions are made
            adversarial_pair = None
        elif not all(p in ENGAGEMENT_SLOTS for p in adversarial_pair):
            adversarial_pair = None
        elif not all(p in perspectives for p in adversarial_pair):
            adversarial_pair = None

    return {
        "perspectives": perspectives,
        "adversarial_pair": adversarial_pair,
        "rationale": str(engagement.get("rationale", ""))[:500],
    }


def _validate(result: dict) -> dict:
    """Validate and sanitize classifier output. Defaults invalid values."""
    discipline = result.get("discipline", "architecture")
    if discipline not in DISCIPLINES:
        discipline = "architecture"
    discipline_confidence = _clip_confidence(result.get("discipline_confidence"))

    archetype = result.get("archetype")
    archetype = archetype if archetype in ARCHETYPES else "executor"
    archetype_confidence = _clip_confidence(result.get("archetype_confidence"))

    mode = result.get("mode")
    mode = mode if mode in MODES else "reactive"
    mode_confidence = _clip_confidence(result.get("mode_confidence"))

    complexity = result.get("complexity")
    complexity = complexity if complexity in COMPLEXITIES else "simple"
    complexity_confidence = _clip_confidence(result.get("complexity_confidence"))

    perspective = result.get("perspective")
    perspective = perspective if perspective in PERSPECTIVES else "practitioner"
    perspective_confidence = _clip_confidence(result.get("perspective_confidence"))

    task_type = result.get("task_type")
    task_type = task_type if task_type in TASK_TYPES else "implement"
    task_type_confidence = _clip_confidence(result.get("task_type_confidence"))

    quality_bar = result.get("quality_bar")
    quality_bar = quality_bar if quality_bar in QUALITY_BARS else "production"
    quality_bar_confidence = _clip_confidence(result.get("quality_bar_confidence"))

    raw_specialties = result.get("specialties", [])
    if not isinstance(raw_specialties, list):
        raw_specialties = []
    specialties = [_to_kebab(s) for s in raw_specialties if isinstance(s, str) and s.strip()][:3]

    raw_org_context = result.get("org_context", [])
    if not isinstance(raw_org_context, list):
        raw_org_context = []
    org_context = [str(s) for s in raw_org_context][:5]

    engagement = _validate_engagement(result.get("engagement"), perspective)

    return {
        "discipline": discipline,
        "discipline_confidence": discipline_confidence,
        "archetype": archetype,
        "archetype_confidence": archetype_confidence,
        "mode": mode,
        "mode_confidence": mode_confidence,
        "complexity": complexity,
        "complexity_confidence": complexity_confidence,
        "perspective": perspective,
        "perspective_confidence": perspective_confidence,
        "task_type": task_type,
        "task_type_confidence": task_type_confidence,
        "quality_bar": quality_bar,
        "quality_bar_confidence": quality_bar_confidence,
        "specialties": specialties,
        "org_context": org_context,
        "engagement": engagement,
    }


async def _load_specialty_catalog(product_id: str) -> str:
    """Load available specialties from DB for the given org.

    Best-effort: returns empty string on any failure.
    """
    try:
        from core.engine.core.db import parse_rows, pool

        async with pool.connection() as conn:
            rows = parse_rows(
                await conn.query(
                    "SELECT slug, description, perspective FROM specialty WHERE product = <string>$product_id LIMIT 50",
                    {"product_id": product_id},
                )
            )
        if not rows:
            return ""
        lines = [f"  - {r['slug']}: {r.get('description', '')} (perspective: {r.get('perspective', '')})" for r in rows]
        return "Available specialties:\n" + "\n".join(lines)
    except Exception as exc:
        logger.debug("_load_specialty_catalog failed (best-effort): %s", exc)
        return ""


def _load_discipline_catalog() -> str:
    """Load available disciplines."""
    from core.engine.product.seed_packs import ALL_DISCIPLINES

    return "Available disciplines:\n" + "\n".join(f"  - {d}" for d in ALL_DISCIPLINES)


async def _load_routing_corrections(product_id: str, limit: int = 8) -> str:
    """Load recent explicit routing corrections for this product.

    Returns a formatted string of "avoid this routing / use this instead" examples,
    injected into the classifier prompt as dynamic few-shot examples.
    Best-effort: returns empty string on any failure.
    """
    try:
        from core.engine.core.db import parse_rows, pool

        async with pool.connection() as conn:
            rows = parse_rows(
                await conn.query(
                    """
                    SELECT task_summary, wrong_discipline, wrong_mode, wrong_archetype,
                           correct_discipline, correct_mode, correct_archetype, reason, created_at
                    FROM routing_correction
                    WHERE product = <string>$product_id
                    ORDER BY created_at DESC
                    LIMIT $limit
                    """,
                    {"product_id": product_id, "limit": limit},
                )
            )
        if not rows:
            return ""
        lines = ["Learned routing corrections (do NOT repeat these mistakes):"]
        for r in rows:
            wrong = f"{r.get('wrong_discipline')}/{r.get('wrong_archetype')}/{r.get('wrong_mode')}"
            correct = f"{r.get('correct_discipline')}/{r.get('correct_archetype')}/{r.get('correct_mode')}"
            summary = r.get("task_summary", "")
            reason = r.get("reason", "")
            lines.append(f'  - Task like "{summary}": was routed {wrong} → correct is {correct}. {reason}')
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("_load_routing_corrections failed (best-effort): %s", exc)
        return ""


async def record_routing_correction(
    product_id: str,
    task_summary: str,
    wrong_discipline: str,
    wrong_mode: str,
    wrong_archetype: str,
    correct_discipline: str,
    correct_mode: str,
    correct_archetype: str,
    reason: str = "",
) -> bool:
    """Record an explicit routing correction. Returns True on success.

    Called when a task was misrouted and the correct classification is known.
    These corrections are injected as dynamic few-shot examples in future calls.
    """
    try:
        from core.engine.core.db import pool

        async with pool.connection() as conn:
            await conn.query(
                """
                CREATE routing_correction SET
                    product = <string>$product_id,
                    task_summary = $task_summary,
                    wrong_discipline = $wrong_discipline,
                    wrong_mode = $wrong_mode,
                    wrong_archetype = $wrong_archetype,
                    correct_discipline = $correct_discipline,
                    correct_mode = $correct_mode,
                    correct_archetype = $correct_archetype,
                    reason = $reason,
                    created_at = time::now()
                """,
                {
                    "product_id": product_id,
                    "task_summary": task_summary[:200],
                    "wrong_discipline": wrong_discipline,
                    "wrong_mode": wrong_mode,
                    "wrong_archetype": wrong_archetype,
                    "correct_discipline": correct_discipline,
                    "correct_mode": correct_mode,
                    "correct_archetype": correct_archetype,
                    "reason": reason[:500],
                },
            )
        logger.info(
            "routing_correction recorded: %s → %s/%s/%s",
            task_summary[:60],
            correct_discipline,
            correct_archetype,
            correct_mode,
        )
        return True
    except Exception as exc:
        logger.warning("record_routing_correction failed: %s", exc)
        return False


async def classify_task(description: str, product_id: str = "product:default") -> dict:
    """Return classification dict for a task.

    Returns: {
        "discipline", "discipline_confidence",
        "archetype", "archetype_confidence",
        "mode", "mode_confidence",
        "complexity", "complexity_confidence",
        "perspective", "perspective_confidence",
        "task_type", "task_type_confidence",
        "quality_bar", "quality_bar_confidence",
        "specialties", "org_context", "engagement"
    }
    """
    try:
        specialty_catalog = await _load_specialty_catalog(product_id)
        discipline_catalog = _load_discipline_catalog()
        routing_corrections = await _load_routing_corrections(product_id)

        catalog_section = ""
        if specialty_catalog:
            catalog_section += f"\n{specialty_catalog}\n"
        if discipline_catalog:
            catalog_section += f"\n{discipline_catalog}\n"

        result = await llm.complete_json(
            f"""Classify this task across ten dimensions. For every field also emit a confidence score (0.0–1.0).

Task: {description}
{catalog_section}
Dimensions:
1. discipline — one of: {", ".join(DISCIPLINES)}. Pick the discipline that best captures the DOMAIN of the task:
   - product_strategy: product-market fit, roadmap prioritization, competitive positioning, market analysis, pricing strategy, growth loops, retention mechanics, go-to-market — USE THIS when the task is about WHAT to build or WHY, not HOW
   - business_logic: business rules encoded in software — rules engines, validation logic, domain invariants, pricing calculations in code, workflow state machines
   - architecture: designing software systems, components, modules, technical structure
   - security: vulnerabilities, auth, data protection, secrets, compliance
   - testing: test coverage, quality assurance, test strategy, regression
   - performance: latency, throughput, optimization, profiling
   - api_design: endpoint contracts, REST/GraphQL design, API versioning
   - data_modeling: schema design, entity relationships, database structure
   - observability: logging, metrics, tracing, alerting
   - devops: CI/CD, infrastructure, automation pipelines
   - For all other disciplines use the closest match from: {", ".join(DISCIPLINES)}
2. archetype — the type of work:
   - creator: building something NEW that doesn't exist yet — writing new code, tests, endpoints, schemas, documentation, even when the spec is clear
   - analyst: analyzing information, producing insights, diagnosing issues
   - executor: running an EXISTING process precisely — applying a migration, running a script, following an exact checklist; NOT for writing new code
   - researcher: investigating, gathering information, exploration — "explain", "walk me through", "how does X work"
   - advisor: recommending a decision or course of action — USE THIS for strategy, tradeoff, or "what should we do" questions
   - sentinel: monitoring, reviewing, flagging issues (code review, security audit, quality check)
3. mode — how to approach the problem:
   - deliberative: multi-step reasoning required, alternatives must be weighed, high-stakes decisions, complex tradeoffs, unfamiliar domains — USE THIS for business strategy, architecture decisions, and any "what should we do" question with real consequences
   - reactive: fast pattern-match, answer is well-known, single direct step (e.g., "write X", "add Y", "fix Z" with clear spec)
   - exploratory: broad investigation, divergent thinking, "walk me through", "explain", "how does X work", "find issues in Y"
   - conversational: ONLY when the task is genuinely ambiguous and cannot proceed without answers — do NOT use for "explain" or "walk me through" requests
   - procedural: follow a defined checklist or process step-by-step
   - reflective: self-assessing, evaluating quality of prior work
4. complexity — simple (one-step, clear) | moderate (multi-step or ambiguous) | complex (cross-domain, multi-phase, high stakes) | ambiguous (needs clarification before proceeding)
5. perspective — the knowledge stance best suited to this task:
   - theorist: conceptual, first-principles, research-oriented
   - practitioner: hands-on, implementation-focused, experienced
   - strategist: big-picture, planning, alignment-focused
   - operator: process-driven, execution-focused, reliability-oriented
6. task_type — the nature of what is being asked:
   - debug: finding and fixing bugs, errors, unexpected behavior
   - implement: writing new code, features, functions
   - plan: decomposing work, sequencing, roadmapping
   - review: evaluating code, PRs, designs, decisions
   - explain: understanding existing code, concepts, systems
   - analyze: investigating data, metrics, patterns, tradeoffs — USE THIS for strategy and advisory questions
   - verify: checking correctness, running tests, validating
   - design: architecture decisions, system design, API contracts
   - research: gathering information, exploring options
   - write: documentation, specs, proposals, content
7. quality_bar — the expected output quality:
   - draft: exploratory output, speed over correctness
   - production: correct, tested, ready to ship
   - critical: high-stakes, security/compliance/data-loss risk
8. specialties — list of up to 3 relevant specialty slugs from the catalog above (kebab-case, empty list if none apply)
9. org_context — list of up to 5 short strings describing relevant organisational context clues in the task (empty list if none)
10. engagement — how many perspective slots this task needs and in what order:
   - For simple/clear tasks: just one slot (e.g., ["executor"])
   - For tasks needing grounding then implementation: ["analyst", "executor"]
   - For tasks needing validation: build first, then sentinel reviews
   - For high-stakes decisions: adversarial pairing (e.g., ["creator", "sentinel"])
   Prefer archetype names: creator, analyst, executor, researcher, advisor, sentinel.
   Legacy perspective names (theorist, strategist, practitioner, operator) are also
   accepted for backward compatibility.
   Operator/executor never debates — they coordinate after decisions are made.
   Return engagement as: {{"perspectives": ["..."], "adversarial_pair": null or ["a","b"], "rationale": "why"}}

Examples (use these as anchors):
- "Our B2B SaaS has 60% monthly churn, 8 months runway, 40 customers. What should we focus on?"
  → discipline:product_strategy, archetype:advisor, mode:deliberative, complexity:complex, task_type:analyze, perspective:strategist
- "Write a pytest fixture for mocking the database connection pool"
  → discipline:testing, archetype:executor, mode:reactive, complexity:simple, task_type:implement, perspective:practitioner
- "Our /auth/refresh endpoint is returning 500 intermittently — help me diagnose it"
  → discipline:api_design, archetype:analyst, mode:exploratory, complexity:moderate, task_type:debug, perspective:practitioner
- "Review this PR for security issues before we merge to main"
  → discipline:security, archetype:sentinel, mode:reflective, complexity:moderate, task_type:review, perspective:practitioner
- "Design the schema for a multi-tenant workspace permission system"
  → discipline:data_modeling, archetype:creator, mode:deliberative, complexity:complex, task_type:design, perspective:strategist
{routing_corrections}
Return JSON with per-field confidence scores (0.0–1.0 floats):
{{
  "discipline": "...", "discipline_confidence": 0.9,
  "task_type": "...", "task_type_confidence": 0.9,
  "quality_bar": "...", "quality_bar_confidence": 0.8,
  "archetype": "...", "archetype_confidence": 0.85,
  "mode": "...", "mode_confidence": 0.8,
  "complexity": "...", "complexity_confidence": 0.75,
  "perspective": "...", "perspective_confidence": 0.8,
  "specialties": [], "org_context": [],
  "engagement": {{"perspectives": ["..."], "adversarial_pair": null, "rationale": "..."}}
}}""",
            model=settings.llm_budget_model,
        )
        validated = _validate(result)

        # TALE per-task token budget — derived from validated complexity + mode.
        from core.engine.orchestrator.budgets import estimate_token_budget

        validated["token_budget"] = estimate_token_budget(validated)

        # Low-confidence guard: if mode_confidence < 0.5, override reactive → deliberative.
        # Rationale: reactive forces depth:1 → fusion_mode=True, silently killing multi-phase
        # reasoning. Deliberative activates multi-phase and produces output even on misrouted tasks.
        mode_conf = validated.get("mode_confidence", 1.0)
        if mode_conf < 0.5 and validated["mode"] == "reactive":
            validated["mode"] = "deliberative"
            logger.info(
                "classify_task: low mode_confidence=%.2f — overriding reactive→deliberative for safety",
                mode_conf,
            )

        fire, tool = should_handoff(validated)
        validated["handoff_recommended"] = fire
        validated["suggested_external_tool"] = tool

        return validated
    except Exception as e:
        logger.warning("classify_task failed: %s", e)
        return dict(_DEFAULT)


# -----------------------------------------------------------------------------
# Layer 5 — precedent tie-breaker (decision:lv6stu70piemfwypde2e §6.4)
# -----------------------------------------------------------------------------


def apply_precedent_tiebreaker(
    classifier_output: dict,
    classification: dict,
    task_meta: dict | None = None,
    *,
    confidence_threshold: float = 0.6,
) -> dict:
    """Apply precedent-routing tie-breaker to a classifier output.

    Spec §6.4: when the classifier's `discipline_confidence` is low AND
    `classification['recent_decisions']` contains at least one capability-tier
    decision with a discipline_hint, override the classifier's discipline
    field with the precedent's hint.

    TODO-12 multi-turn guardrail: if the same precedent decision_id appears
    in `task_meta['tiebreaker_history_last_turn']`, skip — don't re-fire the
    same precedent across consecutive turns, otherwise the system can ossify
    a weak classification into the wrong steady state.

    Scope deliberately narrow:
      - Only `discipline` is overridden. Mode/archetype/perspective stay with
        the classifier because TieredDecision doesn't carry those fields
        directly — deriving them from decision content is speculative.
      - High-confidence (>= confidence_threshold) classifications are
        never touched. This is strictly additive.
      - Mutating archive: returns a new dict; never edits the input.
    """
    output = dict(classifier_output)  # copy — never mutate caller's dict
    if output.get("discipline_confidence", 1.0) >= confidence_threshold:
        return output

    recent = classification.get("recent_decisions") or []
    cap_tier = [d for d in recent if getattr(d, "tier", None) == "capability"]
    if not cap_tier:
        return output

    # Highest-relevance capability-tier decision (the loader already sorted).
    top = cap_tier[0]
    top_id = getattr(top, "decision_id", None) or ""
    hint = getattr(top, "discipline_hint", None)
    if not hint or not top_id:
        return output

    # Multi-turn guard — if last turn's tie-breaker used this same precedent,
    # don't fire again. The classifier needs fresh signal, not echo.
    last_turn = (task_meta or {}).get("tiebreaker_history_last_turn") or []
    if top_id in last_turn:
        return output

    # Apply: override discipline, record precedent id for observability and
    # to feed forward into the next turn's guard.
    output["discipline"] = hint
    output["discipline_tiebreaker"] = top_id
    history = list(output.get("tiebreaker_history", []))
    history.append(top_id)
    output["tiebreaker_history"] = history
    logger.info(
        "classifier.precedent_tiebreaker discipline_conf=%.2f override=%s precedent=%s",
        output.get("discipline_confidence", 0.0),
        hint,
        top_id,
    )
    return output

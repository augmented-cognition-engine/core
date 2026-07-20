# engine/skills/selector.py
"""Skill selector — match task classification against skill activation signals.

Uses keyword overlap between the task description + classification fields
and each skill's activation_signals list. Returns the best match above
a threshold, or None (triggering vanilla execution).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.engine.core.db import pool
from core.engine.skills.models import Job, Phase, Skill, SkillMatch, Slot

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.3


def _tokenize(text: str) -> set[str]:
    """Extract lowercase keyword tokens from text."""
    return set(re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text.lower()))


def score_skill(
    skill: Skill,
    description_tokens: set[str],
    discipline: str,
    specialties: list[str] | None = None,
) -> SkillMatch | None:
    """Score a skill against task tokens, discipline, and specialties.

    Scoring:
    - Each matched activation signal adds 1/len(signals) to the score
    - Discipline match adds 0.2 bonus
    - Specialty overlap adds 0.2 bonus
    - Returns None if below MATCH_THRESHOLD
    """
    if not skill.activation_signals:
        return None

    matched = []
    for signal in skill.activation_signals:
        signal_tokens = _tokenize(signal)
        if signal_tokens & description_tokens:
            matched.append(signal)

    if not matched:
        return None

    score = len(matched) / len(skill.activation_signals)

    # Discipline match bonus
    skill_discipline = skill.effective_discipline
    if skill_discipline and discipline and skill_discipline == discipline:
        score += 0.2

    # Specialty overlap bonus
    if specialties and skill_discipline:
        skill_tokens = _tokenize(skill_discipline)
        for spec in specialties:
            if skill_tokens & _tokenize(spec):
                score += 0.1
                break

    if score < MATCH_THRESHOLD:
        return None

    return SkillMatch(skill=skill, score=min(1.0, score), matched_signals=matched)


async def select_skill(
    classification: dict[str, Any],
    product_id: str,
    description: str = "",
) -> SkillMatch | None:
    """Select the best matching skill for a task classification.

    Queries both built-in skills (org IS NONE) and org-specific skills.
    Returns the highest-scoring match above threshold, or None.
    """
    discipline = classification.get("discipline", "") or classification.get("domain_path", "")
    description_tokens = _tokenize(description)

    # Add classification fields to the token set
    description_tokens |= _tokenize(classification.get("archetype", ""))
    description_tokens |= _tokenize(classification.get("mode", ""))
    description_tokens |= _tokenize(discipline)
    for spec in classification.get("specialties", []):
        description_tokens |= _tokenize(spec)

    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT *
            FROM skill
            WHERE product IS NONE OR product = <record>$product
            """,
            {"product": product_id},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])

    if not rows:
        return None

    best_match: SkillMatch | None = None

    for row in rows:
        # Support both new Phase format and legacy Job format
        phases_data = row.get("phases", [])
        jobs_data = row.get("jobs", row.get("steps", []))

        phases = []
        if phases_data:
            for p in phases_data:
                if isinstance(p, dict):
                    slots = [Slot(**s) if isinstance(s, dict) else s for s in p.get("slots", [])]
                    phases.append(
                        Phase(
                            name=p.get("name", ""),
                            pattern=p.get("pattern", "solo"),
                            slots=slots,
                            aggregation=p.get("aggregation", "last"),
                            termination=p.get("termination", "single"),
                            output_format=p.get("output_format", "prose"),
                            description=p.get("description", ""),
                        )
                    )

        jobs = []
        if not phases and jobs_data:
            jobs = [Job(**j) if isinstance(j, dict) else j for j in jobs_data]

        skill = Skill(
            slug=row.get("slug", ""),
            name=row.get("name", ""),
            description=row.get("description", ""),
            discipline=row.get("discipline") or row.get("domain_path"),
            domain_path=row.get("domain_path"),
            tier=row.get("tier", "built-in"),
            phases=phases,
            jobs=jobs,
            activation_signals=row.get("activation_signals", []),
        )

        specialties = classification.get("specialties", [])
        match = score_skill(skill, description_tokens, discipline, specialties)
        if match and (best_match is None or match.score > best_match.score):
            best_match = match

    if best_match:
        logger.info(
            f"Skill selected: {best_match.skill.slug} "
            f"(score={best_match.score:.2f}, signals={best_match.matched_signals})"
        )

    return best_match

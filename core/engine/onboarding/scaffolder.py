"""Onboarding specialty scaffolder — generates specialties from a role description.

Detects zero-specialty/zero-project state and scaffolds appropriate expertise areas
using LLM classification. Disciplines are resolved to record IDs.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import parse_record_id, parse_rows, pool
from core.engine.core.llm import llm
from core.engine.orchestrator.specialty_resolver import PERSPECTIVES, find_similar_slug
from core.engine.product.seed_packs import get_disciplines_for_product_type

logger = logging.getLogger(__name__)

_MAX_SPECIALTIES = 20
_MIN_SPECIALTIES = 3


async def needs_onboarding(product_id: str) -> bool:
    """Check if this org needs onboarding (no projects AND no non-best-practice specialties)."""
    async with pool.connection() as db:
        proj_rows = parse_rows(
            await db.query(
                "SELECT count() AS c FROM project WHERE product = <record>$product GROUP ALL",
                {"product": product_id},
            )
        )
        has_projects = proj_rows and proj_rows[0].get("c", 0) > 0

        spec_rows = parse_rows(
            await db.query(
                "SELECT count() AS c FROM specialty WHERE product = <record>$product"
                " AND status IN ['active', 'scaffolded', 'proposed']"
                " AND tags NOT CONTAINS 'best_practice' GROUP ALL",
                {"product": product_id},
            )
        )
        has_specialties = spec_rows and spec_rows[0].get("c", 0) > 0

        return not has_projects and not has_specialties


async def needs_project_setup(product_id: str) -> bool:
    """Check if this org has any projects."""
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT count() AS c FROM project WHERE product = <record>$product GROUP ALL",
                {"product": product_id},
            )
        )
        return not rows or rows[0].get("c", 0) == 0


async def scaffold_project(description: str, product_id: str, repo_path: str = None) -> dict:
    """Create a project from a description of what the user is building.

    1. LLM extracts: name, slug, product_type, description
    2. Create project record
    3. Activate appropriate disciplines
    4. Return project dict
    """
    try:
        result = await llm.complete_json(
            f'''The user describes what they're building:
"{description}"

Determine:
- name: human-readable project name
- slug: snake_case identifier
- product_type: one of "web", "api", "mobile", "cli", "library"
- description: one sentence describing what this product does

Return JSON: {{"name": "...", "slug": "...", "product_type": "...", "description": "..."}}''',
            model=settings.llm_model,
        )
    except Exception as exc:
        logger.error("scaffold_project LLM failed: %s", exc)
        return {}

    if not isinstance(result, dict) or "slug" not in result:
        return {}

    slug = result["slug"].strip().lower().replace("-", "_").replace(" ", "_")
    product_type = result.get("product_type", "web")

    # Get active disciplines for this product type
    active_disciplines = get_disciplines_for_product_type(product_type)

    async with pool.connection() as db:
        # Create project
        proj_result = await db.query(
            """CREATE project SET
                name = $name,
                slug = $slug,
                description = $description,
                repo_path = $repo_path,
                product_type = $product_type,
                active_disciplines = $disciplines""",
            {
                "product": product_id,
                "name": result.get("name", slug),
                "slug": slug,
                "description": result.get("description", ""),
                "repo_path": repo_path or "",
                "product_type": product_type,
                "disciplines": active_disciplines,
            },
        )
        project = parse_rows(proj_result)

        # Activate disciplines
        for disc in active_disciplines:
            await db.query(
                """CREATE active_discipline SET
                    discipline = $disc,
                    active = true,
                    reason = 'onboarding'""",
                {"product": product_id, "disc": disc},
            )

    created = project[0] if project else result
    logger.info(
        "Scaffolded project '%s' (%s) with %d disciplines for %s",
        slug,
        product_type,
        len(active_disciplines),
        product_id,
    )
    return created


def _validate_scaffolded_specialties(specs: list[dict]) -> list[dict]:
    """Validate and sanitise LLM-generated specialty list.

    - Deduplicate by slug (first occurrence wins).
    - Default invalid perspective to 'practitioner'.
    - Default invalid priority to 'adjacent'.
    - Cap at _MAX_SPECIALTIES (20).
    """
    if not specs:
        return []

    seen_slugs: set[str] = set()
    unique: list[dict] = []

    for s in specs:
        slug = s.get("slug", "").strip().lower()
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        perspective = s.get("perspective", "practitioner")
        if perspective not in PERSPECTIVES:
            perspective = "practitioner"

        priority = s.get("priority", "adjacent")
        if priority not in ("core", "adjacent"):
            priority = "adjacent"

        unique.append({**s, "slug": slug, "perspective": perspective, "priority": priority})

    return unique[:_MAX_SPECIALTIES]


async def scaffold_specialties(role_description: str, product_id: str) -> list[dict]:
    """Generate and create specialties from a role description.

    1. Queries available disciplines to build the LLM prompt.
    2. Fetches existing specialty slugs for similarity checking.
    3. Calls LLM (settings.llm_model — one-time important call).
    4. Validates and deduplicates the returned specs.
    5. Skips specs too similar to existing specialties.
    6. Creates accepted specs in DB with status='scaffolded'.

    Returns the list of created specialty dicts (each includes 'id').
    """
    async with pool.connection() as db:
        disc_rows = parse_rows(await db.query("SELECT id, slug FROM discipline"))
        disc_map: dict[str, str] = {d["slug"]: d["id"] for d in disc_rows}
        disc_slugs = (
            ", ".join(disc_map.keys()) if disc_map else "sciences, engineering, business, design, humanities, markets"
        )

        existing = parse_rows(
            await db.query(
                "SELECT slug FROM specialty WHERE product = <record>$product",
                {"product": product_id},
            )
        )
        existing_slugs: list[str] = [s["slug"] for s in existing if "slug" in s]

    # LLM call — use full model (this is a one-time important call)
    try:
        result = await llm.complete_json(
            f"""The user describes their role:
"{role_description}"

Available disciplines: {disc_slugs}

Generate specialties for this person. For each specialty:
- slug: kebab-case identifier
- name: human-readable name
- description: 1-2 sentence description of what knowledge this covers
- perspective: theorist | practitioner | strategist | operator
- discipline: which discipline from the list above
- priority: core (primary work) | adjacent (supporting knowledge)

Generate {_MIN_SPECIALTIES}-{_MAX_SPECIALTIES} specialties. Include both core and adjacent.

Return JSON: {{"specialties": [...]}}""",
            model=settings.llm_model,
        )
    except Exception as exc:
        logger.error("Scaffold LLM call failed: %s", exc)
        return []

    raw_specs = result.get("specialties", [])
    if not isinstance(raw_specs, list):
        return []

    validated = _validate_scaffolded_specialties(raw_specs)

    # Similarity check — skip if too close to an existing specialty
    final: list[dict] = []
    for spec in validated:
        similar = find_similar_slug(spec["slug"], existing_slugs)
        if similar and similar != spec["slug"]:
            logger.info("Skipping %s — too similar to existing %s", spec["slug"], similar)
            continue
        final.append(spec)

    # Create in DB
    created: list[dict] = []
    async with pool.connection() as db:
        for spec in final:
            discipline_id = disc_map.get(spec.get("discipline", ""))
            try:
                rows = parse_rows(
                    await db.query(
                        """CREATE specialty SET
                            slug        = $slug,
                            name        = $name,
                            description = $desc,
                            perspective = $perspective,
                            discipline  = $discipline,
                            org         = $product,
                            priority    = $priority,
                            status      = 'scaffolded',
                            bootstrapped = false,
                            insight_count = 0,
                            min_threshold = 5,
                            created_at  = time::now()""",
                        {
                            "slug": spec["slug"],
                            "name": spec.get("name", spec["slug"]),
                            "desc": spec.get("description", ""),
                            "perspective": spec["perspective"],
                            "discipline": discipline_id,
                            "product": parse_record_id(product_id),
                            "priority": spec.get("priority", "adjacent"),
                        },
                    )
                )
                if rows:
                    created.append({**spec, "id": str(rows[0].get("id", ""))})
            except Exception as exc:
                logger.warning("Failed to create specialty %s: %s", spec["slug"], exc)

    logger.info("Scaffolded %d specialties for %s", len(created), product_id)
    return created

# engine/orchestrator/specialty_resolver.py
"""Resolve specialty slugs to record IDs.

Provides:
- Exact-match lookup against the org's specialty table
- Fuzzy slug matching via SequenceMatcher (threshold 0.7)
- Rate-limited auto-creation of proposed specialties (max 3 per org per hour)
"""

from __future__ import annotations

import logging
import time
from difflib import SequenceMatcher

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERSPECTIVES: set[str] = {"theorist", "practitioner", "strategist", "operator"}

_SIMILARITY_THRESHOLD = 0.7
_RATE_LIMIT_MAX = 3
_RATE_LIMIT_WINDOW = 3600  # seconds (1 hour)

# In-memory rate-limit store: {product_id: [timestamp, ...]}
_creation_log: dict[str, list[float]] = {}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def find_similar_slug(candidate: str, existing: list[str]) -> str | None:
    """Return the best matching slug from *existing* for *candidate*.

    Priority:
    1. Exact match — returned immediately.
    2. Closest slug whose SequenceMatcher ratio is >= 0.7.
    3. None if no match found.
    """
    # Exact match first
    if candidate in existing:
        return candidate

    best_slug: str | None = None
    best_ratio: float = 0.0

    for slug in existing:
        ratio = SequenceMatcher(None, candidate, slug).ratio()
        if ratio >= _SIMILARITY_THRESHOLD and ratio > best_ratio:
            best_ratio = ratio
            best_slug = slug

    return best_slug


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def _check_rate_limit(product_id: str) -> bool:
    """Return True if the org is allowed to create another specialty right now."""
    now = time.monotonic()
    timestamps = _creation_log.get(product_id, [])
    # Prune timestamps outside the window
    timestamps = [t for t in timestamps if (now - t) < _RATE_LIMIT_WINDOW]
    _creation_log[product_id] = timestamps
    return len(timestamps) < _RATE_LIMIT_MAX


def _record_creation(product_id: str) -> None:
    """Log a creation timestamp for rate-limit tracking."""
    now = time.monotonic()
    if product_id not in _creation_log:
        _creation_log[product_id] = []
    _creation_log[product_id].append(now)
    logger.debug(
        "Specialty creation recorded for org=%s (total this hour: %d)", product_id, len(_creation_log[product_id])
    )


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------


async def resolve_specialties(slugs: list[str], product_id: str) -> dict:
    """Resolve a list of specialty slugs for an org.

    For each requested slug the resolver attempts, in order:

    1. Exact match in the org's specialty table (or product:platform).
    2. Fuzzy match (find_similar_slug) against all existing slugs.
    3. Auto-create a ``proposed`` specialty — subject to rate limiting.

    Returns a dict::

        {
            "resolved": [<specialty row dict>, ...],   # matched / created
            "gaps":     [{"slug": ..., "reason": ...}, ...],  # thin coverage
            "proposed": [<specialty row dict>, ...],   # newly created this call
        }

    Each resolved entry may carry a ``matched_from`` key when a fuzzy match was
    used.
    """
    resolved: list[dict] = []
    gaps: list[dict] = []
    proposed: list[dict] = []

    async with pool.connection() as db:
        # Fetch all specialties visible to this org (own + platform baseline).
        rows_result = await db.query(
            "SELECT * FROM specialty WHERE (product = <record>$product OR org = <record>product:platform)",
            {"product": product_id},
        )
        existing_rows: list[dict] = parse_rows(rows_result)

    # Build a slug → row index for fast lookup
    slug_to_row: dict[str, dict] = {row["slug"]: row for row in existing_rows if "slug" in row}
    existing_slugs = list(slug_to_row.keys())

    for slug in slugs:
        # --- 1. Exact match ---
        if slug in slug_to_row:
            row = slug_to_row[slug]
            resolved.append(row)
            _maybe_add_gap(row, slug, gaps)
            continue

        # --- 2. Fuzzy match ---
        similar = find_similar_slug(slug, existing_slugs)
        if similar is not None:
            row = dict(slug_to_row[similar])
            row["matched_from"] = slug
            resolved.append(row)
            _maybe_add_gap(row, slug, gaps)
            continue

        # --- 3. Auto-create (rate-limited) ---
        if not _check_rate_limit(product_id):
            logger.warning(
                "Specialty auto-creation rate limit reached for org=%s — skipping slug '%s'",
                product_id,
                slug,
            )
            continue

        new_row = await _create_proposed_specialty(slug, product_id)
        if new_row:
            _record_creation(product_id)
            resolved.append(new_row)
            proposed.append(new_row)
            # A brand-new proposed specialty is also a gap by definition
            gaps.append({"slug": slug, "reason": "newly_proposed"})

    return {"resolved": resolved, "gaps": gaps, "proposed": proposed}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _maybe_add_gap(row: dict, requested_slug: str, gaps: list[dict]) -> None:
    """Add an entry to *gaps* when the specialty has thin coverage."""
    insight_count = row.get("insight_count", 0) or 0
    min_threshold = row.get("min_threshold", 0) or 0
    if insight_count < min_threshold:
        gaps.append({"slug": row.get("slug", requested_slug), "reason": "below_threshold"})


async def _create_proposed_specialty(slug: str, product_id: str) -> dict | None:
    """CREATE a specialty record with status='proposed' and return it."""
    from core.engine.core.db import parse_one

    name = slug.replace("-", " ").title()

    async with pool.connection() as db:
        # decision:8o4c6s8xxrxkov8xzbn1 — v061 REMOVE FIELD org ON specialty.
        # The prior CREATE raised "Found field 'org'" on every scaffolder run.
        # `product` is the correct field per v054.
        result = await db.query(
            """
            CREATE specialty SET
                slug        = $slug,
                name        = $name,
                product     = <record>$product,
                perspective = $perspective,
                status      = $status,
                bootstrapped = false,
                insight_count = 0,
                min_threshold = 0,
                created_at  = time::now()
            """,
            {
                "slug": slug,
                "name": name,
                "product": product_id,
                "perspective": "practitioner",
                "status": "proposed",
            },
        )
        row = parse_one(result)

    if row:
        logger.info("Auto-created proposed specialty '%s' for org=%s", slug, product_id)
    else:
        logger.warning("Failed to create specialty '%s' for org=%s", slug, product_id)

    return row

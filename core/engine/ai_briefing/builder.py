"""AIBriefing builder + renderer.

Pulls a compact, structured ground-truth snapshot from the substrate so any
AI ACE dispatches starts from what's already known — not from theorizing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


# In-process briefing cache. Keyed by product_id; entries are (built_at, briefing).
# Briefings change slowly (decisions/capabilities), so a short TTL cuts substrate
# load substantially across multi-call sessions. TTL is settings-controlled.
_briefing_cache: dict[str, tuple[float, "AIBriefing"]] = {}


def _cache_get(product_id: str, ttl_seconds: int) -> "AIBriefing | None":
    """Return cached briefing if fresh; else None."""
    if ttl_seconds <= 0:
        return None
    entry = _briefing_cache.get(product_id)
    if entry is None:
        return None
    built_at, briefing = entry
    if (time.monotonic() - built_at) > ttl_seconds:
        return None
    return briefing


def _cache_set(product_id: str, briefing: "AIBriefing") -> None:
    """Store briefing in the in-process cache."""
    _briefing_cache[product_id] = (time.monotonic(), briefing)


def invalidate_briefing_cache(product_id: str | None = None) -> None:
    """Drop cached briefings.

    With no argument, drops all entries. With a product_id, drops that one.
    Useful after captures/decisions that should be visible to the next
    dispatched AI immediately.
    """
    if product_id is None:
        _briefing_cache.clear()
    else:
        _briefing_cache.pop(product_id, None)


# Architecture digest: a stable, short paragraph that orients any AI partner to
# what ACE IS before it sees substrate-specific state. Kept under ~500 chars so
# it fits comfortably in cached prefixes across calls.
_ARCHITECTURE_DIGEST = (
    "ACE is a 9-layer reasoning substrate above your IDE. "
    "L1 Meta-Intelligence (substrate state) · L2 Classification (24 disciplines × 6 archetypes × 6 modes) · "
    "L3 Composition (22 meta-skills self-nominate via activation_signals + affinities + composability) · "
    "L4 Engagement Engine (lens-driven, problem-derived, max 4 lenses in parallel) · "
    "L5 Disciplines × Frameworks (181 instruments, learned/static blend) · "
    "L6 Synthesis (cross-discipline implication chains + leverage points) · "
    "L7 Decision + Graph Write (lineage edges, predictions attached) · "
    "L8 Sentinel (34 cron + event-triggered engines, 24/7) · "
    "L9 Foresight (forecaster + reconciler closes the loop, updates archetype_calibration via EMA). "
    "Nothing is predefined. Every layer composes from substrate state, not lookup tables."
)


@dataclass
class AIBriefing:
    """Structured payload sent to a dispatched AI before reasoning.

    Each field is independently optional so renderers can drop sections when
    empty. Fields are populated by substrate queries in build_briefing().
    """

    architecture_digest: str = ""
    current_phase: str = ""
    recent_decisions: list[dict] = field(default_factory=list)
    active_capabilities: list[dict] = field(default_factory=list)
    known_gaps: list[dict] = field(default_factory=list)
    active_meta_skills: list[str] = field(default_factory=list)
    product_id: str = ""
    roadmap_headline: str = ""


async def build_briefing(
    product_id: str,
    *,
    decision_limit: int = 8,
    capability_limit: int = 12,
    gap_limit: int = 6,
    use_cache: bool = True,
) -> AIBriefing:
    """Assemble an AIBriefing from current substrate state.

    All queries are bounded — the briefing must fit in a cached prefix without
    bloating every CLI invocation. If substrate is unreachable, returns a
    briefing with only the architecture_digest populated (still useful).

    Caching: when use_cache=True (default), returns a cached briefing if one
    exists for product_id within settings.ai_briefing_cache_ttl_seconds.
    Call invalidate_briefing_cache(product_id) to force a fresh build.

    Args:
        product_id: substrate scope (e.g. "product:reference")
        decision_limit: max recent decisions to include
        capability_limit: max capabilities to include
        gap_limit: max known gaps to include
        use_cache: when True, consult the in-process cache before querying

    Returns:
        AIBriefing populated from substrate; never raises.
    """
    if use_cache:
        from core.engine.core.config import settings

        cached = _cache_get(product_id, settings.ai_briefing_cache_ttl_seconds)
        if cached is not None:
            return cached

    briefing = AIBriefing(
        architecture_digest=_ARCHITECTURE_DIGEST,
        product_id=product_id,
    )

    try:
        async with pool.connection() as db:
            # Recent decisions — what was decided lately, with rationale leads
            decisions = await db.query(
                """SELECT title, decision_type, rationale, created_at
                   FROM decision
                   WHERE product = <record>$product
                     AND status = 'active'
                   ORDER BY created_at DESC
                   LIMIT $limit""",
                {"product": product_id, "limit": decision_limit},
            )
            briefing.recent_decisions = [
                {
                    "title": row.get("title", "")[:120],
                    "type": row.get("decision_type", ""),
                    "rationale_lead": (row.get("rationale", "") or "")[:200],
                }
                for row in parse_rows(decisions)
            ]

            # Active capabilities — what's already built; prevents the AI from
            # theorizing about building things that exist
            capabilities = await db.query(
                """SELECT slug, description, status, score
                   FROM capability
                   WHERE product = <record>$product
                     AND status IN ['built', 'partial']
                   ORDER BY score DESC
                   LIMIT $limit""",
                {"product": product_id, "limit": capability_limit},
            )
            briefing.active_capabilities = [
                {
                    "slug": row.get("slug", ""),
                    "description": (row.get("description", "") or "")[:140],
                    "status": row.get("status", ""),
                    "score": row.get("score"),
                }
                for row in parse_rows(capabilities)
            ]

            # Known gaps — capabilities below floor, sentinel-detected issues.
            # Lower score = bigger gap. Caps the AI's expectations of substrate
            # maturity per area so it knows what's underdeveloped.
            gaps = await db.query(
                """SELECT slug, description, score
                   FROM capability
                   WHERE product = <record>$product
                     AND status IN ['built', 'partial']
                     AND score < 0.5
                   ORDER BY score ASC
                   LIMIT $limit""",
                {"product": product_id, "limit": gap_limit},
            )
            briefing.known_gaps = [
                {
                    "slug": row.get("slug", ""),
                    "description": (row.get("description", "") or "")[:140],
                    "score": row.get("score"),
                }
                for row in parse_rows(gaps)
            ]

    except Exception as exc:
        # Substrate unreachable (no DB, transient failure, test environment).
        # Return architecture-only briefing — still grounds the AI in what
        # ACE is, even without state-specific detail. Don't cache the
        # architecture-only briefing — the next call should retry the substrate.
        logger.warning("AI briefing substrate query failed; returning architecture-only briefing: %s", exc)
        return briefing

    briefing.roadmap_headline = ""
    try:
        from core.engine.product.roadmap import compute_roadmap

        rm = await compute_roadmap(product_id)
        now = rm.lanes.get("now", [])
        superseded = [i for i in rm.lanes.get("parked", []) if i.staleness.value == "superseded"]
        if now:
            briefing.roadmap_headline = f"Now: {now[0].title} ({now[0].rationale})"
            if superseded:
                briefing.roadmap_headline += f" · {len(superseded)} superseded item(s)"
    except Exception as exc:
        logger.warning("briefing roadmap headline failed (non-fatal): %s", exc)

    if use_cache:
        _cache_set(product_id, briefing)
    return briefing


def render_briefing(briefing: AIBriefing) -> str:
    """Render an AIBriefing as a system-prompt prefix string.

    Sections are dropped when empty so the prefix stays as small as possible —
    important because the prefix is paid for on every CLIProvider invocation
    (modulo Anthropic prompt cache hits).
    """
    parts: list[str] = []

    # Lead with the roadmap so every dispatched AI reaches the plan through its own front door.
    # (This field was computed but never rendered — the reason the roadmap was invisible to the agent.)
    if briefing.roadmap_headline:
        parts.append(f"# Current Roadmap (what's next — lead with this)\n{briefing.roadmap_headline}")

    if briefing.architecture_digest:
        parts.append(f"# ACE Substrate (architecture you are operating within)\n{briefing.architecture_digest}")

    if briefing.recent_decisions:
        lines = ["# Recent Decisions (operate consistently with these)"]
        for d in briefing.recent_decisions:
            title = d.get("title", "")
            dtype = d.get("type", "")
            rationale = d.get("rationale_lead", "")
            lines.append(f"- [{dtype}] {title}")
            if rationale:
                lines.append(f"  why: {rationale}")
        parts.append("\n".join(lines))

    if briefing.active_capabilities:
        lines = ["# Already Built (do not propose to build these — extend or use them)"]
        for cap in briefing.active_capabilities:
            slug = cap.get("slug", "")
            desc = cap.get("description", "")
            score = cap.get("score")
            score_tag = f" (score {score:.2f})" if isinstance(score, (int, float)) else ""
            line = f"- {slug}{score_tag}"
            if desc:
                line += f" — {desc}"
            lines.append(line)
        parts.append("\n".join(lines))

    if briefing.known_gaps:
        lines = ["# Known Gaps (below floor — be careful in these areas)"]
        for gap in briefing.known_gaps:
            slug = gap.get("slug", "")
            score = gap.get("score")
            score_tag = f" (score {score:.2f})" if isinstance(score, (int, float)) else ""
            lines.append(f"- {slug}{score_tag}")
        parts.append("\n".join(lines))

    if briefing.active_meta_skills:
        parts.append("# Active Meta-Intelligences for this task\n" + ", ".join(briefing.active_meta_skills))

    return "\n\n".join(parts)


async def briefing_for_dispatched_ai(product_id: str, meta_skills: list[str] | None = None) -> str:
    """Convenience: build + render in one call.

    Args:
        product_id: substrate scope
        meta_skills: optional list of meta-skill slugs active for this task,
            included in the rendered briefing so the dispatched AI knows
            which intelligences are weighing in

    Returns:
        Rendered briefing string, ready to prepend to a system prompt.
    """
    briefing = await build_briefing(product_id)
    if meta_skills:
        briefing.active_meta_skills = list(meta_skills)
    return render_briefing(briefing)

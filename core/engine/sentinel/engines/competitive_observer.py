"""Competitive intelligence observer — scans competitor changelogs, blogs, and releases.

Extracts competitive signals via budget LLM, classifies relevance to ACE,
writes insights through the intelligence pipeline, and alerts on high-relevance signals.

Spec: docs/superpowers/specs/2026-03-25-competitive-observer.md
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.notifications.dispatcher import dispatch as notify
from core.engine.sentinel.engines import write_engine_insight
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

# Minimum days between scans per tier
TIER_CADENCE_DAYS = {
    1: 6,  # weekly (allow 1 day of slack)
    2: 25,  # monthly
    3: 80,  # quarterly
}

EXTRACTION_PROMPT = """You are analyzing a competitor's changelog/blog for signals relevant to ACE (Augmented Cognition Engine).

ACE is an organizational intelligence system with:
- Dual knowledge graphs (specialty + org)
- Overnight learning engines that self-correct
- Multi-perspective reasoning (theorist/strategist/practitioner/operator)
- Statistical experimentation (A/B tests with Welch's t-test)
- Self-optimizing retrieval and skill emergence
- MCP integration for AI coding tools

Competitor: {competitor_name}

Content to analyze:
{content}

Extract each NEW feature, capability, or strategic shift as a separate signal.
For each signal, provide:
- title: concise name (max 10 words)
- description: what it does (1-2 sentences)
- relevance: one of [overlap, gap, threat, opportunity, none]
  - overlap: ACE already has this or similar
  - gap: ACE should have this but doesn't
  - threat: this directly competes with ACE's differentiator
  - opportunity: this validates ACE's approach or creates a partnership opening
  - none: not relevant to ACE
- urgency: one of [low, medium, high]

Return JSON: {{"signals": [{{...}}, ...]}}
Only include signals with relevance != "none". Max 10 signals."""

CLASSIFICATION_PROMPT = """Assess this competitive signal's relevance to ACE (Augmented Cognition Engine).

Signal: {title}
Description: {description}
Initial relevance: {relevance}
Urgency: {urgency}

ACE capabilities: dual knowledge graphs, overnight learning engines, multi-perspective reasoning,
statistical experimentation, self-optimizing retrieval, MCP integration, idea pipeline, briefings.

Assess:
1. Do we already have this? If so, is ours better or worse?
2. Should we build this? Why or why not?
3. Does this change our competitive positioning?

Return JSON:
{{
    "relevance_score": <float 0.0-1.0, how relevant to ACE>,
    "action": "<ignore|monitor|respond|urgent>",
    "rationale": "<1-2 sentence explanation>"
}}"""


def _html_to_text(html: str) -> str:
    """Strip HTML tags to plain text. Preserves whitespace structure."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:15000]


async def fetch_source(source: dict) -> str:
    """Fetch a competitor source URL and return plain text content.

    Returns empty string on any failure.
    """
    url = source.get("url", "")
    if not url:
        return ""

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "ACE-CompetitiveObserver/1.0"},
            )
            resp.raise_for_status()
            return _html_to_text(resp.text)
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return ""


async def extract_signals(content: str, competitor_name: str) -> list[dict]:
    """Extract competitive signals from fetched content via budget LLM.

    Returns list of signal dicts. Returns empty list on failure.
    """
    if not content or len(content.strip()) < 50:
        return []

    try:
        prompt = EXTRACTION_PROMPT.format(
            competitor_name=competitor_name,
            content=content[:12000],
        )
        result = await llm.complete_json(prompt, model=settings.llm_budget_model)
        signals = result.get("signals", [])
        valid = []
        for s in signals:
            if all(k in s for k in ("title", "description", "relevance", "urgency")):
                valid.append(s)
        return valid
    except Exception as exc:
        logger.warning("Signal extraction failed for %s: %s", competitor_name, exc)
        return []


async def classify_signal(signal: dict) -> dict:
    """Classify a signal's relevance to ACE. Returns enriched signal dict.

    Adds relevance_score, action, and rationale fields.
    Falls back to moderate defaults on failure.
    """
    try:
        prompt = CLASSIFICATION_PROMPT.format(
            title=signal.get("title", ""),
            description=signal.get("description", ""),
            relevance=signal.get("relevance", ""),
            urgency=signal.get("urgency", ""),
        )
        result = await llm.complete_json(prompt, model=settings.llm_budget_model)
        signal["relevance_score"] = float(result.get("relevance_score", 0.5))
        signal["action"] = result.get("action", "monitor")
        signal["rationale"] = result.get("rationale", "")
    except Exception as exc:
        logger.warning("Signal classification failed: %s", exc)
        signal["relevance_score"] = 0.5
        signal["action"] = "monitor"
        signal["rationale"] = f"Classification failed: {exc}"
    return signal


def should_scan(competitor: dict, now: datetime) -> bool:
    """Determine if a competitor should be scanned based on tier cadence."""
    last = competitor.get("last_scanned")
    if last is None:
        return True

    if isinstance(last, str):
        try:
            last = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return True

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    min_days = TIER_CADENCE_DAYS.get(competitor.get("tier", 1), 6)
    return (now - last) > timedelta(days=min_days)


async def _dispatch_alert(product_id: str, signal: dict) -> None:
    """Send notification for high-relevance signals."""
    try:
        await notify(
            product_id=product_id,
            user_id="user:default",
            tier="actionable",
            category="competitive_intelligence",
            title=f"Competitive signal: {signal['title']}",
            body=f"[{signal.get('competitor', '?')}] {signal['description']}\n\nAction: {signal.get('action', 'monitor')} — {signal.get('rationale', '')}",
            link="/settings/sentinel",
        )
    except Exception as exc:
        logger.warning("Failed to dispatch competitive alert: %s", exc)


def _validate_competitive_observer_inputs(product_id: str, budget: int = 100) -> None:
    """Validate competitive observer inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for competitive-observer: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="competitive_observer",
    cron="0 6 * * mon",
    description="Scan competitor changelogs/blogs for competitive intelligence signals",
)
async def run_competitive_observer(product_id: str, budget: int = 0) -> dict:
    """Scan competitor sources, extract and classify signals, write insights.

    Budget is ignored — all eligible competitors are scanned. Cost is naturally
    bounded by the number of competitors × sources × LLM extraction calls.
    """
    now = datetime.now(timezone.utc)
    competitors_scanned = 0
    signals_extracted = 0
    insights_written = 0
    alerts_sent = 0

    _validate_competitive_observer_inputs(product_id, budget)
    async with pool.connection() as db:
        # decision:zlinw5b2kx09j8k2s00l — v064 renamed `org` → `product`
        # (record<product>) on competitor + competitive_signal. This SELECT
        # had been silently returning [] since v064 because `org` no longer
        # exists as a field on `competitor`.
        rows = parse_rows(
            await db.query(
                "SELECT * FROM competitor WHERE product = <record>$product ORDER BY tier ASC",
                {"product": product_id},
            )
        )

        for comp in rows:
            if not should_scan(comp, now):
                logger.debug("Skipping %s (tier %d)", comp["name"], comp["tier"])
                continue

            comp_name = comp["name"]
            comp_signals: list[dict] = []

            for source in comp.get("sources", []):
                text = await fetch_source(source)
                if not text:
                    continue
                extracted = await extract_signals(text, comp_name)
                for sig in extracted:
                    sig["competitor"] = comp_name
                    sig["source_url"] = source.get("url", "")
                comp_signals.extend(extracted)

            for sig in comp_signals:
                sig = await classify_signal(sig)

                await db.query(
                    """
                    CREATE competitive_signal SET
                        competitor = $competitor,
                        product = <record>$product,
                        title = $title,
                        description = $description,
                        source_url = $source_url,
                        relevance = $relevance,
                        relevance_score = $relevance_score,
                        action = $action,
                        urgency = $urgency,
                        rationale = $rationale,
                        created_at = time::now()
                    """,
                    {
                        "competitor": sig.get("competitor", comp_name),
                        # decision:zlinw5b2kx09j8k2s00l — v064 renamed org → product.
                        # The prior CREATE raised "Expected record<product>, found NONE"
                        # on every signal write, silently consumed by the cron-path
                        # error handler. No competitive_signal rows have been written
                        # since v064 landed.
                        "product": product_id,
                        "title": sig.get("title", ""),
                        "description": sig.get("description", ""),
                        "source_url": sig.get("source_url", ""),
                        "relevance": sig.get("relevance", "none"),
                        "relevance_score": sig.get("relevance_score", 0.5),
                        "action": sig.get("action", "monitor"),
                        "urgency": sig.get("urgency", "low"),
                        "rationale": sig.get("rationale", ""),
                    },
                )

                if sig.get("action") in ("respond", "urgent"):
                    discipline = comp.get("domains", ["technology"])[0] if comp.get("domains") else "technology"
                    insight_id = await write_engine_insight(
                        db,
                        product_id=product_id,
                        content=f"[Competitive: {comp_name}] {sig['title']}: {sig['description']}\n\nRelevance: {sig.get('relevance')} | Action: {sig.get('action')}\n{sig.get('rationale', '')}",
                        insight_type="fact",
                        tier="org",
                        discipline=discipline,
                        source_domain="sentinel.competitive-observer",
                        confidence=sig.get("relevance_score", 0.5),
                        tags=[
                            f"competitor:{comp_name.lower().replace(' ', '-')}",
                            f"signal:{sig.get('relevance', 'unknown')}",
                            "competitive-intelligence",
                        ],
                    )
                    insights_written += 1
                    sig["insight_id"] = insight_id

                if sig.get("action") == "urgent" or (
                    sig.get("urgency") == "high" and sig.get("relevance_score", 0) > 0.7
                ):
                    await _dispatch_alert(product_id, sig)
                    alerts_sent += 1

                signals_extracted += 1

            competitors_scanned += 1

            comp_id = comp.get("id", "")
            if comp_id:
                await db.query(
                    "UPDATE <record>$comp_id SET last_scanned = time::now()",
                    {"comp_id": comp_id},
                )

    logger.info(
        "Competitive observer: scanned %d competitors, %d signals, %d insights, %d alerts",
        competitors_scanned,
        signals_extracted,
        insights_written,
        alerts_sent,
    )

    return {
        "competitors_scanned": competitors_scanned,
        "signals_extracted": signals_extracted,
        "insights_written": insights_written,
        "alerts_sent": alerts_sent,
    }

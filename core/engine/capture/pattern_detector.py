"""M6 — Cross-session pattern recurrence detection.

Detects when the same fix/decision pattern appears across multiple sessions
and surfaces a root-cause hypothesis via LLM.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

RECURRENCE_THRESHOLD = 3
SIMILARITY_THRESHOLD = 0.80

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall((text or "").lower()))


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _content_hash(text: str) -> str:
    """Stable hash of normalized pattern content for deduplication."""
    normalized = " ".join(sorted(_tokenize(text)))
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class RecurringPattern:
    pattern_hash: str
    recurrence_count: int
    sessions: list[str]
    affected_modules: list[str]
    representative_content: str
    root_cause_hypothesis: str = ""


class CrossSessionPatternDetector:
    """Detects recurrence of the same pattern across sessions."""

    async def check_recurrence(
        self,
        new_insights: list[dict],
        product_id: str,
        current_session_id: str,
        db_pool,
    ) -> list[RecurringPattern]:
        """Check new insights against historical ones for recurrence.

        Called after synthesis pass — async, non-blocking in the synthesizer.
        Returns list of patterns that hit or exceed RECURRENCE_THRESHOLD.
        """
        if not new_insights:
            return []

        from core.engine.core.db import parse_rows

        # Load recent historical insights (not from current session)
        try:
            async with db_pool.connection() as db:
                historical = parse_rows(
                    await db.query(
                        """SELECT content, source_session, tags, created_at FROM insight
                    WHERE product = <record>$product
                    AND (archived_at = NONE OR archived_at IS NULL)
                    AND source_session != $session
                    ORDER BY created_at DESC LIMIT 2000""",
                        {"product": product_id, "session": current_session_id},
                    )
                )
        except Exception as exc:
            logger.debug("pattern_detector: history query failed: %s", exc)
            return []

        hist_tokens = [(_tokenize(h.get("content", "")), h) for h in historical]

        found: list[RecurringPattern] = []

        for new_item in new_insights:
            new_text = new_item.get("content", "")
            if not new_text:
                continue
            new_tok = _tokenize(new_text)
            p_hash = _content_hash(new_text)

            matching_sessions: set[str] = {current_session_id}
            matching_modules: set[str] = set()
            for hist_tok, hist_item in hist_tokens:
                if _jaccard(new_tok, hist_tok) >= SIMILARITY_THRESHOLD:
                    sess = str(hist_item.get("source_session", ""))
                    if sess:
                        matching_sessions.add(sess)
                    for tag in hist_item.get("tags") or []:
                        if "/" in tag or "." in tag:
                            matching_modules.add(tag)

            if len(matching_sessions) >= RECURRENCE_THRESHOLD:
                rp = RecurringPattern(
                    pattern_hash=p_hash,
                    recurrence_count=len(matching_sessions),
                    sessions=list(matching_sessions),
                    affected_modules=list(matching_modules),
                    representative_content=new_text[:300],
                )
                rp.root_cause_hypothesis = await self.generate_root_cause_hypothesis(rp)
                found.append(rp)
                await self._upsert_recurring_pattern(rp, product_id, db_pool)

        return found

    async def generate_root_cause_hypothesis(self, pattern: RecurringPattern) -> str:
        """LLM call: hypothesize root cause from N examples."""
        try:
            from core.engine.core.llm import get_llm

            prompt = (
                f"This pattern has recurred {pattern.recurrence_count} times across sessions:\n"
                f'"{pattern.representative_content}"\n\n'
                f"In one sentence, hypothesize the root cause that keeps producing this pattern."
            )
            llm = get_llm()
            return (await llm.complete(prompt, max_tokens=80) or "").strip()
        except Exception as exc:
            logger.debug("generate_root_cause_hypothesis failed: %s", exc)
            return ""

    async def _upsert_recurring_pattern(self, pattern: RecurringPattern, product_id: str, db_pool) -> None:
        try:
            async with db_pool.connection() as db:
                await db.query(
                    """UPSERT recurring_pattern SET
                        product = <record>$product,
                        pattern_hash = $hash,
                        recurrence_count = $count,
                        sessions = $sessions,
                        affected_modules = $modules,
                        root_cause_hypothesis = $hypothesis,
                        updated_at = time::now()
                    WHERE product = <record>$product AND pattern_hash = $hash""",
                    {
                        "product": product_id,
                        "hash": pattern.pattern_hash,
                        "count": pattern.recurrence_count,
                        "sessions": pattern.sessions,
                        "modules": pattern.affected_modules,
                        "hypothesis": pattern.root_cause_hypothesis,
                    },
                )
        except Exception as exc:
            logger.debug("pattern_detector._upsert failed: %s", exc)

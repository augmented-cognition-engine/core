# engine/worker/knowledge.py
"""DisciplineKnowledgeAgent — queryable AI agent primed with discipline-specific intelligence.

Build → Prime → Query model:
    agent = DisciplineKnowledgeAgent()
    await agent.prime("ux", "product:platform")
    answer = await agent.query("ux", "what design decisions have been made?")

The corpus is built from the product graph (insights, decisions, capabilities) for a
specific discipline and loaded into an LLM context. The agent then answers questions
grounded in that accumulated intelligence.

Corpus is cached in memory per (discipline, product_id). Call prime() to refresh.
"""

from __future__ import annotations

import logging
import time

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

# In-memory corpus cache: (discipline, product_id) → (corpus text, timestamp)
# TTL matches the intelligence pipeline's INTEL_TTL — stale after 10 minutes.
_corpus_cache: dict[tuple[str, str], tuple[str, float]] = {}

_MAX_CORPUS_CHARS = 8000  # ~2000 tokens — keep it focused
_CORPUS_TTL = 600  # seconds — re-prime after 10 minutes of worker uptime


class DisciplineKnowledgeAgent:
    """Queryable AI agent primed with discipline-specific intelligence from the product graph."""

    async def build_corpus(self, discipline: str, product_id: str) -> str:
        """Query the product graph and build a corpus document for this discipline.

        Pulls insights, decisions, and capabilities filtered by discipline.
        Returns structured text suitable as LLM system context.
        """
        sections: list[str] = []

        try:
            async with pool.connection() as db:
                # Active insights for this discipline
                insight_result = await db.query(
                    """SELECT content, confidence, created_at FROM insight
                    WHERE product = <record>$product AND status = 'active'
                    AND (discipline_hint = $disc OR domain_path = $disc)
                    AND confidence >= 0.6
                    ORDER BY confidence DESC, created_at DESC LIMIT 20""",
                    {"product": product_id, "disc": discipline},
                )
                insights = parse_rows(insight_result)

                # Active decisions for this discipline
                decision_result = await db.query(
                    """SELECT title, annotation, rationale, created_at FROM decision
                    WHERE product = <record>$product AND status = 'active'
                    AND discipline_hint = $disc
                    ORDER BY created_at DESC LIMIT 10""",
                    {"product": product_id, "disc": discipline},
                )
                decisions = parse_rows(decision_result)

                # Capabilities related to this discipline
                cap_result = await db.query(
                    """SELECT name, quality_score, status FROM graph_capability
                    WHERE product = <record>$product
                    AND (discipline = $disc OR name CONTAINS $disc)
                    ORDER BY quality_score DESC LIMIT 10""",
                    {"product": product_id, "disc": discipline},
                )
                capabilities = parse_rows(cap_result)

        except Exception as exc:
            logger.debug("build_corpus DB query failed for %s: %s", discipline, exc)
            return ""

        # Format corpus
        if decisions:
            sections.append(f"## Design Decisions ({discipline})")
            for d in decisions:
                title = d.get("title", "Untitled")
                rationale = d.get("rationale") or d.get("annotation", "")
                if rationale:
                    sections.append(f"- {title}: {str(rationale)[:300]}")
                else:
                    sections.append(f"- {title}")

        if insights:
            sections.append(f"\n## Accumulated Intelligence ({discipline})")
            for ins in insights:
                content = str(ins.get("content", ""))[:200]
                if content:
                    sections.append(f"- {content}")

        if capabilities:
            sections.append(f"\n## Product Capabilities ({discipline})")
            for cap in capabilities:
                name = cap.get("name", "?")
                score = cap.get("quality_score", 0)
                status = cap.get("status", "unknown")
                sections.append(f"- {name} (score:{score:.1f}, {status})")

        if not sections:
            return ""

        corpus = "\n".join(sections)
        # Hard cap to protect token budget
        return corpus[:_MAX_CORPUS_CHARS]

    async def prime(self, discipline: str, product_id: str) -> str:
        """Build corpus for this discipline and store in cache.

        Returns the corpus text. Call this to refresh after new intelligence is captured.
        """
        corpus = await self.build_corpus(discipline, product_id)
        if corpus:
            _corpus_cache[(discipline, product_id)] = (corpus, time.monotonic())
            logger.debug("Primed knowledge agent for %s: %d chars", discipline, len(corpus))
        return corpus

    async def query(self, discipline: str, question: str, product_id: str = "product:platform") -> str:
        """Ask a question grounded in the primed discipline corpus.

        If not yet primed, builds corpus on demand. Returns the LLM answer.
        Answers are grounded only in the accumulated product intelligence — no hallucination.
        """
        from core.engine.core.llm import get_llm

        cached = _corpus_cache.get((discipline, product_id))
        corpus = None
        if cached is not None:
            cached_text, cached_at = cached
            if time.monotonic() - cached_at < _CORPUS_TTL:
                corpus = cached_text
            else:
                logger.debug("Corpus TTL expired for %s — re-priming", discipline)
        if not corpus:
            corpus = await self.prime(discipline, product_id)

        if not corpus:
            return (
                f"No accumulated intelligence found for discipline '{discipline}' "
                f"in product {product_id}. Capture observations via ace_capture to build knowledge."
            )

        grounded_prompt = (
            f"You are an expert in {discipline} with deep knowledge of this specific product. "
            f"Answer questions using ONLY the intelligence documented below. "
            f"If the answer is not in the corpus, say so explicitly rather than speculating.\n\n"
            f"{corpus}\n\n"
            f"---\n\n"
            f"Question: {question}"
        )

        try:
            llm = get_llm()
            answer = await llm.complete(
                prompt=grounded_prompt,
                model=None,
                max_tokens=1024,
            )
            return answer
        except Exception as exc:
            logger.warning("DisciplineKnowledgeAgent.query LLM failed: %s", exc)
            # Fall back to returning a structured summary from the corpus
            lines = corpus.split("\n")[:10]
            return "(LLM unavailable) Corpus summary:\n" + "\n".join(lines)


# Module-level singleton
knowledge_agent = DisciplineKnowledgeAgent()

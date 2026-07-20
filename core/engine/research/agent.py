"""ResearchAgent — multi-mode research pipeline.

Research types:
  "internal"        — Type 2: query ACE graph, zero web calls
  "grounded_how_to" — Type 3: how should WE implement X given our stack
  "competitive"     — Type 4: landscape, gaps, what others are building
  "greenfield"      — Type 5: full pipeline + Opus strategic synthesis

The 11-step pipeline runs for Types 3-5. Type 2 is a direct graph query.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

import httpx

from core.engine.core.config import settings
from core.engine.research.confidence import ConfidenceScore, compute_confidence
from core.engine.research.source_registry import SourceClass, classify_url

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0

# Circuit breakers — before these existed, ace_research could hang for an hour
# if any LLM call or upstream API stalled. The global deadline caps total runtime;
# the per-step timeout caps individual LLM calls so fallbacks trigger instead of
# propagating a hang.
GLOBAL_RESEARCH_DEADLINE_S = 300.0  # 5 minutes total budget for the pipeline
PER_STEP_LLM_TIMEOUT_S = 60.0  # individual LLM call cap

RESEARCH_TYPES = frozenset({"internal", "grounded_how_to", "competitive", "greenfield"})


@dataclass
class SearchResult:
    url: str
    title: str
    content: str
    source_domain: str = ""

    def __post_init__(self) -> None:
        if not self.source_domain and self.url:
            from urllib.parse import urlparse

            try:
                self.source_domain = urlparse(self.url).netloc
            except Exception:
                pass


@dataclass
class ClassifiedResult:
    result: SearchResult
    source_class: SourceClass
    confidence: ConfidenceScore


@dataclass
class ResearchResult:
    topic: str
    discipline: str
    research_type: str
    synthesis: str
    evidence: list[ClassifiedResult] = field(default_factory=list)
    confidence: float = 0.0
    observation_id: str = ""


class ResearchAgent:
    """Routes research requests to the right strategy and runs the pipeline."""

    def __init__(self, product_id: str = "") -> None:
        self._product_id = product_id

    async def run(
        self,
        topic: str,
        research_type: str = "grounded_how_to",
        product_id: str | None = None,
        ceiling: str = "sonnet",
    ) -> ResearchResult:
        """Run research. Returns ResearchResult with synthesis + evidence.

        Wraps the whole pipeline in a GLOBAL_RESEARCH_DEADLINE_S budget so an
        upstream stall cannot hang the caller indefinitely. On timeout, returns
        a result with a clear error synthesis rather than raising.
        """
        if research_type not in RESEARCH_TYPES:
            raise ValueError(f"Unknown research_type {research_type!r}. Valid: {sorted(RESEARCH_TYPES)}")

        pid = product_id or self._product_id

        try:
            return await asyncio.wait_for(
                self._run_pipeline(topic, research_type, pid, ceiling),
                timeout=GLOBAL_RESEARCH_DEADLINE_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "ace_research timed out after %ss for topic=%r type=%r",
                GLOBAL_RESEARCH_DEADLINE_S,
                topic,
                research_type,
            )
            return ResearchResult(
                topic=topic,
                discipline="",
                research_type=research_type,
                synthesis=(
                    f"Research timed out after {GLOBAL_RESEARCH_DEADLINE_S:.0f}s. "
                    "The upstream search or LLM stalled. Try a narrower topic or re-run later."
                ),
                evidence=[],
                confidence=0.0,
                observation_id="",
            )

    async def _run_pipeline(
        self,
        topic: str,
        research_type: str,
        pid: str,
        ceiling: str,
    ) -> ResearchResult:
        """Internal pipeline body — wrapped by run() with a global deadline."""
        if research_type == "internal":
            return await self._type2_internal(topic, pid)

        # Steps 1–11 for Types 3-5
        queries = await self._step1_expand(topic, ceiling)
        raw = await self._step2_search(queries)
        merged = self._step3_dedup(raw)
        classified = self._step4_classify(merged)
        discipline = await self._step5_discipline(topic, ceiling)

        # Step 6: re-query if fewer than 2 REFERENCE sources found
        reference_count = sum(1 for c in classified if c.source_class == SourceClass.REFERENCE)
        if reference_count < 2:
            seen_urls = {c.result.url.rstrip("/").lower() for c in classified}
            gap_raw = await self._step2_search([f"{topic} {discipline} official documentation"])
            gap_deduped = [r for r in self._step3_dedup(gap_raw) if r.url.rstrip("/").lower() not in seen_urls]
            classified.extend(self._step4_classify(gap_deduped))

        # Step 7: deep extraction of top REFERENCE/EXEMPLAR sources
        top = [c for c in classified if c.source_class in (SourceClass.REFERENCE, SourceClass.EXEMPLAR)][:3]
        extracted = await self._step7_extract(top)

        # Step 8: GitHub repo enrichment (skip for competitive — no code needed)
        repos: list[str] = []
        if research_type != "competitive":
            repos = await self._step8_repos(topic)

        # Step 9: rerank
        ranked = self._step9_rerank(classified)

        # Step 10: synthesis
        # All research types use llm_model (Sonnet) — framework context is rich enough.
        # For Opus synthesis, caller must pass ceiling="opus" explicitly (opt-in).
        model = None  # route_model() inside _step10_synthesize picks the right tier
        synthesis = await self._step10_synthesize(
            ranked, extracted, repos, topic, discipline, research_type, model, ceiling
        )

        # Step 11: write to graph
        obs_id = await self._step11_write(synthesis, discipline, topic, pid)

        best_confidence = max((c.confidence.value for c in ranked), default=0.0)
        return ResearchResult(
            topic=topic,
            discipline=discipline,
            research_type=research_type,
            synthesis=synthesis,
            evidence=ranked,
            confidence=best_confidence,
            observation_id=obs_id,
        )

    # ------------------------------------------------------------------
    # Steps 3, 4, 9 — pure logic (no I/O, tested directly)
    # ------------------------------------------------------------------

    def _step3_dedup(self, results: list[SearchResult]) -> list[SearchResult]:
        """Deduplicate search results by URL."""
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for r in results:
            key = r.url.rstrip("/").lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    def _step4_classify(self, results: list[SearchResult]) -> list[ClassifiedResult]:
        """Classify each result by source quality. Drops NOISE."""
        classified: list[ClassifiedResult] = []
        for r in results:
            if not r.url:
                continue
            src_class = classify_url(r.url)
            if src_class == SourceClass.NOISE:
                continue
            classified.append(
                ClassifiedResult(
                    result=r,
                    source_class=src_class,
                    confidence=compute_confidence(src_class, corroboration_count=1),
                )
            )
        return classified

    def _step9_rerank(self, classified: list[ClassifiedResult]) -> list[ClassifiedResult]:
        """Sort REFERENCE > EXEMPLAR > SIGNAL, cap at 10."""
        order = {SourceClass.REFERENCE: 0, SourceClass.EXEMPLAR: 1, SourceClass.SIGNAL: 2}
        ranked = sorted(classified, key=lambda c: order.get(c.source_class, 3))
        return ranked[:10]

    # ------------------------------------------------------------------
    # Steps 1, 2, 5, 7, 8, 10, 11 — I/O steps
    # ------------------------------------------------------------------

    async def _step1_expand(self, topic: str, ceiling: str) -> list[str]:
        """Step 1: Expand topic into 3-5 targeted queries using Haiku.

        Bounded by PER_STEP_LLM_TIMEOUT_S so a stalled LLM falls back to raw queries.
        """
        try:
            from core.engine.core.llm import get_llm
            from core.engine.intelligence.model_router import route_model

            model = route_model("classification", ceiling=ceiling)
            llm = get_llm()
            result = await asyncio.wait_for(
                llm.complete_json(
                    f"Expand this research topic into 3-5 specific search queries.\n"
                    f"Topic: {topic}\n"
                    f'Return JSON: {{"queries": ["query1", "query2", ...]}}',
                    model=model,
                ),
                timeout=PER_STEP_LLM_TIMEOUT_S,
            )
            queries = result.get("queries", [])
            return queries[:5] if queries else [topic]
        except (asyncio.TimeoutError, Exception) as exc:
            logger.debug("Query expansion failed/timed out, using raw topic: %s", exc)
            return [topic, f"{topic} best practices", f"{topic} implementation guide"]

    async def _step2_search(self, queries: list[str]) -> list[SearchResult]:
        """Step 2: Multi-source parallel search across all queries."""
        tasks = [self._search_single(q) for q in queries[:3]]
        batches = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[SearchResult] = []
        for batch in batches:
            if isinstance(batch, list):
                results.extend(batch)
        return results

    async def _search_single(self, query: str) -> list[SearchResult]:
        """Search one query via Firecrawl/SearXNG → Tavily → DDG fallback."""
        results: list[SearchResult] = []

        # Try self-hosted Firecrawl /v1/search (backed by SearXNG — no rate limits)
        firecrawl_url = os.environ.get("FIRECRAWL_URL", "").rstrip("/")
        firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")
        if firecrawl_url:
            try:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if firecrawl_key:
                    headers["Authorization"] = f"Bearer {firecrawl_key}"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{firecrawl_url}/v1/search",
                        json={"query": query, "limit": 5},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                for r in data.get("data", []):
                    results.append(
                        SearchResult(
                            url=r.get("url", ""),
                            title=r.get("title", ""),
                            content=(r.get("description") or r.get("markdown", ""))[:500],
                        )
                    )
                if results:
                    return results
            except Exception as exc:
                logger.debug("Firecrawl search failed for %r: %s", query, exc)

        # Tavily fallback
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if api_key:
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": api_key, "query": query, "max_results": 5},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                for r in data.get("results", []):
                    results.append(
                        SearchResult(
                            url=r.get("url", ""),
                            title=r.get("title", ""),
                            content=r.get("content", "")[:500],
                        )
                    )
                return results
            except Exception as exc:
                logger.debug("Tavily failed for %r: %s", query, exc)

        # DDG last resort — hard timeout to prevent hangs
        try:
            from ddgs import DDGS

            def _ddg_sync() -> list[dict]:
                return list(DDGS(timeout=8).text(query, max_results=5))

            raw = await asyncio.wait_for(asyncio.to_thread(_ddg_sync), timeout=12.0)
            for r in raw:
                results.append(
                    SearchResult(
                        url=r.get("href", ""),
                        title=r.get("title", ""),
                        content=r.get("body", "")[:500],
                    )
                )
        except Exception as exc:
            logger.debug("DDG failed for %r: %s", query, exc)

        return results

    async def _step5_discipline(self, topic: str, ceiling: str) -> str:
        """Step 5: Map topic to one of ACE's 18 disciplines via Haiku."""
        disciplines = [
            "security",
            "testing",
            "ux",
            "performance",
            "devops",
            "data",
            "accessibility",
            "documentation",
            "architecture",
            "api_design",
            "data_modeling",
            "business_logic",
            "integration",
            "error_handling",
            "observability",
            "configuration",
            "deployment",
            "versioning",
            "code_conventions",
            "dependency_management",
        ]
        try:
            from core.engine.core.llm import get_llm
            from core.engine.intelligence.model_router import route_model

            model = route_model("classification", ceiling=ceiling)
            llm = get_llm()
            result = await asyncio.wait_for(
                llm.complete_json(
                    f"Map this topic to the most relevant discipline.\n"
                    f"Topic: {topic}\n"
                    f"Disciplines: {', '.join(disciplines)}\n"
                    f'Return JSON: {{"discipline": "<one of the disciplines above>"}}',
                    model=model,
                ),
                timeout=PER_STEP_LLM_TIMEOUT_S,
            )
            d = result.get("discipline", "architecture")
            return d if d in disciplines else "architecture"
        except (asyncio.TimeoutError, Exception):
            return "architecture"

    async def _step7_extract(self, results: list[ClassifiedResult]) -> list[str]:
        """Step 7: Deep extraction of top sources."""
        extracted: list[str] = []
        firecrawl_url = os.environ.get("FIRECRAWL_URL", "").rstrip("/")
        firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")
        for cr in results[:3]:
            url = cr.result.url
            if not url:
                continue
            try:
                if firecrawl_url:
                    headers = {"Content-Type": "application/json"}
                    if firecrawl_key:
                        headers["Authorization"] = f"Bearer {firecrawl_key}"
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            f"{firecrawl_url}/v1/scrape",
                            json={"url": url, "formats": ["markdown"]},
                            headers=headers,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    text = data.get("data", {}).get("markdown", "")[:4000]
                else:
                    from core.engine.research.fetcher import fetch

                    result = await fetch(url, mode="auto")
                    text = result.markdown[:4000]
                if text:
                    extracted.append(f"[{url}]\n{text}")
            except Exception as exc:
                logger.debug("Extraction failed for %s: %s", url, exc)
        return extracted

    async def _step8_repos(self, topic: str) -> list[str]:
        """Step 8: GitHub API — find exemplar repos for the topic."""
        github_token = settings.github_token
        if not github_token:
            return []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": topic, "sort": "stars", "per_page": 3},
                    headers={
                        "Authorization": f"token {github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            return [
                f"{r['full_name']} ({r.get('stargazers_count', 0)}★): {r.get('description', '')}"
                for r in data.get("items", [])[:3]
            ]
        except Exception as exc:
            logger.debug("GitHub repo search failed: %s", exc)
            return []

    async def _step10_synthesize(
        self,
        ranked: list[ClassifiedResult],
        extracted: list[str],
        repos: list[str],
        topic: str,
        discipline: str,
        research_type: str,
        model: str | None,
        ceiling: str,
    ) -> str:
        """Step 10: Cross-domain synthesis — Sonnet (Types 3-4) or Opus (Type 5)."""
        from core.engine.core.llm import get_llm
        from core.engine.intelligence.model_router import route_model

        if model is None:
            model = route_model("code_analysis", ceiling=ceiling)

        sources_text = "\n".join(
            f"- [{c.source_class.value}] {c.result.title}: {c.result.content[:200]}" for c in ranked[:5]
        )
        extracted_text = "\n\n---\n\n".join(extracted[:2])[:3000] if extracted else ""
        repos_text = "\n".join(repos) if repos else ""

        type_focus = {
            "grounded_how_to": (
                "How should WE specifically implement this given a Python/SurrealDB/Anthropic stack? "
                "Focus on actionable recommendations, not generic advice."
            ),
            "competitive": (
                "What is the competitive landscape? What are others building? What are the gaps and opportunities?"
            ),
            "greenfield": (
                "What should we build, why, and roughly how? Strategic synthesis with trade-offs and first principles."
            ),
        }
        focus = type_focus.get(research_type, type_focus["grounded_how_to"])

        prompt = f"Research topic: {topic}\nDiscipline: {discipline}\nFocus: {focus}\n\nSources:\n{sources_text}\n"
        if extracted_text:
            prompt += f"\nExtracted content:\n{extracted_text}\n"
        if repos_text:
            prompt += f"\nExemplar repos:\n{repos_text}\n"
        prompt += "\nSynthesize into 2-4 sentences of actionable intelligence. Be specific, not generic."

        try:
            llm = get_llm()
            return await asyncio.wait_for(
                llm.complete(prompt, model=model, max_tokens=512),
                timeout=PER_STEP_LLM_TIMEOUT_S,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Synthesis failed/timed out: %s", exc)
            return " | ".join(c.result.content[:100] for c in ranked[:3] if c.result.content)

    async def _step11_write(
        self,
        synthesis: str,
        discipline: str,
        topic: str,
        product_id: str,
    ) -> str:
        """Step 11: Write synthesis to ACE intelligence graph and synthesize to insight.

        Writes observation via ace_capture then immediately flushes through the
        Synthesizer so the result is visible to ace_search without waiting for
        the next batch trigger.
        """
        if not synthesis or not product_id:
            return ""
        try:
            from core.engine.mcp.tools import ace_capture

            content = f"[ResearchAgent] {topic}: {synthesis}"
            result = await ace_capture(
                observation_type="learning",
                content=content,
                domain_path=discipline,
                confidence=0.7,
                product_id=product_id,
            )
            obs_id = str(result.get("id", ""))

            # Promote observation → insight immediately (don't wait for batch flush)
            try:
                from core.engine.capture.synthesizer import Synthesizer
                from core.engine.core.db import pool as _pool

                synth = Synthesizer(product_id=product_id, workspace_id=None, batch_size=1)
                synth._db_pool = _pool
                await synth.add_observation(
                    {
                        "id": obs_id,
                        "content": content,
                        "observation_type": "learning",
                        "discipline_hint": discipline,
                        "confidence": 0.7,
                        "org": product_id,
                    }
                )
            except Exception as syn_exc:
                logger.debug("Synthesizer flush failed (non-fatal): %s", syn_exc)

            return obs_id
        except Exception as exc:
            logger.debug("Graph write failed: %s", exc)
            return ""

    async def _type2_internal(self, topic: str, product_id: str) -> ResearchResult:
        """Type 2: Internal lookup — query ACE graph only, zero web calls."""
        success = False
        try:
            from core.engine.mcp.tools import ace_search

            result = await ace_search(query=topic, product_id=product_id)
            rows = result.get("results", [])
            if rows:
                synthesis = "\n".join(r.get("content", "")[:200] for r in rows[:3])
                success = True
            else:
                synthesis = f"No internal knowledge found for: {topic}"
        except Exception as exc:
            synthesis = f"Graph lookup failed: {exc}"

        return ResearchResult(
            topic=topic,
            discipline="",
            research_type="internal",
            synthesis=synthesis,
            evidence=[],
            confidence=0.9 if success else 0.0,
        )

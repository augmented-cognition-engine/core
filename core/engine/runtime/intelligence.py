# engine/runtime/intelligence.py
"""Intelligence layer — pre-turn classification and intelligence loading.

Wires existing engine/orchestrator modules into the runtime:
- classify_task() → discipline, archetype, mode, specialties
- load_intelligence() → insights, signals, graph context
- _build_intel_context() → formatted prompt string

Implements in-memory-first caching (Rivet pattern): load once, serve from cache.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.engine.orchestrator.classifier import classify_task
from core.engine.orchestrator.executor import _build_intel_context
from core.engine.orchestrator.loader import load_intelligence

if TYPE_CHECKING:
    from core.engine.cognition.models import CognitiveComposition

logger = logging.getLogger(__name__)


class IntelligenceLayer:
    """Pre-turn intelligence: classify tasks and load relevant knowledge."""

    def __init__(self, product_id: str = "product:platform") -> None:
        self._org_id = product_id
        self._intel_cache: dict[str, str] = {}
        self._last_classification: dict | None = None

    async def classify(self, description: str) -> dict:
        """Classify a task description into discipline, archetype, mode, etc."""
        classification = await classify_task(description, self._org_id)
        self._last_classification = classification
        return classification

    async def load(self, classification: dict) -> str:
        """Load intelligence for a classification. Returns formatted context string."""
        discipline = classification.get("discipline", "architecture")
        mode = classification.get("mode", "reactive")
        specialties = classification.get("specialties", [])

        # Check cache first (in-memory-first pattern)
        cache_key = f"{discipline}:{','.join(sorted(specialties))}"
        cached = self._intel_cache.get(cache_key)
        if cached is not None:
            return cached

        # Load from graph
        try:
            snapshot = await load_intelligence(
                discipline=discipline,
                product_id=self._org_id,
                mode=mode,
                specialties=specialties,
            )
            context = _build_intel_context(snapshot)
        except Exception as exc:
            logger.warning("Intelligence loading failed: %s", exc)
            context = ""

        # Cache for future turns
        self._intel_cache[cache_key] = context
        return context

    async def classify_and_load(self, description: str) -> tuple[dict, str]:
        """Classify then load in one call. Returns (classification, context_string)."""
        classification = await self.classify(description)
        context = await self.load(classification)
        return classification, context

    async def classify_compose_and_load(self, description: str) -> tuple[dict, str, "CognitiveComposition"]:
        """Classify, compose, and load intelligence in one call.

        Returns (classification, context_string, cognitive_composition).
        Used by the TUI/chat path to get structured cognition alongside intelligence.
        """
        from core.engine.cognition.composer import CognitiveComposer
        from core.engine.cognition.models import CognitiveComposition

        classification, context = await self.classify_and_load(description)

        try:
            composition = await CognitiveComposer().compose(classification, self._org_id)
        except Exception as exc:
            logger.warning("Cognitive composition failed in chat path: %s", exc)
            composition = CognitiveComposition(
                meta_skills=[],
                depth=1,
                active_phases=[],
                resolved_instruments={},
                prompt_sections=[],
                fusion_mode=True,
            )

        return classification, context, composition

    async def load_code_context(self, description: str) -> str:
        """Get graph-grounded code context for a task description."""
        try:
            from core.engine.intelligence.graph_builder import GraphBuilder
            from core.engine.intelligence.queries import code_context

            builder = GraphBuilder(".")
            builder.phase1_treesitter()
            ctx = code_context(description, builder)

            parts = []
            if ctx.get("matched_files"):
                parts.append("## Relevant Files")
                for f in ctx["matched_files"][:10]:
                    parts.append(f"- {f}")
            if ctx.get("related_files"):
                parts.append("## Related Files")
                for f in ctx["related_files"][:10]:
                    parts.append(f"- {f}")
            return "\n".join(parts)
        except Exception as exc:
            logger.warning("Code context loading failed: %s", exc)
            return ""

    def get_cached(self, discipline: str) -> str | None:
        """Get cached intelligence for a discipline."""
        for key, value in self._intel_cache.items():
            if key.startswith(discipline):
                return value
        return None

    def clear_cache(self) -> None:
        """Clear the intelligence cache (e.g., on compaction)."""
        self._intel_cache.clear()
        self._last_classification = None

    @property
    def last_classification(self) -> dict | None:
        return self._last_classification

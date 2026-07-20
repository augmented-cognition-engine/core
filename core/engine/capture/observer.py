# engine/capture/observer.py
"""Observer — evaluates chunks for intelligence-worthy content.

Uses budget LLM (Haiku-tier) to classify. Returns observation dicts
ready for DB write. Does NOT write to DB itself — the pipeline handles that.
"""

from __future__ import annotations

import logging

from core.engine.capture.watchers import Chunk
from core.engine.core.config import settings
from core.engine.core.llm import llm
from core.engine.core.tasks import logged_task

logger = logging.getLogger(__name__)


class Observer:
    """Evaluates chunks and produces observation dicts."""

    def __init__(self, product_id: str, workspace_id: str | None, discipline_hint: str | None = None) -> None:
        self.product_id = product_id
        self.workspace_id = workspace_id
        self._recent_chunks: list[Chunk] = []
        self._discipline_hint = discipline_hint
        # Pre-loaded intelligence context injected into the evaluation prompt.
        # Loaded once by the pipeline via set_intel_context() — not per chunk.
        self._intel_context: str = ""

    def set_intel_context(self, context: str) -> None:
        """Inject pre-loaded discipline intelligence into chunk evaluation prompts."""
        self._intel_context = context

    async def evaluate_chunk(self, chunk: Chunk, memory_id: str | None) -> list[dict]:
        """Evaluate a chunk. Returns list of observation dicts (may be empty)."""
        if chunk.token_count < 20:
            return []

        # Non-blocking recognition pass — fire and forget, never delays capture.
        # decision:znalk48vc0rluxl1ejdg — logged_task captures exceptions instead
        # of letting them disappear with the task on GC.
        logged_task(self._recognition_pass(chunk.content), label="capture.recognition_pass")

        result = await self._call_budget_llm(chunk)

        if not result.get("has_intelligence"):
            return []

        # Add to context window AFTER evaluation (don't pollute current chunk's context)
        self._recent_chunks.append(chunk)
        if len(self._recent_chunks) > 10:
            self._recent_chunks.pop(0)

        observations = []
        for obs in result.get("observations", []):
            # Use .get() for safe field access; skip malformed entries
            content = obs.get("content")
            obs_type = obs.get("type")
            confidence = obs.get("confidence")
            if not content or not obs_type or confidence is None:
                continue  # skip malformed LLM output

            observations.append(
                {
                    "product": self.product_id,
                    "workspace": self.workspace_id,
                    "content": content,
                    "observation_type": obs_type,
                    "confidence": confidence,
                    "discipline_hint": obs.get("discipline_hint", obs.get("domain_hint")),
                    "source_memory": memory_id,
                    "session_id": chunk.events[0].session_id if chunk.events else None,
                    "synthesized": False,
                }
            )
        return observations

    async def _recognition_pass(self, text: str) -> None:
        """Fire-and-forget decision recognition on a conversation turn.

        Results are not yet acted upon here — recognition output is surfaced
        via the /recognition/turn REST endpoint for UI-driven confirm/dismiss.
        This task wires the observer into the recognition pipeline without
        blocking the capture path.
        """
        try:
            from core.engine.recognition import decision_classifier

            result = await decision_classifier.classify(
                turn_text=text,
                conversation_context="\n".join(c.content[:200] for c in self._recent_chunks[-3:]),
            )
            if result.is_decision and result.confidence >= 0.6:
                logger.debug(
                    "recognition: decision detected (confidence=%.2f) title=%r",
                    result.confidence,
                    result.extracted_title,
                )
        except Exception as exc:
            logger.debug("_recognition_pass failed (non-fatal): %s", exc)

    async def _call_budget_llm(self, chunk: Chunk) -> dict:
        """Call budget LLM to classify chunk for intelligence.

        Uses structured output (complete_structured) for guaranteed schema
        conformance. Falls back to freeform JSON if structured output fails.
        """
        from core.engine.capture.schemas import ObserverOutput

        context = "\n".join(f"[{c.chunk_type}] {c.content[:200]}" for c in self._recent_chunks[-5:])

        intel_section = (
            f"\n\nKnown patterns/conventions for this discipline (deviations from these are especially worth capturing):\n{self._intel_context}"
            if self._intel_context
            else ""
        )

        prompt = f"""Evaluate this chunk from an active work session.
Does it contain anything worth remembering?

Chunk type: {chunk.chunk_type}
Content: {chunk.content[:1000]}

Recent context:
{context}{intel_section}

Intelligence signals:
- A decision was made (chose A over B, and why)
- A correction occurred (initial approach failed, pivoted)
- Something unexpected was discovered
- A pattern was noted (recurring theme)
- A user preference was expressed (accepted/rejected something)
- A failure happened (and the cause was identified)
- A specific fact or convention was established"""

        try:
            result = await llm.complete_structured(prompt, ObserverOutput, model=settings.llm_budget_model)
            return result.model_dump()
        except Exception:
            # Fallback to freeform JSON if structured output fails
            return await llm.complete_json(
                prompt
                + '\n\nReturn JSON: {"has_intelligence": true|false, "observations": [{"content": "...", "type": "...", "confidence": 0.0-1.0, "discipline_hint": "..."}]}',
                model=settings.llm_budget_model,
            )

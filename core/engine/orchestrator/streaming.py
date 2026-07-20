# engine/orchestrator/streaming.py
"""Streaming orchestrator — yields typed events during task execution.

Event sequence:
  classification -> intelligence -> [framework] -> token+ -> done

Mirrors execute_task() but as an async generator instead of returning a dict.
Imports shared helpers from executor — no logic duplication.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.core.llm import llm
from core.engine.orchestrator.classifier import classify_task
from core.engine.orchestrator.executor import ARCHETYPE_INSTRUCTIONS, MODE_INSTRUCTIONS, _build_intel_context
from core.engine.orchestrator.loader import load_intelligence

logger = logging.getLogger(__name__)


# NOTE: This module is being deprecated in favor of engine.orchestration.stream().
# Chat streaming still uses this module until the orchestration layer supports
# token-level streaming via patterns.
async def stream_task(
    description: str,
    product_id: str,
    workspace_id: str,
    user_id: str,
    model: str | None = None,
    conversation_messages: list[dict] | None = None,
    source: str = "direct",
    system_prompt_override: str | None = None,
) -> AsyncIterator[dict]:
    """Stream task execution as typed events.

    Yields:
        {type: "classification", domain_path, archetype, mode, complexity}
        {type: "intelligence", insights_count, corrections_count, domain_path}
        {type: "framework", frameworks, composition_pattern}  (optional)
        {type: "token", text}  (repeated)
        {type: "done", task_id, full_output}
        {type: "error", message}  (on failure)
    """
    try:
        # 1. Classify
        classification = await classify_task(description)
        domain_path = classification.get("domain_path", "")
        archetype = classification["archetype"]
        mode = classification["mode"]

        yield {
            "type": "classification",
            "domain_path": domain_path,
            "archetype": archetype,
            "mode": mode,
            "complexity": classification.get("complexity", "simple"),
        }

        # 2. Load intelligence
        snapshot = await load_intelligence(domain_path, product_id, mode=mode)
        insights = snapshot.get("insights", [])
        corrections_count = sum(1 for i in insights if i.get("insight_type") == "correction")

        yield {
            "type": "intelligence",
            "insights_count": snapshot.get("total_count", len(insights)),
            "corrections_count": corrections_count,
            "domain_path": domain_path,
        }

        # 3. Build prompt context
        intel_context = _build_intel_context(snapshot)
        archetype_instruction = ARCHETYPE_INSTRUCTIONS.get(archetype, ARCHETYPE_INSTRUCTIONS["executor"])
        mode_instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["reactive"])

        system_prompt = f"""You are ACE, an AI intelligence engine built by QueryLabs. You help users by leveraging organizational intelligence — insights, patterns, and knowledge accumulated from ongoing work. When you reference your capabilities, refer to yourself as ACE, not as Claude or any other AI assistant.

{archetype_instruction}
{mode_instruction}
{intel_context}

Provide a thorough, high-quality response."""

        # Override system prompt for idea-scoped sessions
        if system_prompt_override:
            system_prompt = system_prompt_override + "\n\n" + intel_context

        # 4. Stream tokens
        llm_model = settings.llm_budget_model if model == "budget" else settings.llm_model
        full_output = ""

        if conversation_messages:
            # Multi-turn chat: use stream_messages with history
            messages = list(conversation_messages) + [{"role": "user", "content": description}]
            token_stream = llm.stream_messages(
                system=system_prompt,
                messages=messages,
                model=llm_model,
            )
        else:
            # Single-turn: use stream with prompt
            messages = [{"role": "user", "content": description}]
            token_stream = llm.stream_messages(
                system=system_prompt,
                messages=messages,
                model=llm_model,
            )

        async for token in token_stream:
            full_output += token
            yield {"type": "token", "text": token}

        # 5. Persist task record (only for direct tasks, not chat conversations)
        task_id = None
        if source != "chat":
            try:
                async with pool.connection() as db:
                    result = await db.query(
                        """
                        CREATE task SET
                            product = <record>$product,
                            user = <record>$user,
                            description = $description,
                            domain_path = $domain_path,
                            archetype = $archetype,
                            mode = $mode,
                            intelligence_loaded = $intel,
                            output = $output,
                            model_used = $model,
                            source = $source,
                            status = 'completed',
                            completed_at = time::now()
                        """,
                        {
                            "product": product_id,
                            "workspace": workspace_id,
                            "user": user_id,
                            "description": description,
                            "domain_path": domain_path,
                            "archetype": archetype,
                            "mode": mode,
                            "intel": snapshot,
                            "output": full_output,
                            "model": llm_model,
                            "source": source,
                        },
                    )
                    from core.engine.core.db import parse_one

                    task_record = parse_one(result) or {}
                    task_id = str(task_record.get("id", "unknown"))
            except Exception as exc:
                logger.warning("Failed to persist streaming task record: %s", exc)

        yield {
            "type": "done",
            "task_id": task_id,
            "full_output": full_output,
        }

    except Exception as exc:
        logger.error("Streaming task failed: %s", exc)
        yield {"type": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Multi-spin engagement streaming
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 50  # approximate characters per streamed chunk


def _chunk_text(text: str, size: int = _CHUNK_SIZE) -> list[str]:
    """Split *text* into roughly *size*-character segments on word boundaries."""
    chunks: list[str] = []
    buf = ""
    for word in text.split(" "):
        candidate = f"{buf} {word}" if buf else word
        if len(candidate) >= size:
            chunks.append(candidate)
            buf = ""
        else:
            buf = candidate
    if buf:
        chunks.append(buf)
    return chunks


async def stream_engagement(
    task_description: str,
    classification: dict,
    product_id: str,
    workspace_id: str = "workspace:default",
    history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """Stream a multi-spin engagement as SSE events.

    Yields dicts with ``{type, ...}`` for each event.  After each spin
    completes, streams the spin's content as token events.  Final synthesis
    streams token-by-token (chunked for smooth rendering).

    Event sequence::

        classification -> (spin_started -> intelligence -> spin_completed -> token+)* ->
        synthesis_started -> token+ -> done
    """
    from core.engine.orchestrator.engagement import execute_engagement

    try:
        # 1. Yield classification event with engagement info
        engagement = classification.get("engagement", {})
        perspectives = engagement.get("perspectives", [classification.get("perspective", "practitioner")])

        yield {
            "type": "classification",
            "domain_path": classification.get("domain_path", ""),
            "archetype": classification.get("archetype", ""),
            "mode": classification.get("mode", ""),
            "complexity": classification.get("complexity", "simple"),
            "engagement": {
                "perspectives": perspectives,
                "adversarial_pair": engagement.get("adversarial_pair"),
                "rationale": engagement.get("rationale", ""),
            },
        }

        # 2. Event queue + callback
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def _on_event(event: dict) -> None:
            await queue.put(event)

        # 3. Run execute_engagement in a background task
        result_future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _run() -> None:
            try:
                result = await execute_engagement(
                    task_description=task_description,
                    classification=classification,
                    product_id=product_id,
                    workspace_id=workspace_id,
                    event_callback=_on_event,
                )
                result_future.set_result(result)
            except Exception as exc:
                result_future.set_exception(exc)
            finally:
                await queue.put(None)  # sentinel

        task = asyncio.create_task(_run())

        # 4. Drain the queue, yielding events as they arrive
        completed_spins: list[dict] = []  # collect spin_completed events for content streaming
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

            # After each spin_completed, stream the spin's content as tokens
            if event.get("type") == "spin_completed":
                completed_spins.append(event)

        # Ensure background task is done and propagate errors
        await task
        result = result_future.result()

        # 5. Stream each spin's content as token events
        for spin in result.spins:
            for chunk in _chunk_text(spin.content):
                yield {
                    "type": "token",
                    "spin": next(
                        (i + 1 for i, s in enumerate(result.spins) if s.perspective == spin.perspective),
                        0,
                    ),
                    "perspective": spin.perspective,
                    "text": chunk,
                }

        # 6. If multi-spin, stream the merged synthesis as tokens
        if len(result.spins) > 1:
            for chunk in _chunk_text(result.merged_output):
                yield {"type": "token", "text": chunk}

        # 7. Done
        yield {
            "type": "done",
            "perspectives_used": result.perspectives_used,
            "merged_output": result.merged_output,
        }

    except Exception as exc:
        logger.error("Streaming engagement failed: %s", exc)
        yield {"type": "error", "message": str(exc)}

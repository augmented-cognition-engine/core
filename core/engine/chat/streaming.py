# engine/chat/streaming.py
"""SSE streaming adapter for chat responses.

Delegates to the orchestration layer's stream() function, which yields
typed OrchestratorEvents. This module maps them back to the SSE contract
that the portal expects: classification, intelligence, token, done, error,
spin_started, spin_completed, synthesis_started.

Persists user and assistant messages to the chat_message table.
"""

from __future__ import annotations

import json
import logging

from core.engine.core.db import pool

logger = logging.getLogger(__name__)


IDEA_DEVELOPMENT_PROMPT = """You are ACE, helping develop an idea into something actionable.

Current idea: {title}
Description: {raw_input}

Current brief:
{brief_text}

Your job:
1. EXPAND: Ask questions that fill gaps in the brief (what, why, what_we_know, open_questions, approach, effort, first_step, risks)
2. RESEARCH: Pull relevant intelligence and note what's missing
3. CHALLENGE: Surface risks, conflicts, dependencies, open questions
4. ASSESS: Track readiness — is this fleshed out enough to become a project?
5. SUGGEST: When ready, propose promotion:
   - Small scope: "This is a single task — want me to add it to the work queue?"
   - Medium scope: "This needs milestones — want me to create an initiative?"
   - Large scope: "This is big — I'd split it into separate initiatives: ..."

If the idea is too thin, say so: "I don't have enough to work with yet — what specifically would change?"
If you plan to research something, say so: "I'll look into this and have ideas next time you come back."

Be conversational, opinionated, and concise. You're a colleague, not a form."""


async def _get_idea_context(db, session_id: str) -> dict | None:
    """Check if session is linked to an idea and return context if so."""
    session_result = await db.query(
        "SELECT linked_to, linked_type FROM ONLY <record>$id",
        {"id": session_id},
    )
    session_rows = (
        session_result[0] if session_result and isinstance(session_result[0], list) else (session_result or [])
    )
    if not session_rows:
        return None

    session = session_rows[0] if isinstance(session_rows[0], dict) else {}
    if session.get("linked_type") != "idea" or not session.get("linked_to"):
        return None

    idea_id = session["linked_to"]
    idea_result = await db.query("SELECT * FROM ONLY <record>$id", {"id": idea_id})
    idea_rows = idea_result[0] if idea_result and isinstance(idea_result[0], list) else (idea_result or [])
    if not idea_rows:
        return None

    idea = idea_rows[0]
    brief = idea.get("brief") or {}
    brief_parts = []
    for field in [
        "what",
        "why",
        "what_we_know",
        "open_questions",
        "approach",
        "effort",
        "first_step",
        "risks",
    ]:
        val = brief.get(field)
        if val:
            brief_parts.append(f"  {field}: {val}")
    brief_text = "\n".join(brief_parts) if brief_parts else "  (empty — needs development)"

    system_prompt = IDEA_DEVELOPMENT_PROMPT.format(
        title=idea.get("title") or idea.get("raw_input", "")[:60],
        raw_input=idea.get("raw_input", ""),
        brief_text=brief_text,
    )

    return {
        "title": idea.get("title") or idea.get("raw_input", "")[:60],
        "idea_id": idea_id,
        "system_prompt": system_prompt,
    }


async def stream_chat_response(
    session_id: str,
    message: str,
    product_id: str,
    workspace_id: str,
    user_id: str,
):
    """Generator that yields typed SSE events for a streaming chat response.

    Event flow:
      1. Persist user message
      2. Load conversation history
      3. Delegate to stream_task() — yields classification, intelligence, token, done
      4. Persist assistant message after streaming completes
    """
    from core.engine.chat.handler import get_session_history
    from core.engine.orchestration import stream as orchestration_stream
    from core.engine.orchestration.request import OrchestrationRequest

    try:
        # Persist user message
        async with pool.connection() as db:
            await db.query(
                """
                CREATE chat_message SET
                    session = <record>$sess,
                    role = 'user',
                    content = $content,
                    created_at = time::now()
                """,
                {"sess": session_id, "content": message},
            )

        # ── Product intent fast path ────────────────────────────
        # Detect product intents BEFORE the heavy orchestration pipeline.
        # If matched, respond instantly with real product data.
        # Broad patterns (lookup, capability_detail) only match on the
        # first message to avoid swallowing normal follow-ups.
        try:
            from core.engine.product.conversation import ProductConversation

            # Check if this is the first user message in the session
            async with pool.connection() as db:
                count_result = await db.query(
                    "SELECT count() as c FROM chat_message WHERE session = <record>$sess AND role = 'user' GROUP ALL",
                    {"sess": session_id},
                )
            msg_count = 0
            if count_result and isinstance(count_result[0], list) and count_result[0]:
                msg_count = count_result[0][0].get("c", 0)
            elif count_result and isinstance(count_result[0], dict):
                msg_count = count_result[0].get("c", 0)

            pc = ProductConversation(pool)
            intent = await pc.detect_intent(message, is_first_message=(msg_count <= 1))
            if intent:
                product_result = await pc.handle_product_intent(intent, product_id)
                if product_result.get("handled"):
                    response_text = product_result.get("response", "")

                    yield {"event": "ping", "data": json.dumps({"type": "ping"})}

                    yield {
                        "event": "classification",
                        "data": json.dumps(
                            {
                                "type": "classification",
                                "domain_path": "",
                                "archetype": "analyst",
                                "mode": "reactive",
                                "complexity": "simple",
                            }
                        ),
                    }

                    if response_text:
                        yield {
                            "event": "token",
                            "data": json.dumps({"type": "token", "text": response_text}),
                        }

                    yield {
                        "event": "done",
                        "data": json.dumps(
                            {
                                "type": "done",
                                "task_id": None,
                                "full_output": response_text,
                            }
                        ),
                    }

                    # Persist assistant message
                    async with pool.connection() as db:
                        await db.query(
                            """CREATE chat_message SET
                                session = <record>$sess, role = 'assistant',
                                content = $content, created_at = time::now()""",
                            {"sess": session_id, "content": response_text},
                        )
                        await db.query(
                            """UPDATE <record>$sess SET
                                message_count = message_count + 2,
                                last_message_at = time::now(),
                                title = IF title THEN title ELSE $auto_title END""",
                            {"sess": session_id, "auto_title": message[:60]},
                        )

                    return  # short-circuit — don't run full orchestration
        except Exception as exc:
            logger.debug("Product intent fast path failed, falling through: %s", exc)

        # ── Full orchestration path (non-product intents) ───────

        # Load conversation history for multi-turn context.
        # Exclude the last message (the one we just persisted above) because
        # it becomes OrchestrationRequest.description / user_prompt.  Including
        # it here would create two consecutive "user" messages, which the
        # Anthropic API rejects (roles must alternate).
        history = await get_session_history(session_id)
        prior_history = [
            {"role": msg.get("role", "user"), "content": str(msg.get("content", ""))[:500]}
            for msg in history[:-1]
            if isinstance(msg, dict)
        ]
        conversation_messages = prior_history if prior_history else None

        # Check for idea-scoped session
        idea_context = None
        async with pool.connection() as db:
            idea_context = await _get_idea_context(db, session_id)

        # Build orchestration request
        request = OrchestrationRequest.from_chat(
            session_id=session_id,
            message=message,
            product_id=product_id,
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_messages=conversation_messages,
            system_prompt_override=idea_context["system_prompt"] if idea_context else None,
        )

        # Send initial keepalive so client knows connection is alive
        yield {"event": "ping", "data": json.dumps({"type": "ping"})}

        # Stream through orchestration layer
        full_output = ""
        had_tokens = False
        classification = {}
        task_id = None

        async for event in orchestration_stream(request):
            event_type = event.event_type

            if event_type == "classification_complete":
                classification = {
                    "domain_path": event.domain_path,
                    "archetype": event.archetype,
                    "mode": event.mode,
                }
                yield {
                    "event": "classification",
                    "data": json.dumps(
                        {
                            "type": "classification",
                            "domain_path": event.domain_path,
                            "archetype": event.archetype,
                            "mode": event.mode,
                            "complexity": event.complexity,
                        }
                    ),
                }

            elif event_type == "intelligence_loaded":
                yield {
                    "event": "intelligence",
                    "data": json.dumps(
                        {
                            "type": "intelligence",
                            "insights_count": event.insights_count,
                            "corrections_count": 0,
                            "domain_path": classification.get("domain_path", ""),
                        }
                    ),
                }

            elif event_type == "agent_token":
                full_output += event.text
                had_tokens = True
                yield {
                    "event": "token",
                    "data": json.dumps(
                        {
                            "type": "token",
                            "text": event.text,
                        }
                    ),
                }

            elif event_type == "task_completed":
                task_id = event.task_id if event.task_id else None
                if not full_output:
                    full_output = event.output_summary or ""

                # If no tokens were streamed (e.g. multi-perspective engagement
                # path), send the full output as a single token so the client
                # sees the response text.  Skip if tokens were already streamed
                # incrementally via agent_token events.
                if full_output and not had_tokens:
                    yield {
                        "event": "token",
                        "data": json.dumps(
                            {
                                "type": "token",
                                "text": full_output,
                            }
                        ),
                    }

                # Persist assistant message BEFORE yielding done —
                # the client may disconnect after reading done, which
                # cancels the generator and skips any code after yield.
                try:
                    async with pool.connection() as db:
                        await db.query(
                            """
                            CREATE chat_message SET
                                session = <record>$sess,
                                role = 'assistant',
                                content = $content,
                                created_at = time::now()
                            """,
                            {
                                "sess": session_id,
                                "content": full_output,
                            },
                        )
                        await db.query(
                            """
                            UPDATE <record>$sess SET
                                message_count = message_count + 2,
                                last_message_at = time::now(),
                                title = IF title THEN title ELSE $auto_title END
                            """,
                            {"sess": session_id, "auto_title": message[:60]},
                        )
                except Exception as exc:
                    logger.warning("Failed to persist assistant message: %s", exc)

                yield {
                    "event": "done",
                    "data": json.dumps(
                        {
                            "type": "done",
                            "task_id": task_id,
                            "full_output": full_output,
                        }
                    ),
                }

            elif event_type == "task_failed":
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {
                            "type": "error",
                            "message": event.error,
                        }
                    ),
                }

            elif event_type == "spin_started":
                yield {
                    "event": "spin_started",
                    "data": json.dumps(
                        {
                            "type": "spin_started",
                            "spin": event.spin,
                            "total": event.total,
                            "perspective": event.perspective,
                        }
                    ),
                }

            elif event_type == "spin_completed":
                yield {
                    "event": "spin_completed",
                    "data": json.dumps(
                        {
                            "type": "spin_completed",
                            "spin": event.spin,
                            "perspective": event.perspective,
                            "handoff": event.handoff,
                            "confidence": event.confidence,
                        }
                    ),
                }

            elif event_type == "synthesis_started":
                yield {
                    "event": "synthesis_started",
                    "data": json.dumps(
                        {
                            "type": "synthesis_started",
                            "perspectives": list(event.perspectives),
                        }
                    ),
                }

    except Exception as exc:
        from core.engine.core.error_buffer import error_buffer
        from core.engine.core.log_context import get_correlation_id

        cid = get_correlation_id()
        error_buffer.record(
            source="chat.streaming",
            error_type=type(exc).__name__,
            message=str(exc),
            cid=cid,
            context={
                "session_id": session_id,
                "user_id": user_id,
                "product_id": product_id,
            },
        )
        logger.error(
            "Chat streaming error: %s",
            exc,
            exc_info=True,
            extra={
                "session_id": session_id,
                "user_id": user_id,
                "product_id": product_id,
                "cid": cid,
            },
        )
        yield {"event": "error", "data": json.dumps({"type": "error", "message": str(exc)})}

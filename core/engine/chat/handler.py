"""Chat message handler — thin wrapper around execute_task().

Each chat message is a task with source='chat' and conversation context
from prior messages in the session. The orchestrator classifies, loads
intelligence, and executes exactly as for any task.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from core.engine.core.db import parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)

MAX_CONTEXT_MESSAGES = 20


async def create_session(
    product_id: str,
    workspace_id: str,
    user_id: str,
    title: str | None = None,
    linked_to: str | None = None,
    linked_type: str | None = None,
) -> dict:
    """Create a new chat session."""
    async with pool.connection() as db:
        from core.engine.core.db import parse_one

        result = await db.query(
            """
            CREATE chat_session SET
                user = <record>$user,
                title = $title,
                status = 'active',
                linked_to = $linked_to,
                linked_type = $linked_type,
                created_at = time::now()
            """,
            {
                "product": product_id,
                "workspace": workspace_id,
                "user": user_id,
                "title": title,
                "linked_to": linked_to,
                "linked_type": linked_type,
            },
        )
        row = parse_one(result) or {"status": "active"}
    return serialize_record(row)


async def get_session_history(session_id: str, limit: int = MAX_CONTEXT_MESSAGES) -> list[dict]:
    """Load conversation history for context."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT role, content, created_at FROM chat_message
            WHERE session = <record>$sess
            ORDER BY created_at ASC
            LIMIT $limit
            """,
            {"sess": session_id, "limit": limit},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])
    return [serialize_record(r) for r in rows if isinstance(r, dict)]


async def _handle_remember(text: str, session_id: str, product_id: str, workspace_id: str) -> dict:
    """Handle /remember — create explicit observation."""
    if not text.strip():
        return {"output": "Usage: /remember <what to remember>", "slash_command": "remember"}

    async with pool.connection() as db:
        await db.query(
            """
            CREATE observation SET
                content = $content,
                observation_type = 'user_declaration',
                confidence = 0.95,
                source = 'user_explicit',
                tags = ['user-declared'],
                synthesized = false,
                created_at = time::now()
            """,
            {"product": product_id, "workspace": workspace_id, "content": text.strip()},
        )

        # Also persist the chat messages
        await db.query(
            "CREATE chat_message SET session = <record>$sess, role = 'user', content = $content, created_at = time::now()",
            {"sess": session_id, "content": f"/remember {text}"},
        )
        await db.query(
            "CREATE chat_message SET session = <record>$sess, role = 'assistant', content = $content, created_at = time::now()",
            {"sess": session_id, "content": "Noted. I'll remember that."},
        )

    return {"output": "Noted. I'll remember that.", "slash_command": "remember"}


def _parse_window(window_str: str) -> timedelta:
    """Parse a time window string like '3d', '1w', '12h'. Default: 7 days."""
    if not window_str:
        return timedelta(days=7)
    match = re.match(r"(\d+)(d|w|h)", window_str.strip().lower())
    if not match:
        return timedelta(days=7)
    n = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return timedelta(days=n)
    if unit == "w":
        return timedelta(weeks=n)
    if unit == "h":
        return timedelta(hours=n)
    return timedelta(days=7)


async def _handle_catchup(args: str, session_id: str, product_id: str, workspace_id: str, user_id: str) -> dict:
    """Handle /catchup — gather context and generate conversational summary."""
    from core.engine.orchestrator.executor import execute_task

    window = _parse_window(args)
    since = datetime.now(timezone.utc) - window

    # Gather context from multiple sources
    sections = []

    async with pool.connection() as db:
        # Attention items (conflicts, ready ideas, paused initiatives)
        conflicts = parse_rows(
            await db.query(
                "SELECT id, status FROM conflict WHERE product = <record>$product AND status = 'pending'",
                {"product": product_id},
            )
        )
        if conflicts:
            sections.append(f"Pending conflicts: {len(conflicts)}")

        # Recent engine runs
        runs = parse_rows(
            await db.query(
                """
                SELECT engine, status, results, completed_at FROM engine_run
                WHERE product = <record>$product AND completed_at > $since AND status = 'completed'
                ORDER BY completed_at DESC LIMIT 10
                """,
                {"product": product_id, "since": since},
            )
        )
        if runs:
            run_summary = ", ".join(f"{r['engine']}({r.get('status', '?')})" for r in runs[:5])
            sections.append(f"Recent engine runs: {run_summary}")

        # Latest briefing
        briefing = parse_rows(
            await db.query(
                "SELECT content, created_at FROM briefing WHERE product = <record>$product ORDER BY created_at DESC LIMIT 1",
                {"product": product_id},
            )
        )
        if briefing:
            sections.append(f"Latest briefing highlights:\n{briefing[0].get('content', '')[:500]}")

        # Active initiatives
        initiatives = parse_rows(
            await db.query(
                "SELECT id, title, status FROM initiative WHERE product = <record>$product AND status IN ['active', 'paused']",
                {"product": product_id},
            )
        )
        if initiatives:
            init_list = ", ".join(f"{i.get('title', '?')} ({i['status']})" for i in initiatives[:5])
            sections.append(f"Active initiatives: {init_list}")

        # Ideas ready for action
        ideas = parse_rows(
            await db.query(
                "SELECT id, title, status FROM idea WHERE product = <record>$product AND status = 'ready'",
                {"product": product_id},
            )
        )
        if ideas:
            sections.append(f"Ideas ready for activation: {len(ideas)}")

    context = "\n\n".join(sections) if sections else "No significant activity found in this period."

    window_desc = args.strip() if args.strip() else "7d"
    catchup_prompt = (
        f"The user asked for a catch-up summary (window: {window_desc}). "
        f"Synthesize this into a brief, conversational catch-up — what happened, "
        f"what needs attention, and what's progressing well. Be concise and direct.\n\n"
        f"Context gathered:\n{context}"
    )

    result = await execute_task(
        description=catchup_prompt,
        product_id=product_id,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    # Persist messages
    async with pool.connection() as db:
        await db.query(
            "CREATE chat_message SET session = <record>$sess, role = 'user', content = $content, created_at = time::now()",
            {"sess": session_id, "content": f"/catchup {args}".strip()},
        )
        await db.query(
            "CREATE chat_message SET session = <record>$sess, role = 'assistant', content = $content, created_at = time::now()",
            {"sess": session_id, "content": result.get("output", "")},
        )

    result["slash_command"] = "catchup"
    return result


async def handle_message(
    session_id: str,
    message: str,
    product_id: str,
    workspace_id: str,
    user_id: str,
) -> dict:
    """Handle a chat message by routing through the orchestrator.

    Returns the task result dict.
    """
    from core.engine.orchestrator.executor import execute_task

    # Slash command routing
    stripped = message.strip()
    if stripped.startswith("/remember ") or stripped == "/remember":
        text = stripped[10:] if stripped.startswith("/remember ") else ""
        return await _handle_remember(text, session_id, product_id, workspace_id)

    if stripped.startswith("/catchup"):
        args = stripped[8:].strip()
        return await _handle_catchup(args, session_id, product_id, workspace_id, user_id)

    # Load prior conversation for context
    history = await get_session_history(session_id)

    # Onboarding intercept — first message only
    onboarding_prefix = None
    if not history:
        try:
            from core.engine.onboarding.scaffolder import needs_onboarding, scaffold_specialties

            if await needs_onboarding(product_id):
                specialties = await scaffold_specialties(message, product_id)
                if specialties:
                    spec_list = "\n".join(
                        f"- **{s.get('name', s['slug'])}** ({s['perspective']}, {s.get('discipline', '?')})"
                        for s in specialties
                    )
                    onboarding_prefix = (
                        f"I've set up {len(specialties)} knowledge areas based on what you told me:\n\n"
                        f"{spec_list}\n\n"
                        "My overnight research will start building knowledge in your core areas first.\n\n---\n\n"
                    )
        except Exception as exc:
            logging.getLogger(__name__).warning("Onboarding check failed: %s", exc)

    # Product intent detection — route to product modules before general executor
    try:
        from core.engine.product.conversation import ProductConversation

        pc = ProductConversation(pool)
        intent = await pc.detect_intent(message, is_first_message=(len(history) == 0))
        if intent:
            product_result = await pc.handle_product_intent(intent, product_id)
            if product_result.get("handled"):
                # Persist messages and return product response
                async with pool.connection() as db:
                    await db.query(
                        "CREATE chat_message SET session = <record>$sess, role = 'user', content = $content, created_at = time::now()",
                        {"sess": session_id, "content": message},
                    )
                    await db.query(
                        "CREATE chat_message SET session = <record>$sess, role = 'assistant', content = $content, created_at = time::now()",
                        {"sess": session_id, "content": product_result.get("response", "")},
                    )
                    await db.query(
                        "UPDATE <record>$sess SET message_count = message_count + 2, last_message_at = time::now(), title = IF title THEN title ELSE $auto_title END",
                        {"sess": session_id, "auto_title": message[:60]},
                    )

                if onboarding_prefix:
                    product_result["response"] = onboarding_prefix + product_result.get("response", "")
                    product_result["onboarding"] = True

                return {
                    "output": product_result.get("response", ""),
                    "data": product_result.get("data", {}),
                    "product_intent": intent,
                }
    except Exception as exc:
        logger.debug("Product intent detection failed (falling through): %s", exc)

    # Build conversation context string
    context_lines = []
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")[:500]
        context_lines.append(f"{role}: {content}")
    conversation_context = "\n".join(context_lines) if context_lines else None

    # Build the full description with conversation context
    if conversation_context:
        full_description = (
            f"[Conversation context — prior messages in this chat session:]\n"
            f"{conversation_context}\n\n"
            f"[Current message:]\n{message}"
        )
    else:
        full_description = message

    # Execute through orchestrator (general — non-product intents)
    result = await execute_task(
        description=full_description,
        product_id=product_id,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    # Persist messages
    async with pool.connection() as db:
        # User message
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

        # Assistant response
        task_id = result.get("id")
        await db.query(
            """
            CREATE chat_message SET
                session = <record>$sess,
                role = 'assistant',
                content = $content,
                task = $task_id,
                classification = $classification,
                created_at = time::now()
            """,
            {
                "sess": session_id,
                "content": result.get("output", ""),
                "task_id": task_id,
                "classification": {
                    "discipline": result.get("discipline", ""),
                    "archetype": result.get("archetype", ""),
                    "mode": result.get("mode", ""),
                },
            },
        )

        # Update session metadata
        await db.query(
            """
            UPDATE <record>$sess SET
                message_count = message_count + 2,
                last_message_at = time::now(),
                title = IF title THEN title ELSE $auto_title END
            """,
            {"sess": session_id, "auto_title": message[:60]},
        )

    # Prepend onboarding summary when this was the first message
    if onboarding_prefix and isinstance(result, dict):
        result["output"] = onboarding_prefix + result.get("output", "")
        result["onboarding"] = True

    return result

"""Core query loop — the while-true async generator heart of the ACE Runtime.

Design:
- Async generator: yields every Message produced (AssistantMessage, ToolResultMessage)
- While-true iteration with TurnState (no recursion — no stack overflow on long sessions)
- Per iteration: build API messages → call model → yield assistant → if tool_use:
  execute tools, yield results, continue → if no tool_use: done
- Max turns safety cap stops the loop after max_turns iterations
- _to_api_messages groups consecutive ToolResultMessages into a single user message
  because the Anthropic API requires strict user/assistant alternation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from core.engine.runtime.model_adapter import ModelAdapter
from core.engine.runtime.models import (
    AssistantMessage,
    Message,
    ToolResultMessage,
    Transition,
    TurnState,
    UserMessage,
)
from core.engine.runtime.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# QueryParams
# ---------------------------------------------------------------------------


@dataclass
class QueryParams:
    """All inputs needed to drive a query_loop call."""

    system: str
    messages: list[Message]
    adapter: ModelAdapter
    executor: ToolExecutor
    tool_schemas: list[dict[str, Any]] = field(default_factory=list)
    max_turns: int = 100
    max_tokens: int = 8192
    thinking: str = "adaptive"
    error_recovery: Any = None  # Optional ErrorRecovery
    token_budget: Any = None  # Optional TokenBudget
    stream: bool = False  # yield str/ThinkingDelta chunks when True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def query_loop(params: QueryParams) -> AsyncGenerator[Message, None]:
    """Core while-true loop. Yields every Message produced during the session.

    Consumers switch on message.type:
    - "assistant"   → text/tool_use response from the model
    - "tool_result" → output from tool execution
    - "system"      → lifecycle events (max_turns, errors)
    """
    state = TurnState(messages=list(params.messages))

    while True:
        if state.turn_count > params.max_turns:
            logger.warning("query_loop: max_turns (%d) reached", params.max_turns)
            state.transition = Transition.MAX_TURNS
            return

        api_messages = _to_api_messages(state.messages)

        # Call model — streaming or non-streaming
        assistant_msg: AssistantMessage | None = None

        if params.stream and hasattr(params.adapter, "stream_model"):
            async for chunk in params.adapter.stream_model(
                system=params.system,
                messages=api_messages,
                tools=params.tool_schemas,
                max_tokens=params.max_tokens,
                thinking=params.thinking,
            ):
                if isinstance(chunk, AssistantMessage):
                    assistant_msg = chunk
                else:
                    yield chunk  # str or ThinkingDelta — consumed by TUI _iter_events()
        elif params.stream:
            raise NotImplementedError(
                f"adapter {type(params.adapter).__name__!r} does not implement stream_model; "
                "set stream=False or add stream_model() to the adapter"
            )
        else:
            async for msg in params.adapter.call_model(
                system=params.system,
                messages=api_messages,
                tools=params.tool_schemas,
                max_tokens=params.max_tokens,
                thinking=params.thinking,
            ):
                assistant_msg = msg

        if assistant_msg is None:
            logger.error("query_loop: adapter returned no message on turn %d", state.turn_count)
            state.transition = Transition.ERROR
            return

        # Append assistant message to state history and yield to consumer
        state.messages.append(assistant_msg)

        # Check for max_tokens stop and attempt recovery
        if assistant_msg.stop_reason == "max_tokens" and params.error_recovery:
            if params.error_recovery.try_max_output_recovery():
                nudge = params.error_recovery.get_recovery_nudge()
                nudge_msg = UserMessage(content=nudge, is_meta=True)
                yield assistant_msg
                state.messages.append(nudge_msg)
                state.turn_count += 1
                continue  # retry with nudge

        yield assistant_msg

        # If no tool calls, the model is done
        if not assistant_msg.tool_use:
            state.transition = Transition.COMPLETED
            return

        # Execute all requested tools
        results = await params.executor.execute(assistant_msg.tool_use)

        # Yield each result to consumer and append to history
        for result in results:
            state.messages.append(result)
            yield result

        # Check token budget after tool results.
        # Only activate when a real total is set — TokenBudget(total=None) means
        # "no budget constraint", so the gate must be skipped in that case.
        if (
            params.token_budget
            and params.token_budget.total is not None
            and params.token_budget.should_continue(
                sum(1 for m in state.messages if isinstance(m, (UserMessage, AssistantMessage)))
            )
            == "stop"
        ):
            state.transition = Transition.COMPLETED
            return

        # Increment turn counter and loop back to call the model again
        state.turn_count += 1


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


def _to_api_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert internal Message types to Anthropic API message dicts.

    CRITICAL: consecutive ToolResultMessages MUST be grouped into a single
    user message — the Anthropic API requires strict user/assistant alternation
    and tool results must be delivered as a user-role message containing a list
    of tool_result content blocks.
    """
    api_msgs: list[dict[str, Any]] = []
    i = 0

    while i < len(messages):
        msg = messages[i]
        i += 1

        if isinstance(msg, UserMessage):
            api_msgs.append({"role": "user", "content": msg.content})

        elif isinstance(msg, AssistantMessage):
            content: list[dict[str, Any]] = []
            if msg.content:
                content.append({"type": "text", "text": msg.content})
            for tu in msg.tool_use:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tu.id,
                        "name": tu.name,
                        "input": tu.input,
                    }
                )
            if not content:
                content.append({"type": "text", "text": ""})
            api_msgs.append({"role": "assistant", "content": content})

        elif isinstance(msg, ToolResultMessage):
            # Group ALL consecutive ToolResultMessages into one user message
            tool_results: list[dict[str, Any]] = []
            # Back up — msg was already consumed above; process it first
            tr = msg
            while True:
                entry: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": tr.tool_use_id,
                    "content": tr.content,
                }
                if tr.is_error:
                    entry["is_error"] = True
                tool_results.append(entry)

                if i < len(messages) and isinstance(messages[i], ToolResultMessage):
                    tr = messages[i]
                    i += 1
                else:
                    break

            api_msgs.append({"role": "user", "content": tool_results})

        # SystemMessage and ToolUseMessage are not sent to the API

    return api_msgs

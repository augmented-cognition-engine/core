"""Runtime — the public SDK entry point for the ACE agent runtime.

Usage::

    from core.engine.runtime import Runtime
    from core.engine.runtime.model_adapter import MockAdapter

    runtime = Runtime(adapter=MockAdapter(responses=["Hello!"]))
    async for msg in runtime.chat("hi"):
        print(msg)

The Runtime class:
- Owns the conversation history across multiple chat() calls
- Registers the six built-in tools (bash, read, write, edit, grep, glob)
- Creates a ToolExecutor that dispatches tool invocations
- Delegates each query to query_loop, yielding every produced Message
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

from core.engine.orchestrator.executor import ARCHETYPE_INSTRUCTIONS, MODE_INSTRUCTIONS

try:
    from core.engine.events.bus import bus as event_bus
except ImportError:
    event_bus = None
from core.engine.runtime.adapters import get_adapter
from core.engine.runtime.auto_extract import AutoExtractor
from core.engine.runtime.context_manager import ContextManager
from core.engine.runtime.error_recovery import ErrorRecovery
from core.engine.runtime.events import ThinkingDelta
from core.engine.runtime.intelligence import IntelligenceLayer
from core.engine.runtime.mid_session_observer import MidSessionObserver
from core.engine.runtime.model_adapter import ModelAdapter
from core.engine.runtime.models import (
    AssistantMessage,
    IntelligenceLoadedMessage,
    Message,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
)
from core.engine.runtime.progress import ProgressTracker
from core.engine.runtime.prompt_cache import PromptCacheManager
from core.engine.runtime.query_loop import QueryParams, query_loop
from core.engine.runtime.reflection import ReflectionLoop
from core.engine.runtime.retry import RetryPolicy
from core.engine.runtime.safety import SafetyLimits
from core.engine.runtime.session_memory import SessionMemory
from core.engine.runtime.token_budget import TokenBudget
from core.engine.runtime.token_tracker import TokenTracker
from core.engine.runtime.tool_executor import ToolExecutor
from core.engine.runtime.tools import ToolRegistry
from core.engine.runtime.tools.ace_tools import make_ace_tools
from core.engine.runtime.tools.bash import BashTool
from core.engine.runtime.tools.file_edit import FileEditTool
from core.engine.runtime.tools.file_read import FileReadTool
from core.engine.runtime.tools.file_write import FileWriteTool
from core.engine.runtime.tools.glob_tool import GlobTool
from core.engine.runtime.tools.grep import GrepTool
from core.engine.runtime.tools.web_tools import make_web_tools
from core.engine.runtime.transcript import TranscriptManager
from core.engine.runtime.verification_nudge import VerificationNudge

# ---------------------------------------------------------------------------
# Base system prompt
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """You are ACE, an AI agent that helps with software engineering tasks.

You have tools available to read files, write files, edit files, search code, and run shell commands. Use them to accomplish the user's request.

After every file modification, verify your changes are correct. If you can't verify (no test exists, can't run the code), say so explicitly rather than claiming success.

Report outcomes faithfully: if tests fail, say so with the relevant output. Never claim "all tests pass" when output shows failures."""


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class Runtime:
    """Public SDK entry point for the ACE agent runtime.

    Parameters
    ----------
    model:
        Model identifier passed to the adapter.  Ignored when a custom
        ``adapter`` is supplied.
    adapter:
        A :class:`ModelAdapter`-compatible object.  When *None* a
        :class:`~engine.runtime.model_adapter.ClaudeAdapter` is created
        automatically using the configured model name.
    system:
        Custom system prompt.  Defaults to ``BASE_SYSTEM_PROMPT``.
    max_turns:
        Maximum query-loop iterations before aborting.
    max_tokens:
        Maximum tokens per model call.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        adapter: ModelAdapter | None = None,
        system: str | None = None,
        max_turns: int = 100,
        max_tokens: int = 8192,
        thinking: str = "disabled",
        enable_intelligence: bool = True,
        product_id: str = "product:platform",
        transcript_path: str | None = None,
        lint_cmd: str | None = None,
        test_cmd: str | None = None,
    ) -> None:
        self._model = model
        self._system = system or BASE_SYSTEM_PROMPT
        self._max_turns = max_turns
        self._max_tokens = max_tokens
        self._thinking = thinking

        # Active product_id — used by close() and by TUI /switch
        self._product_id: str = product_id

        # Learned model-tier routing — seeded once per runtime on first turn.
        self._routing_warmed: bool = False

        # Intelligence layer (optional)
        if enable_intelligence:
            self._intelligence: IntelligenceLayer | None = IntelligenceLayer(product_id)
            self._extractor: AutoExtractor | None = AutoExtractor(product_id)
            self._session_memory: SessionMemory | None = SessionMemory()
            self._mid_session_observer: MidSessionObserver | None = MidSessionObserver(product_id)
        else:
            self._intelligence = None
            self._extractor = None
            self._session_memory = None
            self._mid_session_observer = None

        # Token tracker and context manager — always present
        self._token_tracker = TokenTracker()
        self._context_manager = ContextManager()

        # M3-M8 modules — always present
        self._safety = SafetyLimits(max_turns=max_turns)
        self._retry_policy = RetryPolicy()
        self._token_budget = TokenBudget()
        self._error_recovery = ErrorRecovery()
        self._prompt_cache = PromptCacheManager()
        self._progress = ProgressTracker()
        self._verification_nudge = VerificationNudge()
        self._transcript: TranscriptManager | None = TranscriptManager(transcript_path) if transcript_path else None
        self._reflection: ReflectionLoop | None = (
            ReflectionLoop(lint_cmd=lint_cmd, test_cmd=test_cmd) if (lint_cmd or test_cmd) else None
        )

        # Build adapter — use get_adapter when none provided
        if adapter is not None:
            self._adapter: ModelAdapter = adapter
        else:
            self._adapter = get_adapter(model)

        # Register built-in tools
        self._registry = ToolRegistry()
        for tool in [
            BashTool(),
            FileReadTool(),
            FileWriteTool(),
            FileEditTool(),
            GrepTool(),
            GlobTool(),
        ]:
            self._registry.register(tool)

        # Register ACE self-tools (Layer 2) when intelligence is enabled
        if enable_intelligence:
            for tool in make_ace_tools(product_id, model):
                self._registry.register(tool)

        # Register web tools (always available — degrade gracefully at runtime)
        for tool in make_web_tools():
            self._registry.register(tool)

        # Register browser tool (optional dep — returns install msg if playwright absent)
        from core.engine.runtime.tools.browser_tool import BrowserTool

        self._registry.register(BrowserTool())

        self._executor = ToolExecutor(self._registry)

        # Conversation history — grows across chat() calls
        self._messages: list[Message] = []

        # Current-turn discipline — set by intelligence layer, used by reflection
        self._current_discipline: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(self, input: str, *, stream: bool = False) -> AsyncGenerator[Message, None]:
        """Send a user message and yield every Message produced.

        The conversation history is persisted across calls so subsequent
        invocations see all prior turns.

        Parameters
        ----------
        input:
            The user's message text.

        Yields
        ------
        Message
            AssistantMessage and ToolResultMessage instances produced by
            the query loop.
        """
        user_msg = UserMessage(content=input)
        self._messages.append(user_msg)

        # Seed learned model-tier routing once (fail-safe, off the DB hot path).
        await self._warm_learned_routing()

        # Emit turn_started event
        if event_bus:
            asyncio.get_event_loop().create_task(
                event_bus.emit(
                    "runtime.turn_started",
                    {
                        "input": input[:200],
                        "model": self._model,
                        "turn_count": len([m for m in self._messages if isinstance(m, UserMessage)]),
                    },
                )
            )

        # Persist user message BEFORE API call (crash recovery)
        if self._transcript:
            self._transcript.append(user_msg)

        # Safety check: cost
        cost_ok, cost_reason = self._safety.check_cost(self._token_tracker.estimated_cost_usd)
        if not cost_ok:
            sys_msg = SystemMessage(content=cost_reason, subtype="cost_limit")
            yield sys_msg
            return

        # Compose system prompt — augmented if intelligence is enabled
        if self._intelligence is not None:
            classification, intel_context, composition = await self._intelligence.classify_compose_and_load(input)
            self._current_discipline = classification.get("discipline") if classification else None
            code_ctx = await self._intelligence.load_code_context(input)
            fw_prompts = await self._load_framework_prompts(composition)

            # AI-side briefing: grounds the dispatched AI in substrate state
            # before reasoning starts. Closes the cold-start ignorance gap
            # every IDE-layer AI suffers. Feature-flagged for gradual rollout.
            ai_briefing_text: str | None = None
            from core.engine.core.config import settings

            if getattr(settings, "enable_ai_briefing", False):
                try:
                    from core.engine.ai_briefing import briefing_for_dispatched_ai

                    meta_skills = (
                        list(composition.meta_skills)
                        if composition is not None and getattr(composition, "meta_skills", None)
                        else None
                    )
                    ai_briefing_text = await briefing_for_dispatched_ai(self._product_id, meta_skills=meta_skills)
                except Exception as exc:
                    logger.debug("AI briefing assembly failed; continuing without it: %s", exc)
                    ai_briefing_text = None

            system = self._assemble_system_prompt(
                classification=classification,
                intel_context=intel_context or None,
                session_memory=self._session_memory.get_content() if self._session_memory else None,
                code_context=code_ctx or None,
                composition=composition,
                framework_prompts=fw_prompts,
                ai_briefing=ai_briefing_text,
            )
            # Yield intelligence context summary for TUI display
            discipline = classification.get("discipline", "")
            entries = [(discipline, 1)] if discipline else []
            yield IntelligenceLoadedMessage(entries=entries)
        else:
            system = self._system

        # Track prompt cache
        tool_names = self._registry.list_names()
        if self._prompt_cache.has_changed(system, tool_names):
            self._prompt_cache.record(system, tool_names)

        # Reset error recovery for new turn
        self._error_recovery.reset()

        # Context compaction — rotate before the call if context is nearing the limit
        messages_for_query = list(self._messages)
        if self._token_tracker.should_compact():
            before_tokens = self._token_tracker.estimate_tokens(self._messages)
            messages_for_query = self._context_manager.compact(
                messages_for_query,
                intelligence=self._intelligence,
                session_memory=self._session_memory,
                current_query=input,
            )
            after_tokens = self._token_tracker.estimate_tokens(messages_for_query)
            logger.debug("Context compacted: %d → %d messages", len(self._messages), len(messages_for_query))
            yield SystemMessage(
                content=f"context compacted — {before_tokens // 1000}K → {after_tokens // 1000}K tokens",
                subtype="compaction",
                before_tokens=before_tokens,
                after_tokens=after_tokens,
            )

        params = QueryParams(
            system=system,
            messages=messages_for_query,
            adapter=self._adapter,
            executor=self._executor,
            tool_schemas=self._registry.list_schemas(),
            max_turns=self._max_turns,
            max_tokens=self._max_tokens,
            thinking=self._thinking,
            error_recovery=self._error_recovery,
            token_budget=self._token_budget,
            stream=stream,
        )

        async for msg in query_loop(params):
            # Streaming chunks (str / ThinkingDelta) pass through to TUI but must not be persisted
            if isinstance(msg, (str, ThinkingDelta)):
                yield msg
                continue
            self._messages.append(msg)

            # Token tracking
            if isinstance(msg, AssistantMessage) and msg.usage:
                self._token_tracker.record_turn(
                    input_tokens=msg.usage.get("input_tokens", 0),
                    output_tokens=msg.usage.get("output_tokens", 0),
                )

            # Progress tracking
            if isinstance(msg, ToolResultMessage):
                tool_name = msg.tool_use_id.split("_")[0] if "_" in msg.tool_use_id else "tool"
                self._progress.record_tool(
                    name=tool_name,
                    summary=msg.content[:40],
                )

            # Persist every message
            if self._transcript:
                self._transcript.append(msg)

            yield msg

        # Emit turn_completed event
        if event_bus:
            asyncio.get_event_loop().create_task(
                event_bus.emit(
                    "runtime.turn_completed",
                    {
                        "model": self._model,
                        "message_count": len(self._messages),
                        "tokens": self._token_tracker.summary() if self._token_tracker else {},
                    },
                )
            )

        # Post-turn: verification nudge — deliver if threshold crossed
        self._verification_nudge.record_task_completed()
        if self._verification_nudge.should_nudge():
            nudge_msg = SystemMessage(
                content=self._verification_nudge.get_nudge_message(),
                subtype="verification_nudge",
            )
            self._messages.append(nudge_msg)
            yield nudge_msg

        # Post-turn: update session memory sections from history
        if self._update_session_memory():
            # LLM sections fire-and-forget — fills current_state/decisions/learnings via Haiku
            asyncio.get_event_loop().create_task(self._fill_session_memory_llm())

        # Post-turn: run reflection validation if file edits happened this turn
        if self._reflection is not None and self._reflection.can_reflect():
            edited = self._edited_files_this_turn()
            if edited:
                errors = await self._reflection.validate(edited, discipline=self._current_discipline)
                if errors:
                    feedback_msg = UserMessage(
                        content=f"Validation errors from your last changes:\n\n{errors}\n\nFix these before continuing.",
                        is_meta=True,
                    )
                    self._messages.append(feedback_msg)
                    logger.debug("Reflection: injected validation errors (%d chars)", len(errors))

        # Fire-and-forget extraction after each turn (Tier 3 — batch, session end)
        if self._extractor is not None:
            self._extractor.fire_and_forget(self._messages)

        # Tier 2 — near-real-time: Haiku signal scan every N turns
        if self._mid_session_observer is not None:
            self._mid_session_observer.record_turn(self._messages)

    def clear_messages(self) -> None:
        """Clear conversation history."""
        self._messages.clear()

    def restore_messages(self, messages: list) -> None:
        """Replace conversation history (for session resume)."""
        self._messages = list(messages)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def _warm_learned_routing(self) -> None:
        """One-time, fail-safe seed of learned model-tier routing.

        Loads persisted escalation counts and refreshes route_model's in-memory
        cache so chronically-escalating task types start one tier higher. Guarded
        so it runs at most once per runtime; never raises (routing must degrade to
        the static table if the learning store is unavailable).
        """
        if self._routing_warmed:
            return
        # Set the guard before awaiting so a concurrent turn does not double-warm;
        # reset it on failure so a transient first-turn DB blip can retry next turn
        # (rather than leaving the cache empty for the whole session).
        self._routing_warmed = True
        try:
            from core.engine.intelligence.cascade_router import load_escalation_counts
            from core.engine.runtime.model_config import refresh_learned_routing

            await load_escalation_counts(self._product_id)
            await refresh_learned_routing(self._product_id)
        except Exception:
            self._routing_warmed = False
            logger.debug("learned-routing warm skipped (will retry next turn)", exc_info=True)

    async def close(self, product_id: str | None = None) -> None:
        """Flush session memory + close any tools that hold external resources."""
        if self._session_memory is not None:
            pid = product_id or self._product_id
            count = await self._session_memory.promote_to_graph(pid)
            logger.debug("Session memory: promoted %d sections to graph", count)

        # Flush learned-routing escalation counts so the signal survives restarts.
        try:
            from core.engine.intelligence.cascade_router import persist_escalation_counts

            await persist_escalation_counts(product_id or self._product_id)
        except Exception:
            logger.warning("persist_escalation_counts on close failed — continuing teardown", exc_info=True)

        # Close tools that hold resources (e.g., BrowserTool → Playwright)
        for tool in self._registry._tools.values():
            try:
                await tool.close()
            except Exception:
                logger.warning("Error closing tool %r — continuing teardown", tool.name, exc_info=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_session_memory(self) -> bool:
        """Populate session memory sections from message history without an LLM call.

        Extracts:
        - task: first user message (the original intent)
        - files_modified: paths from file_write / file_edit tool invocations
        - errors: content of failed tool results

        Returns True if an update was performed (caller may schedule LLM fill).
        """
        if self._session_memory is None:
            return False

        token_count = self._token_tracker.estimated_context_tokens
        tool_count = sum(1 for m in self._messages if isinstance(m, ToolResultMessage))
        if not self._session_memory.should_update(token_count, tool_count):
            return False

        # task — first real user message
        user_msgs = [m for m in self._messages if isinstance(m, UserMessage) and not m.is_meta]
        if user_msgs:
            self._session_memory.update_section("task", user_msgs[0].content[:500])

        # files_modified — deduplicated paths from file tool invocations
        seen: list[str] = []
        for m in self._messages:
            if isinstance(m, AssistantMessage):
                for tu in m.tool_use:
                    if tu.name in {"file_write", "file_edit"}:
                        path = tu.input.get("file_path", tu.input.get("path", ""))
                        if path and path not in seen:
                            seen.append(path)
        if seen:
            self._session_memory.update_section("files_modified", "\n".join(seen[:20]))

        # errors — last 5 failed tool results
        errors = [m.content[:200] for m in self._messages if isinstance(m, ToolResultMessage) and m.is_error]
        if errors:
            self._session_memory.update_section("errors", "\n---\n".join(errors[-5:]))

        self._session_memory.mark_updated(token_count, tool_count)
        return True

    async def _fill_session_memory_llm(self) -> None:
        """Fire-and-forget: fill current_state, decisions, learnings via Haiku.

        Called only when _update_session_memory() returns True (i.e. enough
        token/tool growth has occurred). Uses the weak model so it's fast and cheap.
        """
        if self._session_memory is None:
            return

        # Compact conversation excerpt — skip meta messages and cap length
        recent = [
            m
            for m in self._messages[-20:]
            if isinstance(m, (UserMessage, AssistantMessage)) and not (isinstance(m, UserMessage) and m.is_meta)
        ]
        if len(recent) < 2:
            return

        excerpt = "\n".join(
            f"{'User' if isinstance(m, UserMessage) else 'Assistant'}: {m.content[:300]}" for m in recent
        )

        try:
            from core.engine.core.llm import get_llm
            from core.engine.runtime.model_config import route_model

            haiku = route_model("context_summary")
            result = await get_llm().complete_json(
                f"Extract from this conversation. Reply with ONLY valid JSON — no markdown:\n"
                f'{{"current_state": "1-2 sentence description of what is happening right now",'
                f'"decisions": "bullet list of key decisions made, or empty string",'
                f'"learnings": "bullet list of learnings or corrections, or empty string"}}\n\n'
                f"Conversation:\n{excerpt}",
                model=haiku,
                max_tokens=512,
            )
            if result.get("current_state"):
                self._session_memory.update_section("current_state", result["current_state"])
            if result.get("decisions"):
                self._session_memory.update_section("decisions", result["decisions"])
            if result.get("learnings"):
                self._session_memory.update_section("learnings", result["learnings"])
        except Exception as exc:
            logger.debug("LLM session memory fill failed: %s", exc)

    def _edited_files_this_turn(self) -> list[str]:
        """Return file paths modified by file_write / file_edit in the last assistant turn."""
        # Walk backwards until the last UserMessage (that's where this turn started)
        files: list[str] = []
        for m in reversed(self._messages):
            if isinstance(m, UserMessage):
                break
            if isinstance(m, AssistantMessage):
                for tu in m.tool_use:
                    if tu.name in {"file_write", "file_edit"}:
                        path = tu.input.get("file_path", tu.input.get("path", ""))
                        if path and path not in files:
                            files.append(path)
        return files

    async def _load_framework_prompts(self, composition) -> dict[str, str]:
        """Fetch system_prompt strings from DB for all resolved instrument slugs.

        Returns a slug→system_prompt dict; empty dict on any failure (non-fatal).
        """
        if not composition or not composition.resolved_instruments:
            return {}
        all_slugs = {slug for slugs in composition.resolved_instruments.values() for slug in slugs}
        if not all_slugs:
            return {}
        try:
            from core.engine.core.db import parse_rows, pool

            async with pool.connection() as db:
                rows = await db.query(
                    "SELECT slug, system_prompt FROM framework WHERE slug IN $slugs",
                    {"slugs": list(all_slugs)},
                )
                return {row["slug"]: row["system_prompt"] for row in parse_rows(rows) if row.get("system_prompt")}
        except Exception:
            logger.warning("Runtime: framework prompt fetch failed — slugs=%r", all_slugs, exc_info=True)
            return {}

    def _assemble_system_prompt(
        self,
        classification: dict | None = None,
        intel_context: str | None = None,
        session_memory: str | None = None,
        code_context: str | None = None,
        composition=None,
        framework_prompts: dict | None = None,
        ai_briefing: str | None = None,
    ) -> str:
        """Assemble the full system prompt from BASE_SYSTEM_PROMPT + intelligence layers.

        ai_briefing (optional): a rendered AI-side briefing payload (architecture
        digest + recent decisions + active capabilities + known gaps + active
        meta-skills) injected as a top-level prefix. Closes the cold-start
        ignorance gap for dispatched AIs — they start grounded in substrate
        state instead of theorizing. Caller pre-builds via
        core.engine.ai_briefing.briefing_for_dispatched_ai(product_id, meta_skills).
        """
        parts: list[str] = []
        if ai_briefing:
            parts.append(ai_briefing)
        parts.append(self._system)

        if classification:
            sections = []
            discipline = classification.get("discipline", "")
            if discipline:
                sections.append(f"## Active Discipline: {discipline}")
            archetype = classification.get("archetype", "")
            if archetype and archetype in ARCHETYPE_INSTRUCTIONS:
                sections.append(ARCHETYPE_INSTRUCTIONS[archetype])
            mode = classification.get("mode", "")
            if mode and mode in MODE_INSTRUCTIONS:
                sections.append(MODE_INSTRUCTIONS[mode])
            if sections:
                parts.append("\n".join(sections))

        if composition and composition.meta_skills:
            from core.engine.cognition.models import derive_depth

            depth = derive_depth(
                classification.get("mode", "reactive") if classification else "reactive",
                classification.get("complexity", "moderate") if classification else "moderate",
            )

            # Inject full framework content when prompts are available (Wave 6 demo-mode).
            # Falls back to phase-label summary when framework_prompts is empty.
            if framework_prompts and composition.prompt_sections:
                from core.engine.cognition.fusion import PromptFusion

                meta_tag = f"depth:{depth}  meta-skills:{' + '.join(composition.meta_skills)}"
                fused = PromptFusion().fuse(composition, framework_prompts)
                # Embed meta-tag into PromptFusion's own header line.
                fused = fused.replace(
                    "## Cognitive Structure\n",
                    f"## Cognitive Structure  ({meta_tag})\n",
                    1,
                )
                parts.append(fused)
            else:
                # Lightweight fallback: phase labels only (no DB content available).
                cog_lines = [
                    f"## Reasoning Structure  (depth:{depth}  meta-skills:{' + '.join(composition.meta_skills)})",
                    "Structure your thinking through these cognitive phases in order:",
                ]
                for i, phase in enumerate(composition.active_phases):
                    slugs = composition.resolved_instruments.get(str(i), [])
                    slug_hint = f" [{', '.join(slugs)}]" if slugs else ""
                    cog_lines.append(
                        f"  {i + 1}. {phase.cognitive_function.upper()}{slug_hint}: {phase.output_schema or ''}"
                    )
                parts.append("\n".join(cog_lines))

        if intel_context:
            parts.append(f"\n# Intelligence\n{intel_context}")

        if session_memory:
            parts.append(f"\n# Session Context\n{session_memory}")

        if code_context:
            parts.append(f"\n# Code Context\n{code_context}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def token_tracker(self) -> TokenTracker:
        """The token tracker for this runtime session."""
        return self._token_tracker

    @property
    def context_manager(self) -> ContextManager:
        """The context manager for this runtime session."""
        return self._context_manager

    @property
    def messages(self) -> list[Message]:
        """A copy of the full conversation history."""
        return list(self._messages)

    @property
    def tool_names(self) -> list[str]:
        """Names of all registered tools."""
        return self._registry.list_names()

    @property
    def safety(self) -> SafetyLimits:
        """Safety limits for this runtime session."""
        return self._safety

    @property
    def progress(self) -> ProgressTracker:
        """Progress tracker for this runtime session."""
        return self._progress

    @property
    def prompt_cache(self) -> PromptCacheManager:
        """Prompt cache manager for this runtime session."""
        return self._prompt_cache

    @property
    def verification_nudge(self) -> VerificationNudge:
        """Verification nudge tracker for this runtime session."""
        return self._verification_nudge

    @property
    def product_id(self) -> str:
        """The product this runtime is scoped to."""
        return self._product_id

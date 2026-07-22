# engine/core/llm.py
import asyncio
import contextvars
import functools
import json
import logging
import os
import re
import shutil
import tempfile
import time
from typing import AsyncIterator, Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx
from anthropic import AsyncAnthropic, AuthenticationError
from pydantic import BaseModel

from core.engine.core.config import settings
from core.engine.core.log_context import get_correlation_id
from core.engine.core.tokens import get_accumulator

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> str: ...

    async def complete_json(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> dict: ...

    def stream(self, prompt: str, model: str | None = None, max_tokens: int = 4096) -> AsyncIterator[str]: ...

    def stream_messages(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]: ...

    async def complete_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> BaseModel: ...


def _semantic_effort(model: str | None) -> str:
    """Resolve ACE's provider-neutral effort policy for a requested model."""
    requested = model or settings.llm_model
    mapping = {
        settings.llm_budget_model: getattr(settings, "llm_budget_effort", "default"),
        settings.llm_model: getattr(settings, "llm_effort", "default"),
        settings.llm_reasoning_model: getattr(settings, "llm_reasoning_effort", "high"),
        settings.llm_frontier_model: getattr(settings, "llm_frontier_effort", "xhigh"),
        "claude-sonnet-4-6": "default",
        "claude-opus-4-6": "high",
    }
    return str(mapping.get(requested, "default"))


def _claude_effort_config(model: str | None) -> dict[str, str]:
    """Return an Anthropic output_config fragment only for supported models."""
    requested = model or settings.llm_model
    supported = requested.startswith(("claude-fable-5", "claude-opus-4-8", "claude-sonnet-5")) or requested in {
        "claude-opus-4-6",
        "claude-sonnet-4-6",
    }
    effort = _semantic_effort(requested)
    if supported and effort == "none":
        raise ValueError(
            f"unsupported Claude effort 'none' for {requested}; use default, low, medium, high, xhigh, or max"
        )
    return {"effort": effort} if supported and effort != "default" else {}


class ClaudeProvider:
    def __init__(self, api_key: str, default_model: str, *, oauth_token: str | None = None) -> None:
        """Construct an Anthropic client.

        Two auth shapes:
          - api_key (default): sent as `x-api-key`. Covers the metered API key AND
            the gated, undocumented OAuth-as-API slot (allow_oauth_api_path).
          - oauth_token (sanctioned subscription-programmatic shape): a
            `claude setup-token` / CLAUDE_CODE_OAUTH_TOKEN credential, sent as
            `Authorization: Bearer` with the `oauth-2025-04-20` beta header, per
            the documented OAuth shape. This is the only first-class subscription
            slot below the metered key.
        """
        self._api_key = api_key
        self._oauth_token = oauth_token
        self._default_model = default_model
        self._client = self._build_client()

    def _resolve_effort(self, requested_model: str | None, resolved_model: str | None = None) -> str:
        requested = requested_model or resolved_model or self._default_model
        _claude_effort_config(requested)  # validates route-specific support
        return _semantic_effort(requested)

    def _build_client(self) -> AsyncAnthropic:
        if self._oauth_token:
            return AsyncAnthropic(
                auth_token=self._oauth_token,
                default_headers={"anthropic-beta": "oauth-2025-04-20"},
            )
        return AsyncAnthropic(api_key=self._api_key)

    def _refresh_client(self) -> bool:
        """Re-read OAuth token from disk and rebuild client. Returns True if refreshed.

        Only applies to the api_key (x-api-key) auth shape — the subscription
        OAuth access token in the credentials store rotates, so a 401 may just
        mean the on-disk token was refreshed. A first-class CLAUDE_CODE_OAUTH_TOKEN
        bearer is long-lived (one year) and not re-read here.
        """
        if self._oauth_token:
            return False
        new_key = _resolve_api_key()
        if new_key and new_key != self._api_key:
            logger.info("Refreshing API key after 401 [%s]", get_correlation_id())
            self._api_key = new_key
            self._client = self._build_client()
            return True
        return False

    async def aclose(self) -> None:
        """Close the persistent SDK transport on the event loop that used it."""
        await self._client.close()

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> str:
        from core.engine.orchestration.context import get_active_bus

        kwargs: dict = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            kwargs["system"] = system
        effort_config = _claude_effort_config(kwargs["model"])
        if effort_config:
            kwargs["output_config"] = effort_config

        # Adaptive thinking — Claude 4 native (standard messages.create, no beta header)
        resolved_model = kwargs["model"]
        mcfg = _get_model_config().get(resolved_model)
        if mcfg.get("thinking") == "adaptive" and mcfg.get("supports_thinking"):
            kwargs["thinking"] = {"type": "adaptive"}

        bus = get_active_bus()
        t0 = time.monotonic()
        if bus is not None:
            from core.engine.orchestration.events import ClaudeCallStart

            await bus.emit(ClaudeCallStart(run_id=bus.run_id, product_id=bus.product_id, model=resolved_model))

        response = None
        try:
            try:
                response = await self._client.messages.create(**kwargs)
            except AuthenticationError:
                if not self._refresh_client():
                    raise
                response = await self._client.messages.create(**kwargs)

            _record_usage(response, "complete")
            # Enrich the active gen_ai span (opened by _TracedLLM) with usage tokens.
            from core.engine.core.otel import set_gen_ai_usage

            _usage = getattr(response, "usage", None)
            set_gen_ai_usage(
                input_tokens=getattr(_usage, "input_tokens", 0) if _usage else 0,
                output_tokens=getattr(_usage, "output_tokens", 0) if _usage else 0,
                response_model=getattr(response, "model", None),
            )
            return _extract_text(response)
        finally:
            if bus is not None:
                from core.engine.orchestration.events import ClaudeCallDone

                usage = getattr(response, "usage", None)
                await bus.emit(
                    ClaudeCallDone(
                        run_id=bus.run_id,
                        product_id=bus.product_id,
                        tokens_in=getattr(usage, "input_tokens", 0) if usage else 0,
                        tokens_out=getattr(usage, "output_tokens", 0) if usage else 0,
                        cache_read=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
                        cache_write=getattr(usage, "cache_creation_input_tokens", 0) if usage else 0,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                )

    async def complete_json(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> dict:
        text = await self.complete(
            f"{prompt}\n\nReturn valid JSON only. No markdown, no explanation.",
            model=model,
            max_tokens=max_tokens,
            system=system,
        )
        text = text.strip()
        if text.startswith("```"):
            # Strip ```json ... ``` fences
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    async def complete_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> BaseModel:
        """Call LLM with native structured output. Returns validated Pydantic instance.

        Uses Anthropic's output_config with json_schema format for guaranteed
        schema conformance at the API level.
        """
        json_schema = schema.model_json_schema()
        _fix_additional_properties(json_schema)

        kwargs = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {
                "format": {"type": "json_schema", "schema": json_schema},
                **_claude_effort_config(model or self._default_model),
            },
        }
        try:
            response = await self._client.messages.create(**kwargs)
        except AuthenticationError:
            if not self._refresh_client():
                raise
            response = await self._client.messages.create(**kwargs)
        _record_usage(response, "complete_structured")
        text = _extract_text(response)
        return schema.model_validate_json(text)

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Yield text chunks as they arrive from the Anthropic streaming API."""
        kwargs = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        effort_config = _claude_effort_config(kwargs["model"])
        if effort_config:
            kwargs["output_config"] = effort_config
        try:
            async with self._client.messages.stream(**kwargs) as s:
                async for text in s.text_stream:
                    yield text
        except AuthenticationError:
            if not self._refresh_client():
                raise
            async with self._client.messages.stream(**kwargs) as s:
                async for text in s.text_stream:
                    yield text

    async def stream_messages(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream with system prompt and message history (for multi-turn chat)."""
        kwargs = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        effort_config = _claude_effort_config(kwargs["model"])
        if effort_config:
            kwargs["output_config"] = effort_config
        try:
            async with self._client.messages.stream(**kwargs) as s:
                async for text in s.text_stream:
                    yield text
        except AuthenticationError:
            if not self._refresh_client():
                raise
            async with self._client.messages.stream(**kwargs) as s:
                async for text in s.text_stream:
                    yield text


def _record_usage(response, method: str) -> None:
    """Record token usage to active accumulator if one exists."""
    acc = get_accumulator()
    if acc is None:
        return
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    acc.record(
        method=method,
        input_tokens=getattr(usage, "input_tokens", 0),
        output_tokens=getattr(usage, "output_tokens", 0),
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0),
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0),
    )


def _extract_text(response) -> str:
    """Extract text from response, filtering out thinking blocks.

    When extended thinking is enabled, response.content contains interleaved
    ThinkingBlock (type="thinking") and TextBlock (type="text") objects.
    We only want the text blocks.
    """
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


_model_config = None


def _get_model_config():
    global _model_config
    if _model_config is None:
        from core.engine.runtime.model_config import ModelConfig

        _model_config = ModelConfig()
    return _model_config


def _fix_additional_properties(schema: dict) -> None:
    """Recursively fix JSON schema for Anthropic structured output.

    - Sets additionalProperties: false on all object types (required).
    - Strips unsupported number constraints (minimum, maximum, etc.).
    - Removes title fields (unnecessary noise).
    """
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
    # Anthropic doesn't support min/max/exclusiveMin/exclusiveMax on numbers
    if schema.get("type") == "number" or schema.get("type") == "integer":
        for unsupported in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            schema.pop(unsupported, None)
    schema.pop("title", None)
    for key in ("properties", "$defs"):
        if key in schema:
            for v in schema[key].values():
                if isinstance(v, dict):
                    _fix_additional_properties(v)
    if "items" in schema and isinstance(schema["items"], dict):
        _fix_additional_properties(schema["items"])


async def _terminate_subprocess(proc: asyncio.subprocess.Process) -> None:
    """Force-reap a subprocess that has run past its timeout.

    SIGTERM first (lets the child flush + close pipes), brief grace, then SIGKILL.
    Always await proc.wait() so the kernel reaps the zombie before this coroutine
    returns — otherwise concurrent callers stack up uncollectable child procs.
    """
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
        return
    except asyncio.TimeoutError:
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        logger.warning("subprocess %s did not exit within 4s of SIGTERM+SIGKILL", proc.pid)


class CLIProvider:
    """LLM provider using `claude` CLI subprocess.

    No API key required — uses the installed Claude Code subscription.
    Automation is explicitly supported by Anthropic via `-p` / `--print` mode.

    All subprocess calls use --tools "" (pure LLM completion) and run from a neutral
    scratch directory (tempfile.gettempdir()) so the project's CLAUDE.md is outside
    the cwd ancestry chain and --setting-sources project,local resolves to nothing
    on disk — the invocation is hermetic from any installed hooks/MCP. --bare is
    NOT used — it requires ANTHROPIC_API_KEY and breaks OAuth/keychain auth.

    Token usage is tracked cumulatively in usage_stats for observability.
    Cache hit/miss data surfaces whether prompt caching is active across calls.
    """

    def __init__(self, default_model: str, claude_bin: str = "claude") -> None:
        self._default_model = default_model
        self._claude_bin = claude_bin
        # Cumulative token stats — updated on every call for observability
        self._stats: dict[str, int] = {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }

    def _model_arg(self, model: str | None) -> str:
        return model or self._default_model

    def _resolve_effort(self, requested_model: str | None, resolved_model: str | None = None) -> str:
        return _semantic_effort(requested_model or resolved_model or self._default_model)

    def _effort_args(self, model: str | None) -> list[str]:
        effort = self._resolve_effort(model, self._model_arg(model))
        return [] if effort == "default" else ["--effort", effort]

    @property
    def usage_stats(self) -> dict[str, int]:
        """Cumulative token usage across all calls. Useful for cost observability."""
        return dict(self._stats)

    def _track_usage(self, data: dict) -> dict:
        """Parse token usage from a CLI JSON response, accumulate stats, and
        return the per-call usage dict (for persistence).

        Modern Claude Code nests counts under a `usage` object
        (`usage.input_tokens`, `usage.cache_read_input_tokens`, …) and reports
        an API-rate-equivalent `total_cost_usd` at top level. Older/flat shapes
        put bare counts at the top level. Read nested first, fall back to flat —
        the prior flat-only read silently recorded zeros against the nested shape.
        """
        self._stats["calls"] += 1
        usage = data.get("usage") or {}
        input_t = usage.get("input_tokens") or data.get("total_input_tokens") or data.get("input_tokens") or 0
        output_t = usage.get("output_tokens") or data.get("total_output_tokens") or data.get("output_tokens") or 0
        cache_read = (
            usage.get("cache_read_input_tokens")
            or data.get("cache_read_input_tokens")
            or data.get("total_cache_read_input_tokens")
            or 0
        )
        cache_write = (
            usage.get("cache_creation_input_tokens")
            or data.get("cache_creation_input_tokens")
            or data.get("total_cache_creation_input_tokens")
            or 0
        )
        # The CLI's own API-rate-equivalent cost for this call, when present.
        cost_usd = data.get("total_cost_usd")
        self._stats["input_tokens"] += input_t
        self._stats["output_tokens"] += output_t
        self._stats["cache_read_tokens"] += cache_read
        self._stats["cache_write_tokens"] += cache_write
        if input_t or output_t:
            logger.debug(
                "CLIProvider usage — in: %d, out: %d, cache_read: %d, cache_write: %d",
                input_t,
                output_t,
                cache_read,
                cache_write,
            )
        return {
            "input_tokens": input_t,
            "output_tokens": output_t,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "cost_usd": cost_usd,
        }

    async def _persist_usage(self, usage: dict, model: str | None) -> None:
        """Fail-open: persist one token_ledger_entry per completed CLI call so the
        subscription-credit draw — the spend the June 15 2026 Agent SDK credit
        debits — becomes observable. NEVER raises; a DB failure must not break
        the LLM call (same discipline as composition-signal emission).

        cost_usd semantics: on a subscription plan no dollars are billed per call.
        The `claude` CLI reports `total_cost_usd` — the API-rate-equivalent cost
        Claude Code itself computes — which is the best estimate of the draw
        against the monthly Agent SDK credit. Recorded with
        billing="subscription_credit_estimate"; falls back to
        model_costs.cost_for_call (input+output only, cache-blind) when the CLI
        omits the figure.

        Follow-up: machine-triggered (sentinel/foresight) vs human-triggered
        (interactive chat) is not cheaply available at this layer — product
        attribution is taken from the active bus when present; the trigger-source
        split is left for a caller-context thread.
        """
        try:
            from core.engine.intelligence.token_ledger import TokenLedger
            from core.engine.orchestration.context import get_active_bus

            model_name = self._model_arg(model)
            cost = usage.get("cost_usd")
            if cost is None:
                from core.engine.core.model_costs import cost_for_call

                cost = cost_for_call(model_name, usage.get("input_tokens", 0), usage.get("output_tokens", 0))

            tokens_by_stage = {
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "cache_read": usage.get("cache_read_tokens", 0),
                "cache_creation": usage.get("cache_write_tokens", 0),
            }
            total_in = tokens_by_stage["input"] + tokens_by_stage["cache_read"] + tokens_by_stage["cache_creation"]
            cache_hit_rate = (tokens_by_stage["cache_read"] / total_in) if total_in > 0 else 0.0

            bus = get_active_bus()
            product_id = getattr(bus, "product_id", None) or "product:platform"

            await TokenLedger().record(
                task_id="cli_provider",
                discipline="",
                task_type="cli_completion",
                tier="",
                executor_model=model_name,
                reviewer_model=None,
                passes=1,
                escalated=False,
                cost_usd=cost or 0.0,
                tokens_by_stage=tokens_by_stage,
                cache_hit_rate=cache_hit_rate,
                failure_categories=[],
                product_id=product_id,
                source="cli_provider",
                billing="subscription_credit_estimate",
            )
        except Exception:
            logger.debug("CLIProvider._persist_usage failed (non-fatal)", exc_info=True)

    # Stable, minimal system prompt — kept short so it fits comfortably in the
    # cached prefix across all CLIProvider calls (same string = same cache key).
    _SYSTEM_PROMPT = (
        "You are a concise, expert assistant. Respond directly with the requested output. "
        "Do NOT invoke any skills, tools, slash commands, or function calls. "
        "Do NOT check for applicable skills. Output only what is explicitly requested."
    )

    # Base flags shared across all subprocess calls.
    # --no-session-persistence: stateless calls, no disk writes
    # --tools "": pure LLM completion, no file/bash access
    # --setting-sources project,local: skip user-tier ~/.claude/settings.json so
    #   the global hook/MCP set (which may belong to unrelated projects) doesn't
    #   fire on every ACE LLM call. Combined with _NEUTRAL_CWD below, no settings
    #   file resolves to "project" tier either — ACE invocations are hermetic.
    # NOTE: --bare is intentionally absent — it disables OAuth/keychain auth and
    # requires ANTHROPIC_API_KEY. Subscription auth still works under
    # --setting-sources because credential loading is independent of settings tiers.
    _BASE_FLAGS: list[str] = [
        "--no-session-persistence",
        "--tools",
        "",
        "--setting-sources",
        "project,local",
    ]

    # Neutral cwd: outside the ACE project tree (so CLAUDE.md is not auto-loaded)
    # AND not $HOME (so ~/.claude/settings.json is not loaded as the "project" tier
    # when --setting-sources excludes "user"). tempfile.gettempdir() satisfies both.
    _NEUTRAL_CWD: str = tempfile.gettempdir()

    async def _run(self, args: list[str], timeout: float | None = None) -> str:
        """Run claude subprocess and return stdout. Raises on non-zero exit or timeout."""
        effective_timeout = settings.claude_cli_timeout_seconds if timeout is None else timeout
        env = {**os.environ, "HOME": os.path.expanduser("~")}
        proc = await asyncio.create_subprocess_exec(
            self._claude_bin,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self._NEUTRAL_CWD,  # outside project tree (no CLAUDE.md), not $HOME (no settings hooks)
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
        except asyncio.TimeoutError:
            await _terminate_subprocess(proc)
            from core.engine.core.exceptions import LLMError

            raise LLMError(f"claude subprocess timed out after {effective_timeout}s")
        except asyncio.CancelledError:
            await _terminate_subprocess(proc)
            raise
        if proc.returncode != 0:
            from core.engine.core.exceptions import LLMError

            raise LLMError(f"claude subprocess failed (exit {proc.returncode}): {stderr.decode()[:300]}")
        return stdout.decode()

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> str:
        from core.engine.orchestration.context import get_active_bus

        # Use caller's system prompt if provided, otherwise default.
        # list[dict] (cache-structured blocks) are flattened to plain text for CLI transport.
        if isinstance(system, str):
            sys_prompt = system
        elif isinstance(system, list):
            sys_prompt = " ".join(b.get("text", "") for b in system if isinstance(b, dict))
        else:
            sys_prompt = self._SYSTEM_PROMPT
        args = [
            "-p",
            prompt,
            "--model",
            self._model_arg(model),
            *self._effort_args(model),
            "--output-format",
            "json",
            "--system-prompt",
            sys_prompt,
            *self._BASE_FLAGS,
        ]

        bus = get_active_bus()
        t0 = time.monotonic()
        tokens_in_before = self._stats.get("input_tokens", 0)
        tokens_out_before = self._stats.get("output_tokens", 0)
        if bus is not None:
            from core.engine.orchestration.events import ClaudeCallStart

            await bus.emit(ClaudeCallStart(run_id=bus.run_id, product_id=bus.product_id, model=self._model_arg(model)))

        try:
            for attempt in range(3):
                out = await self._run(args)
                stripped = out.strip()
                try:
                    lines = stripped.splitlines()
                    if lines:
                        data = json.loads(lines[0])
                        usage = self._track_usage(data)
                        # Enrich the active gen_ai span (opened by _TracedLLM) with usage.
                        from core.engine.core.otel import set_gen_ai_usage

                        set_gen_ai_usage(
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                            response_model=data.get("model"),
                        )
                        result = data.get("result", stripped)
                        if result != "":
                            await self._persist_usage(usage, model)
                            return result
                    elif stripped:
                        return stripped  # non-JSON non-empty output
                except json.JSONDecodeError:
                    if stripped:
                        return stripped  # non-JSON but non-empty output — return as-is
                # Empty or unparseable-empty result; retry with backoff
                logger.warning("CLIProvider got empty result (attempt %d/3)", attempt + 1)
                await asyncio.sleep(2**attempt)
            return ""
        finally:
            if bus is not None:
                from core.engine.orchestration.events import ClaudeCallDone

                await bus.emit(
                    ClaudeCallDone(
                        run_id=bus.run_id,
                        product_id=bus.product_id,
                        tokens_in=self._stats.get("input_tokens", 0) - tokens_in_before,
                        tokens_out=self._stats.get("output_tokens", 0) - tokens_out_before,
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                )

    async def complete_json(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> dict:
        full_prompt = f"{prompt}\n\nReturn valid JSON only. No markdown, no explanation."
        for attempt in range(3):
            result = await self.complete(full_prompt, model=model, system=system)
            text = result.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                if attempt < 2:
                    logger.warning(
                        "complete_json non-JSON response (attempt %d/3): %r",
                        attempt + 1,
                        text[:120],
                    )
                    await asyncio.sleep(2**attempt)
        raise json.JSONDecodeError("Failed after 3 attempts", "", 0)

    async def complete_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> BaseModel:
        _fix_additional_properties(schema.model_json_schema())
        # --json-schema with --output-format json produces empty result field in CLI;
        # inject schema as prompt instruction instead and strip fences from output.
        schema_str = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        structured_prompt = f"{prompt}\n\nReturn valid JSON only. No markdown, no explanation. Schema: {schema_str}"
        out = await self._run(
            [
                "-p",
                structured_prompt,
                "--model",
                self._model_arg(model),
                *self._effort_args(model),
                "--output-format",
                "json",
                "--system-prompt",
                self._SYSTEM_PROMPT,
                *self._BASE_FLAGS,
            ]
        )
        usage: dict | None = None
        try:
            data = json.loads(out.splitlines()[0])
            usage = self._track_usage(data)
            result_text = data.get("result", out)
        except json.JSONDecodeError:
            result_text = out.strip()
        # Persist OUTSIDE the parse path: the tokens were spent regardless of
        # whether the result survives fence-stripping or the schema validation
        # below — a parse/validation failure must not lose the ledger row.
        # (When the envelope itself isn't JSON, the CLI gave us no usage to
        # record — there is nothing to persist.)
        if usage is not None:
            await self._persist_usage(usage, model)
        # Strip markdown code fences that the CLI model sometimes wraps output in
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = re.sub(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", r"\1", result_text, flags=re.DOTALL).strip()
        return schema.model_validate_json(result_text)

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        env = {**os.environ, "HOME": os.path.expanduser("~")}
        proc = await asyncio.create_subprocess_exec(
            self._claude_bin,
            "-p",
            prompt,
            "--model",
            self._model_arg(model),
            *self._effort_args(model),
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            "--system-prompt",
            self._SYSTEM_PROMPT,
            *self._BASE_FLAGS,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self._NEUTRAL_CWD,
        )
        async for raw in proc.stdout:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Partial assistant content blocks
            if event.get("type") == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        yield block["text"]
        await proc.wait()

    async def stream_messages(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        # Build a prompt from message history; system prompt injected via flag
        parts = []
        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            parts.append(f"{role}: {content}")
        prompt = "\n\n".join(parts)

        env = {**os.environ, "HOME": os.path.expanduser("~")}
        proc = await asyncio.create_subprocess_exec(
            self._claude_bin,
            "-p",
            prompt,
            "--model",
            self._model_arg(model),
            *self._effort_args(model),
            "--system-prompt",
            system,
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            *self._BASE_FLAGS,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self._NEUTRAL_CWD,
        )
        async for raw in proc.stdout:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        yield block["text"]
        await proc.wait()


# Module-level so the once-per-name warning promise survives throwaway provider
# instances: get_llm() constructs a FRESH provider at ~75 call sites, so an
# instance-held seen-set would re-warn on effectively every LLM call in a
# degraded config. Keyed (provider class name, requested model name).
_TIER_FALLBACK_WARNED: set[tuple[str, str]] = set()


class ModelMapMixin:
    """Per-provider translation of ACE's Anthropic tier vocabulary (Task 3).

    ACE call sites route cost-aware by passing Anthropic model names verbatim
    (settings.llm_budget_model / llm_model / llm_reasoning_model). Renaming
    that caller vocabulary is deliberately out of scope — providers whose
    backends speak a different catalog translate at request time instead:

      1. mapped name        → the provider-native model from `model_map`
      2. unmapped `claude*` → the provider's default model, with a ONE-TIME
                              warning per name (unknown-model grace — tier
                              routing degrades visibly, never crashes)
      3. anything else      → passed through verbatim (a native model name is
                              deliberate caller intent; trust it)

    `model_map` merges OVER the provider's built-in defaults, so a settings
    override can re-point one tier without re-declaring the rest.
    """

    _default_model: str
    # Which settings knob fixes a degraded fallback — named in the warning.
    _map_setting_name: str = "the provider's model_map"

    def _init_model_map(self, model_map: dict[str, str] | None, defaults: dict[str, str] | None = None) -> None:
        self._model_map: dict[str, str] = {**(defaults or {}), **(model_map or {})}

    def _resolve_model(self, requested: str | None) -> str:
        if not requested:
            return self._default_model
        mapped = self._model_map.get(requested)
        if mapped is not None:
            return mapped
        if requested.startswith("claude"):
            warn_key = (type(self).__name__, requested)
            if warn_key not in _TIER_FALLBACK_WARNED:
                _TIER_FALLBACK_WARNED.add(warn_key)
                logger.warning(
                    "No model-map entry for %r on %s — falling back to default model %r. "
                    "Tier routing is degraded; set %s to translate Anthropic tier names.",
                    requested,
                    type(self).__name__,
                    self._default_model,
                    self._map_setting_name,
                )
            return self._default_model
        return requested


async def _persist_usage_row(
    *,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    task_id: str,
    task_type: str,
    source: str,
    billing: str,
    cost_usd: float | None = None,
) -> None:
    """Shared fail-open per-call ledger writer (Task-4c pattern) for providers
    that live OUTSIDE this module (the optional router adapters in
    llm_litellm.py / llm_anyllm.py). NEVER raises — a DB failure must not
    break the LLM call, same discipline as composition-signal emission.

    cost_usd: pass the backend's own figure when it reports one (litellm's
    `response_cost` hidden param); None falls back to
    model_costs.cost_for_call, whose unknown-model grace records 0.0 with a
    debug log — most router wire names aren't in ACE's bounded rates
    table, and that's fine.
    """
    if not (input_tokens or output_tokens):
        return
    try:
        from core.engine.core.model_costs import cost_for_call
        from core.engine.intelligence.token_ledger import TokenLedger
        from core.engine.orchestration.context import get_active_bus

        if cost_usd is None:
            cost_usd = cost_for_call(model_name, input_tokens, output_tokens)
            if cost_usd == 0.0:
                logger.debug(
                    "No cost rates for model %r — recording cost_usd=0.0 (unknown-model grace)",
                    model_name,
                )

        bus = get_active_bus()
        product_id = getattr(bus, "product_id", None) or "product:platform"

        await TokenLedger().record(
            task_id=task_id,
            discipline="",
            task_type=task_type,
            tier="",
            executor_model=model_name,
            reviewer_model=None,
            passes=1,
            escalated=False,
            cost_usd=cost_usd,
            tokens_by_stage={
                "input": input_tokens,
                "output": output_tokens,
                "cache_read": 0,
                "cache_creation": 0,
            },
            cache_hit_rate=0.0,
            failure_categories=[],
            product_id=product_id,
            source=source,
            billing=billing,
        )
    except Exception:
        logger.debug("_persist_usage_row failed (non-fatal, source=%s)", source, exc_info=True)


_CODEX_TIER_MAP_DEFAULTS: dict[str, str] = {
    "claude-haiku-4-5-20251001": "gpt-5.6-luna",
    "claude-sonnet-5": "gpt-5.6-terra",
    "claude-opus-4-8": "gpt-5.6-sol",
    "claude-fable-5": "gpt-5.6-sol",
    # Compatibility for persisted work and extensions using the prior catalog.
    "claude-sonnet-4-6": "gpt-5.6-terra",
    "claude-opus-4-6": "gpt-5.6-sol",
}

_CODEX_EFFORT_MAP_DEFAULTS: dict[str, str] = {
    "claude-haiku-4-5-20251001": "default",
    "claude-sonnet-5": "default",
    "claude-opus-4-8": "high",
    "claude-fable-5": "xhigh",
    "claude-sonnet-4-6": "default",
    "claude-opus-4-6": "high",
    "gpt-5.6-luna": "default",
    "gpt-5.6-terra": "default",
    "gpt-5.6-sol": "high",
}
_CODEX_EFFORTS = frozenset({"default", "none", "low", "medium", "high", "xhigh", "max"})


class CodexCLIProvider(ModelMapMixin):
    """OpenAI subscription route through the documented Codex CLI.

    The CLI owns ChatGPT authentication and token refresh. ACE invokes
    ``codex exec`` but never reads, copies, or forwards ``~/.codex/auth.json``.
    Calls are ephemeral, use a neutral working directory, disable Codex tools,
    rules, hooks, apps, memories, and web search, and run inside a read-only
    sandbox. This makes the route a stateless model transport rather than a
    nested coding agent. Model and reasoning effort resolve independently, so
    two semantic roles may share Sol without receiving the same inference budget.

    ChatGPT sign-in is subscription-backed. OpenAI Platform API-key access
    remains a separate, explicitly metered ``OpenAICompatProvider`` route.
    """

    _map_setting_name = "CODEX_CLI_MODEL_MAP"
    _NEUTRAL_CWD = tempfile.gettempdir()
    _BASE_FLAGS: tuple[str, ...] = (
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--disable",
        "shell_tool",
        "--disable",
        "apps",
        "--disable",
        "hooks",
        "--disable",
        "goals",
        "--disable",
        "multi_agent",
        "--disable",
        "memories",
        "-c",
        'web_search="disabled"',
        "--json",
    )
    _SYSTEM_PROMPT = (
        "Act only as a stateless language-model completion transport. Do not use tools, "
        "inspect files, browse, execute commands, delegate, or modify state. Return only "
        "the requested answer."
    )

    def __init__(
        self,
        default_model: str = "gpt-5.6-terra",
        codex_bin: str = "codex",
        model_map: dict[str, str] | None = None,
        default_effort: str = "default",
        effort_map: dict[str, str] | None = None,
    ) -> None:
        self._default_model = default_model
        self._codex_bin = codex_bin
        self._init_model_map(model_map, _CODEX_TIER_MAP_DEFAULTS)
        merged_efforts = {**_CODEX_EFFORT_MAP_DEFAULTS, **(effort_map or {})}
        invalid = sorted(set(merged_efforts.values()) - _CODEX_EFFORTS)
        if default_effort not in _CODEX_EFFORTS or invalid:
            raise ValueError(f"invalid Codex reasoning effort: {invalid or [default_effort]}")
        self._default_effort = default_effort
        self._effort_map = merged_efforts
        self._stats = {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "reasoning_output_tokens": 0,
        }

    @property
    def usage_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def _model_arg(self, model: str | None) -> str:
        return self._resolve_model(model)

    def _resolve_effort(self, requested_model: str | None, resolved_model: str | None = None) -> str:
        """Resolve effort by semantic request before falling back to native model."""
        if requested_model in self._effort_map:
            return self._effort_map[requested_model]
        if resolved_model in self._effort_map:
            return self._effort_map[resolved_model]
        return self._default_effort

    @staticmethod
    def _flatten_system(system: str | list[dict] | None) -> str:
        if isinstance(system, str):
            return system
        if isinstance(system, list):
            return " ".join(block.get("text", "") for block in system if isinstance(block, dict))
        return CodexCLIProvider._SYSTEM_PROMPT

    def _prompt(self, prompt: str, system: str | list[dict] | None) -> str:
        supplied = self._flatten_system(system)
        return (
            f"<transport_constraints>\n{self._SYSTEM_PROMPT}\n</transport_constraints>\n\n"
            f"<system_instructions>\n{supplied}\n</system_instructions>\n\n{prompt}"
        )

    @staticmethod
    def _subprocess_env() -> dict[str, str]:
        """Pass process basics plus Codex's documented state location only."""
        allowed = (
            "HOME",
            "PATH",
            "TMPDIR",
            "TEMP",
            "TMP",
            "LANG",
            "LC_ALL",
            "TERM",
            "USER",
            "LOGNAME",
            "SHELL",
            "CODEX_HOME",
        )
        return {name: os.environ[name] for name in allowed if os.environ.get(name)}

    def _track_usage(self, usage: dict) -> dict[str, int]:
        normalized = {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
            "reasoning_output_tokens": int(usage.get("reasoning_output_tokens") or 0),
        }
        self._stats["calls"] += 1
        for key, value in normalized.items():
            self._stats[key] += value
        return normalized

    async def _run(
        self,
        prompt: str,
        model: str,
        effort: str = "default",
        timeout: float = 300.0,
    ) -> tuple[str, dict[str, int]]:
        """Run one hermetic Codex completion and parse its JSONL event stream."""
        effort_args = () if effort == "default" else ("-c", f'model_reasoning_effort="{effort}"')
        proc = await asyncio.create_subprocess_exec(
            self._codex_bin,
            *self._BASE_FLAGS,
            *effort_args,
            "--model",
            model,
            "-C",
            self._NEUTRAL_CWD,
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._subprocess_env(),
            cwd=self._NEUTRAL_CWD,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=timeout)
        except asyncio.TimeoutError:
            await _terminate_subprocess(proc)
            from core.engine.core.exceptions import LLMError

            raise LLMError(f"codex subprocess timed out after {timeout}s")
        except asyncio.CancelledError:
            await _terminate_subprocess(proc)
            raise
        if proc.returncode != 0:
            from core.engine.core.exceptions import LLMError

            detail = stderr.decode(errors="replace").strip().replace("\n", " ")[:300]
            raise LLMError(f"codex subprocess failed (exit {proc.returncode}): {detail}")

        messages: list[str] = []
        usage: dict = {}
        for raw_line in stdout.decode(errors="replace").splitlines():
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                    messages.append(item["text"])
            elif event.get("type") == "turn.completed":
                usage = event.get("usage") or {}
            elif event.get("type") in {"turn.failed", "error"}:
                from core.engine.core.exceptions import LLMError

                raise LLMError("codex completion failed")
        if not messages:
            from core.engine.core.exceptions import LLMError

            raise LLMError("codex completion returned no agent message")
        return messages[-1], self._track_usage(usage)

    async def _persist_usage(self, usage: dict[str, int], model: str) -> None:
        await _persist_usage_row(
            model_name=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            task_id="codex_cli_provider",
            task_type="cli_completion",
            source="codex_cli",
            billing="chatgpt_subscription",
            cost_usd=0.0,
        )

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> str:
        del max_tokens  # codex exec exposes no output-token cap
        resolved_model = self._model_arg(model)
        effort = self._resolve_effort(model, resolved_model)
        text, usage = await self._run(self._prompt(prompt, system), resolved_model, effort)
        from core.engine.core.otel import set_gen_ai_usage

        set_gen_ai_usage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            response_model=resolved_model,
        )
        await self._persist_usage(usage, resolved_model)
        return text

    async def complete_json(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> dict:
        full_prompt = f"{prompt}\n\nReturn valid JSON only. No markdown, no explanation."
        for attempt in range(3):
            text = (await self.complete(full_prompt, model=model, max_tokens=max_tokens, system=system)).strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", r"\1", text, flags=re.DOTALL).strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
        raise json.JSONDecodeError("Failed after 3 attempts", "", 0)

    async def complete_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> BaseModel:
        json_schema = schema.model_json_schema()
        _fix_additional_properties(json_schema)
        full_prompt = (
            f"{prompt}\n\nReturn JSON matching this schema exactly:\n"
            f"{json.dumps(json_schema, separators=(',', ':'))}\nReturn JSON only."
        )
        data = await self.complete_json(full_prompt, model=model, max_tokens=max_tokens)
        return schema.model_validate(data)

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        text = await self.complete(prompt, model=model, max_tokens=max_tokens)
        if text:
            yield text

    async def stream_messages(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        parts: list[str] = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, list):
                content = " ".join(block.get("text", "") for block in content if isinstance(block, dict))
            parts.append(f"{message.get('role', 'user').upper()}: {content}")
        text = await self.complete("\n\n".join(parts), model=model, max_tokens=max_tokens, system=system)
        if text:
            yield text


class OllamaProvider(ModelMapMixin):
    """LLM provider using Ollama HTTP API for local inference.

    Targets the Ollama REST API (https://ollama.ai/docs/api):
    - POST /api/generate for completion
    - stream=False for synchronous responses

    No API key required — runs against a local Ollama instance.
    Activated when settings.ollama_host is set.

    Tier mapping: no built-in catalog — a local box serves whatever models the
    operator pulled, so unmapped Anthropic tier names collapse to
    `default_model` (one-time warning). Tiered local routing = OLLAMA_MODEL_MAP.
    """

    _map_setting_name = "OLLAMA_MODEL_MAP"

    def __init__(self, host: str, default_model: str = "llama3.2", model_map: dict[str, str] | None = None) -> None:
        self._host = host.rstrip("/")
        self._default_model = default_model
        self._init_model_map(model_map)

    def _model(self, model: str | None) -> str:
        return self._resolve_model(model)

    async def _post(self, endpoint: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self._host}{endpoint}", json=payload)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _record_local_usage(data: dict, method: str, model: str) -> None:
        """Record Ollama's exact local token counts with zero provider cost."""
        accumulator = get_accumulator()
        if accumulator is not None:
            accumulator.record(
                method,
                int(data.get("prompt_eval_count") or 0),
                int(data.get("eval_count") or 0),
                purpose="ollama_local",
                provider="OllamaProvider",
                model=str(data.get("model") or model),
                cost_usd=0.0,
            )

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> str:
        resolved_model = self._model(model)
        payload: dict = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if isinstance(system, str):
            payload["system"] = system
        elif isinstance(system, list):
            # Flatten content blocks for Ollama (no cache_control support)
            payload["system"] = " ".join(b.get("text", "") for b in system)
        data = await self._post("/api/generate", payload)
        self._record_local_usage(data, "complete", resolved_model)
        return data.get("response", "")

    async def complete_json(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> dict:
        resolved_model = self._model(model)
        payload: dict = {
            "model": resolved_model,
            "prompt": f"{prompt}\n\nReturn valid JSON only. No markdown, no explanation.",
            "stream": False,
            "format": "json",
            "options": {"num_predict": max_tokens},
        }
        if isinstance(system, str):
            payload["system"] = system
        elif isinstance(system, list):
            payload["system"] = " ".join(b.get("text", "") for b in system)
        data = await self._post("/api/generate", payload)
        self._record_local_usage(data, "complete_json", resolved_model)
        text = data.get("response", "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    async def complete_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> BaseModel:
        schema_str = json.dumps(schema.model_json_schema())
        full_prompt = (
            f"{prompt}\n\n"
            f"Return JSON that strictly matches this schema:\n{schema_str}\n\n"
            f"Return JSON only. No markdown."
        )
        resolved_model = self._model(model)
        data = await self._post(
            "/api/generate",
            {
                "model": resolved_model,
                "prompt": full_prompt,
                "stream": False,
                "format": "json",
                "options": {"num_predict": max_tokens},
            },
        )
        self._record_local_usage(data, "complete_structured", resolved_model)
        text = data.get("response", "").strip()
        return schema.model_validate_json(text)

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self._host}/api/generate",
                json={
                    "model": self._model(model),
                    "prompt": prompt,
                    "stream": True,
                    "options": {"num_predict": max_tokens},
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        chunk = event.get("response", "")
                        if chunk:
                            yield chunk
                    except json.JSONDecodeError:
                        continue

    async def stream_messages(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        parts = [f"SYSTEM: {system}"]
        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            parts.append(f"{role}: {content}")
        prompt = "\n\n".join(parts)
        async for chunk in self.stream(prompt, model=model, max_tokens=max_tokens):
            yield chunk


# Built-in tier translations applied ONLY when the backend is api.openai.com —
# the one OpenAI-format backend whose catalog is known. Other compat backends
# (Groq, Together, OpenRouter, vLLM, LM Studio, Ollama-compat) serve catalogs
# this code can't guess, so they start with an EMPTY map and Anthropic tier
# names fall back to default_model (one-time warning) until
# OPENAI_COMPAT_MODEL_MAP says otherwise. The current known catalog maps four
# ACE/Claude roles onto GPT's three native levels; Opus and Fable share Sol.
_OPENAI_TIER_MAP_DEFAULTS: dict[str, str] = {
    "claude-haiku-4-5-20251001": "gpt-5.6-luna",
    "claude-sonnet-5": "gpt-5.6-terra",
    "claude-opus-4-8": "gpt-5.6-sol",
    "claude-fable-5": "gpt-5.6-sol",
    "claude-sonnet-4-6": "gpt-5.6-terra",
    "claude-opus-4-6": "gpt-5.6-sol",
}
_OPENAI_GPT56_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh", "max"})


class OpenAICompatProvider(ModelMapMixin):
    """Zero-dependency adapter for the OpenAI chat-completions wire format.

    One provider covers the whole OpenAI-format ecosystem: OpenAI, Azure,
    Groq, Together, OpenRouter, vLLM, LM Studio, and Ollama's compat endpoint
    — anything serving `POST {base_url}/chat/completions` with bearer auth,
    a `messages` array, and SSE streaming (`data:` lines, `[DONE]` terminator).
    Built on httpx (existing dep) — no openai SDK, the default install stays lean.

    Cache-control system blocks are flattened to plain text (the format has no
    cache_control concept — same discipline as OllamaProvider). `api_key` is
    optional: local servers (vLLM, LM Studio) often run keyless.

    Tier mapping: callers pass Anthropic model names; `model_map` translates
    them per request (see ModelMapMixin). Built-in tiered defaults apply only
    against api.openai.com (_OPENAI_TIER_MAP_DEFAULTS); everywhere else the
    map starts empty and OPENAI_COMPAT_MODEL_MAP configures it.

    response_format fallback: complete_json() asks for
    `{"type": "json_object"}` and complete_structured() for a `json_schema`
    response_format — but many compat servers reject the parameter with a 400.
    On a 400 whose error body names response_format, the provider retries ONCE
    without the parameter and relies on the prompt-based JSON/schema
    instruction (which is always sent), then fence-strips and parses. All
    other errors — including 400s about anything else — propagate untouched.

    Per-call usage (`usage.prompt_tokens` / `usage.completion_tokens`) is
    persisted fail-open to the token ledger with source="openai_compat" —
    Task-4c parity. Streaming responses carry no usage by default
    (`stream_options.include_usage` is not requested — deliberately out of
    scope for this arc).

    NOTE: chat-completions is this provider's wire shape, not an assumption
    baked into the Protocol — the vendor-neutral Responses API gets its own
    OpenResponsesProvider when the ecosystem lands there (watch item).
    """

    _map_setting_name = "OPENAI_COMPAT_MODEL_MAP"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        default_model: str = "gpt-5.6-terra",
        model_map: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        # Exact-hostname gate, not a substring match: "api.openai.com" as a
        # substring would also match api.openai.com.evil.tld or a path that
        # merely contains the string.
        defaults = _OPENAI_TIER_MAP_DEFAULTS if urlparse(self._base_url).hostname == "api.openai.com" else None
        self._init_model_map(model_map, defaults)

    def _model(self, model: str | None) -> str:
        return self._resolve_model(model)

    def _resolve_effort(self, requested_model: str | None, resolved_model: str | None = None) -> str:
        """Resolve effort only where ACE knows the upstream capability.

        Arbitrary OpenAI-compatible endpoints deliberately report
        ``provider_default`` and receive no reasoning parameter.  For the exact
        OpenAI host, GPT-5.6 supports the provider-neutral ACE effort policy.
        """
        resolved = resolved_model or self._model(requested_model)
        if urlparse(self._base_url).hostname != "api.openai.com" or not resolved.startswith("gpt-5.6"):
            return "provider_default"
        effort = _semantic_effort(requested_model or resolved)
        if effort == "default":
            return "provider_default"
        if effort not in _OPENAI_GPT56_EFFORTS:
            raise ValueError(f"unsupported GPT-5.6 reasoning effort: {effort}")
        return effort

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def _flatten_system(system: str | list[dict] | None) -> str | None:
        if isinstance(system, str):
            return system
        if isinstance(system, list):
            # Flatten content blocks — no cache_control support downstream.
            return " ".join(b.get("text", "") for b in system if isinstance(b, dict))
        return None

    def _payload(
        self,
        prompt: str,
        model: str | None,
        max_tokens: int,
        system: str | list[dict] | None,
    ) -> dict:
        messages: list[dict] = []
        sys_text = self._flatten_system(system)
        if sys_text is not None:
            messages.append({"role": "system", "content": sys_text})
        messages.append({"role": "user", "content": prompt})
        resolved_model = self._model(model)
        token_limit_key = "max_completion_tokens" if resolved_model.startswith("gpt-5") else "max_tokens"
        payload = {
            "model": resolved_model,
            token_limit_key: max_tokens,
            "messages": messages,
            "stream": False,
        }
        effort = self._resolve_effort(model, resolved_model)
        if effort != "provider_default":
            payload["reasoning_effort"] = effort
        return payload

    @staticmethod
    def _extract_content(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        # `content` may be null (refusals / tool-only turns) — yield "".
        return (choices[0].get("message") or {}).get("content") or ""

    async def _post_chat(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        await self._persist_usage(data.get("usage") or {}, payload.get("model"))
        return data

    @staticmethod
    def _is_response_format_rejection(exc: Exception, payload: dict) -> bool:
        """True only when a 400 actually complains about `response_format`.

        A 400 about max_tokens, a bad model name, or malformed messages must
        propagate untouched — retrying it without response_format would
        misattribute the error and burn a round-trip. The check reads the
        error body, where OpenAI-format servers name the offending parameter.
        """
        if "response_format" not in payload:
            return False
        if getattr(getattr(exc, "response", None), "status_code", None) != 400:
            return False
        try:
            body = exc.response.text or ""
        except Exception:
            body = ""
        return "response_format" in body

    async def _post_with_format_fallback(self, payload: dict) -> str:
        """POST a payload carrying `response_format`; when the backend rejects
        THAT parameter with a 400 (many compat servers do), retry ONCE without
        it — the prompt already carries the JSON/schema instruction, so the
        fallback round-trip can still produce conforming output. Every other
        error — including 400s about anything else — propagates."""
        try:
            data = await self._post_chat(payload)
        except httpx.HTTPStatusError as exc:
            if not self._is_response_format_rejection(exc, payload):
                raise
            logger.info(
                "Backend rejected response_format (400) — retrying with prompt-based JSON [%s]",
                get_correlation_id(),
            )
            data = await self._post_chat({k: v for k, v in payload.items() if k != "response_format"})
        return self._extract_content(data)

    async def _persist_usage(self, usage: dict, model: str | None) -> None:
        """Fail-open: persist one token_ledger_entry per completed call (Task-4c
        parity with CLIProvider). NEVER raises — a DB failure must not break
        the LLM call.

        cost_usd comes from model_costs.cost_for_call; unknown wire models
        record 0.0 with a debug log — unknown-model grace, not a crash.
        """
        if not usage:
            return
        try:
            from core.engine.core.model_costs import cost_for_call
            from core.engine.intelligence.token_ledger import TokenLedger
            from core.engine.orchestration.context import get_active_bus

            # `model` arrives as the payload's model — already wire-resolved.
            # Record it verbatim: re-resolving would re-map a chained entry
            # whose value is also a key (idempotent only for today's maps).
            model_name = model or self._default_model
            input_t = usage.get("prompt_tokens", 0)
            output_t = usage.get("completion_tokens", 0)
            cost = cost_for_call(model_name, input_t, output_t)
            if cost == 0.0 and (input_t or output_t):
                logger.debug(
                    "No cost rates for model %r — recording cost_usd=0.0 (unknown-model grace)",
                    model_name,
                )

            bus = get_active_bus()
            product_id = getattr(bus, "product_id", None) or "product:platform"

            await TokenLedger().record(
                task_id="openai_compat_provider",
                discipline="",
                task_type="chat_completion",
                tier="",
                executor_model=model_name,
                reviewer_model=None,
                passes=1,
                escalated=False,
                cost_usd=cost,
                tokens_by_stage={
                    "input": input_t,
                    "output": output_t,
                    "cache_read": 0,
                    "cache_creation": 0,
                },
                cache_hit_rate=0.0,
                failure_categories=[],
                product_id=product_id,
                source="openai_compat",
                billing="metered_estimate",
            )
        except Exception:
            logger.debug("OpenAICompatProvider._persist_usage failed (non-fatal)", exc_info=True)

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> str:
        data = await self._post_chat(self._payload(prompt, model, max_tokens, system))
        return self._extract_content(data)

    async def complete_json(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> dict:
        payload = self._payload(
            f"{prompt}\n\nReturn valid JSON only. No markdown, no explanation.",
            model,
            max_tokens,
            system,
        )
        payload["response_format"] = {"type": "json_object"}
        text = (await self._post_with_format_fallback(payload)).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    async def complete_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> BaseModel:
        json_schema = schema.model_json_schema()
        _fix_additional_properties(json_schema)
        schema_str = json.dumps(json_schema, separators=(",", ":"))
        # The schema rides in the prompt as well, so the response_format
        # fallback round-trip can still produce conforming output.
        full_prompt = (
            f"{prompt}\n\n"
            f"Return JSON that strictly matches this schema:\n{schema_str}\n\n"
            f"Return JSON only. No markdown."
        )
        payload = self._payload(full_prompt, model, max_tokens, None)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": json_schema, "strict": True},
        }
        text = (await self._post_with_format_fallback(payload)).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", r"\1", text, flags=re.DOTALL).strip()
        return schema.model_validate_json(text)

    async def _stream_chat(self, payload: dict) -> AsyncIterator[str]:
        """SSE streaming: `data:` lines carrying delta chunks, `[DONE]` terminator."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:") :].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    chunk = (choices[0].get("delta") or {}).get("content")
                    if chunk:
                        yield chunk

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        payload = self._payload(prompt, model, max_tokens, None)
        payload["stream"] = True
        async for chunk in self._stream_chat(payload):
            yield chunk

    async def stream_messages(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        # Chat-completions speaks message arrays natively — no prompt flattening.
        msgs: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            msgs.append({"role": msg.get("role", "user"), "content": content})
        payload = {
            "model": self._model(model),
            "max_tokens": max_tokens,
            "messages": msgs,
            "stream": True,
        }
        async for chunk in self._stream_chat(payload):
            yield chunk


def _resolve_api_key() -> str:
    """Resolve API key: direct env var, or Claude subscription OAuth token."""
    key = settings.llm_api_key
    if key and not key.startswith("sk-test") and not key.startswith("sk-ant-...") and len(key) > 20:
        return key
    # Fall back to Claude subscription OAuth token
    try:
        import json as _json
        from pathlib import Path

        creds_path = Path.home() / ".claude" / ".credentials.json"
        data = _json.loads(creds_path.read_text(encoding="utf-8"))
        token = data.get("claudeAiOauth", {}).get("accessToken")
        if token:
            return token
    except Exception:
        pass
    return key  # return whatever we have


# Re-entrancy guard: complete_json() delegates to complete() on some providers, so
# instrumenting both in place would nest two spans for one logical call. Only the
# OUTERMOST instrumented call opens a span; inner delegated calls run inside it.
_in_llm_call: contextvars.ContextVar[bool] = contextvars.ContextVar("ace_in_llm_call", default=False)

_TRACED_CALL_METHODS = ("complete", "complete_json", "complete_structured")
_TRACED_STREAM_METHODS = ("stream", "stream_messages")


def _provider_system(provider) -> str:
    """Map a provider instance to its gen_ai.system label (OTel GenAI conventions)."""
    name = type(provider).__name__
    mapping = {
        "ClaudeProvider": "anthropic",
        "CLIProvider": "anthropic",  # claude CLI subprocess
        "CodexCLIProvider": "openai",
        "OllamaProvider": "ollama",
        "OpenAICompatProvider": "openai",
        "LiteLLMProvider": "litellm",
        "AnyLLMProvider": "any-llm",
    }
    return mapping.get(name, name.replace("Provider", "").lower() or "unknown")


def _wrap_call(method, system: str):
    """Wrap a coroutine LLM-call method so each top-level invocation opens a gen_ai span.

    The span's gen_ai.request.model comes from the `model` kwarg when present
    (otherwise 'default'); the response model + usage tokens are filled in by the
    provider via set_gen_ai_usage() on the same (current) span.
    """

    @functools.wraps(method)
    async def _traced(*args, **kwargs):
        if _in_llm_call.get():
            return await method(*args, **kwargs)  # nested delegated call — already spanned
        from core.engine.core.otel import gen_ai_span

        token = _in_llm_call.set(True)
        try:
            with gen_ai_span(system, kwargs.get("model") or "default"):
                return await method(*args, **kwargs)
        finally:
            _in_llm_call.reset(token)

    return _traced


def _wrap_stream(method, system: str):
    """Wrap an async-generator streaming method so the span covers the whole stream."""

    @functools.wraps(method)
    async def _traced(*args, **kwargs):
        if _in_llm_call.get():
            async for chunk in method(*args, **kwargs):
                yield chunk
            return
        from core.engine.core.otel import gen_ai_span

        token = _in_llm_call.set(True)
        try:
            with gen_ai_span(system, kwargs.get("model") or "default"):
                async for chunk in method(*args, **kwargs):
                    yield chunk
        finally:
            _in_llm_call.reset(token)

    return _traced


def _instrument_llm(provider, system: str):
    """Instrument a provider's LLM-call methods with OTel GenAI spans, IN PLACE.

    Returns the SAME instance, so isinstance()/type() checks and provider-specific
    attributes keep working and every direct get_llm() caller gets the concrete
    provider it expects — only complete/complete_json/complete_structured/stream/
    stream_messages are wrapped. Idempotent: a provider is instrumented at most once.
    """
    if getattr(provider, "_gen_ai_instrumented", False):
        return provider
    for name in _TRACED_CALL_METHODS:
        method = getattr(provider, name, None)
        if method is not None:
            setattr(provider, name, _wrap_call(method, system))
    for name in _TRACED_STREAM_METHODS:
        method = getattr(provider, name, None)
        if method is not None:
            setattr(provider, name, _wrap_stream(method, system))
    try:
        provider._gen_ai_instrumented = True
    except Exception:  # pragma: no cover — exotic providers may block setattr
        pass
    return provider


def get_llm() -> "LLMProvider":
    """Public entry: resolve a provider (see _resolve_llm) and instrument its LLM-call
    methods with OTel GenAI spans, in place. Returns the SAME provider instance — so
    isinstance/type checks and provider-specific attributes keep working; only the
    call methods (complete/complete_json/complete_structured/stream/stream_messages)
    are wrapped."""
    provider = _resolve_llm()
    return _instrument_llm(provider, _provider_system(provider))


def _find_codex_bin() -> str | None:
    """Locate Codex without inspecting its authentication store."""
    fallback_paths = (
        os.path.expanduser("~/.local/bin/codex"),
        "/usr/local/bin/codex",
        "/opt/homebrew/bin/codex",
        "/Applications/ChatGPT.app/Contents/Resources/codex",
    )
    return shutil.which("codex") or next(
        (path for path in fallback_paths if os.path.isfile(path) and os.access(path, os.X_OK)),
        None,
    )


def _resolve_llm() -> "LLMProvider":
    """Resolve LLM provider in priority order (post-June-15-2026 reality):

    1. settings.litellm_model set → LiteLLMProvider (optional `ace[litellm]`
       extra, lazy-imported — a clear "pip install 'ace[litellm]'" error if the
       extra is missing). An explicitly configured router model is the MOST
       explicit intent in the chain (it names both provider and model), so it
       claims the top slot. If anyllm_model is ALSO set, litellm wins and a
       warning logs — unset one to silence it.
    2. settings.anyllm_model set → AnyLLMProvider (optional `ace[any-llm]`
       extra, same lazy-import discipline). Same explicit-intent rationale.
    3. settings.ollama_host set → OllamaProvider (local Ollama inference)
    4. settings.openai_compat_base_url set, via OPENAI_COMPAT_BASE_URL (alias:
       OPENAI_BASE_URL; canonical wins when both are set) → OpenAICompatProvider
       (an explicit base_url is explicit intent — OpenAI, Azure, Groq, Together,
       OpenRouter, vLLM, LM Studio, Ollama-compat; the api key is optional,
       local servers run keyless)
    5. SUBSCRIPTION_PROVIDER=codex → CodexCLIProvider through documented
       ``codex exec`` + ChatGPT sign-in. This is explicit operator intent and
       never reads or forwards Codex's cached credentials.
    6. Explicit metered API key (LLM_API_KEY — config.py reads no other name;
       the value is passed to AsyncAnthropic explicitly) → ClaudeProvider
       (direct API, fastest, METERED — pay-per-token, not subscription)
    7. CLAUDE_CODE_OAUTH_TOKEN set → ClaudeProvider via OAuth bearer (the SANCTIONED
       subscription-programmatic shape — a `claude setup-token` credential, sent as
       `Authorization: Bearer` + the `oauth-2025-04-20` beta header; no subprocess)
    8. [opt-in: ALLOW_OAUTH_API_PATH=1] subscription OAuth access token lifted from
       the local credentials store → ClaudeProvider as `x-api-key` (UNDOCUMENTED
       OAuth-as-API shape; off by default — Anthropic publishes no sanction for it)
    9. `claude` CLI in PATH → CLIProvider (subprocess per call). NOTE: this is
       `claude -p`-shaped, so on subscription plans it draws from the monthly
       **Agent SDK credit** (Pro $20 / Max 5x $100 / Max 20x $200) starting
       June 15 2026, and HARD-STOPS when that credit is exhausted unless usage
       credits (API-rate overage) are enabled. Prefer slot 7 for headless/CI runs.
    10. OPENAI_COMPAT_API_KEY (alias: OPENAI_API_KEY — the ambient-export case
       this slot exists to handle) set with NO Anthropic credentials and NO
       usable CLI → OpenAICompatProvider against https://api.openai.com/v1 (a
       bare key with no base_url means OpenAI itself). Deliberately the LAST
       resort before the loud-fail: a stray OPENAI_API_KEY export must never
       outrank a working subscription CLI. The tier maps now translate ACE's
       Anthropic model names for this provider, so the slot WORKS — promoting
       it above the CLI is a deliberate follow-up decision, not automatic.
       Deliberate OpenAI users set OPENAI_COMPAT_BASE_URL (slot 4).
    11. Final fallback → empty ClaudeProvider (errors loudly on first use)

    Slot 7 is the recommended Claude subscription path: a long-lived (one-year)
    inference token, no per-call subprocess overhead, and a documented/sanctioned
    shape — yet it bills the same subscription pool as the CLI. Slot 8 is the legacy fast-HTTP
    promotion, now gated off by default because the shape is unsanctioned.
    Set FORCE_CLI_PROVIDER=1 to force the Claude subprocess (slots 7, 8 and 10
    skipped). FORCE_CLI does NOT skip slots 1-4 (explicit router/backend config) —
    an explicit backend choice outranks the CLI-forcing flag, consistent with the
    flag never skipping ollama_host or the metered key either.

    Safeguard: when REQUIRE_SUBSCRIPTION=1, slot 6 is refused (clear RuntimeError)
    and slot 10 is skipped — an accidentally-set key (Anthropic OR OpenAI) cannot
    silently bill a metered API. Slots 1, 2 and 4 stay exempt from the safeguard:
    the router slots cannot be triggered by ambient credentials at all (only the
    explicit LITELLM_MODEL / ANYLLM_MODEL settings activate them — deliberate
    operator intent, the thing the safeguard exists to distinguish from
    accidents), and an explicit OPENAI_COMPAT_BASE_URL is the same deliberate
    choice.
    """
    # Slots 1-2 — explicit router config (optional extras, lazy-imported). The
    # provider __init__ raises the actionable install hint when the extra is
    # absent: explicit config + missing dependency = loud fail, never a silent
    # fall-through to a different (differently-billed) backend.
    if getattr(settings, "litellm_model", None):
        if getattr(settings, "anyllm_model", None):
            logger.warning(
                "Both LITELLM_MODEL and ANYLLM_MODEL are set — litellm wins "
                "(documented precedence). Unset one to silence this warning."
            )
        from core.engine.core.llm_litellm import LiteLLMProvider

        logger.info("Using LiteLLMProvider (%s)", settings.litellm_model)
        return LiteLLMProvider(
            default_model=settings.litellm_model,
            model_map=getattr(settings, "litellm_model_map", None),
        )

    if getattr(settings, "anyllm_model", None):
        from core.engine.core.llm_anyllm import AnyLLMProvider

        logger.info("Using AnyLLMProvider (%s)", settings.anyllm_model)
        return AnyLLMProvider(
            default_model=settings.anyllm_model,
            model_map=getattr(settings, "anyllm_model_map", None),
        )

    if settings.ollama_host:
        logger.info("Using OllamaProvider (%s)", settings.ollama_host)
        return OllamaProvider(
            host=settings.ollama_host,
            default_model=settings.ollama_model,
            model_map=getattr(settings, "ollama_model_map", None),
        )

    # Slot 4 — explicit OpenAI-compat intent: the operator configured a base_url,
    # so it outranks any Anthropic credentials sitting in the environment.
    if settings.openai_compat_base_url:
        logger.info("Using OpenAICompatProvider (%s)", settings.openai_compat_base_url)
        return OpenAICompatProvider(
            base_url=settings.openai_compat_base_url,
            api_key=settings.openai_compat_api_key,
            default_model=settings.openai_compat_model,
            model_map=getattr(settings, "openai_compat_model_map", None),
        )

    subscription_provider = getattr(settings, "subscription_provider", "auto")
    if subscription_provider == "codex":
        codex_bin = _find_codex_bin()
        if not codex_bin:
            raise RuntimeError(
                "SUBSCRIPTION_PROVIDER=codex but no Codex CLI executable was found. "
                "Install Codex, run `codex login` with ChatGPT, and retry."
            )
        logger.info("Using CodexCLIProvider (%s) via ChatGPT subscription", codex_bin)
        semantic_efforts = {
            settings.llm_budget_model: getattr(settings, "llm_budget_effort", "default"),
            settings.llm_model: getattr(settings, "llm_effort", "default"),
            settings.llm_reasoning_model: getattr(settings, "llm_reasoning_effort", "high"),
            settings.llm_frontier_model: getattr(settings, "llm_frontier_effort", "xhigh"),
            **(getattr(settings, "codex_cli_effort_map", None) or {}),
        }
        return CodexCLIProvider(
            default_model=getattr(settings, "codex_cli_model", "gpt-5.6-terra"),
            codex_bin=codex_bin,
            model_map=getattr(settings, "codex_cli_model_map", None),
            default_effort=getattr(settings, "codex_cli_effort", "default"),
            effort_map=semantic_efforts,
        )

    key = settings.llm_api_key
    _looks_real = key and not key.startswith("sk-test") and not key.startswith("sk-ant-...") and len(key) > 20
    if _looks_real:
        if getattr(settings, "require_subscription", False):
            # Refuse to silently bill. Operator opted into subscription-only;
            # an env that still carries a real key is a config mistake.
            raise RuntimeError(
                "REQUIRE_SUBSCRIPTION=1 but LLM_API_KEY looks like a real metered "
                "key. Either:\n"
                "  (a) replace the key with a placeholder (e.g. sk-test-placeholder) "
                "so the resolver falls through to subscription OAuth / CLI,\n"
                "  (b) unset REQUIRE_SUBSCRIPTION to allow metered API,\n"
                "  (c) use Ollama by setting OLLAMA_HOST.\n"
                "See core/engine/core/llm.py:get_llm() for the resolver order."
            )
        logger.info("Using ClaudeProvider via direct API key (METERED)")
        return ClaudeProvider(api_key=key, default_model=settings.llm_model)

    _force_cli = getattr(settings, "force_cli_provider", False)

    # Slot 7 — sanctioned subscription-programmatic path: `claude setup-token`
    # bearer in CLAUDE_CODE_OAUTH_TOKEN. Documented OAuth shape (Authorization:
    # Bearer + oauth-2025-04-20). Draws the same subscription pool as the CLI but
    # with no subprocess. Takes precedence over the CLI and the undocumented slot.
    if not _force_cli:
        setup_token = (
            os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
            or getattr(settings, "claude_code_oauth_token", "").strip()
        )
        if setup_token and len(setup_token) > 20:
            logger.info("Using ClaudeProvider via CLAUDE_CODE_OAUTH_TOKEN (sanctioned OAuth bearer)")
            return ClaudeProvider(api_key="", default_model=settings.llm_model, oauth_token=setup_token)

    # Slot 8 — UNDOCUMENTED OAuth-as-API: lift the subscription OAuth access token
    # from the local credentials store and send it as x-api-key. Off by default;
    # opt in with ALLOW_OAUTH_API_PATH=1 only if you've verified it in your env.
    if not _force_cli and getattr(settings, "allow_oauth_api_path", False):
        oauth = _resolve_api_key()
        if oauth and len(oauth) > 20:
            logger.warning(
                "Using ClaudeProvider via OAuth-as-API (x-api-key) — UNDOCUMENTED shape, "
                "enabled by ALLOW_OAUTH_API_PATH=1. Prefer CLAUDE_CODE_OAUTH_TOKEN."
            )
            return ClaudeProvider(api_key=oauth, default_model=settings.llm_model)

    _fallback_paths = [
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
    ]
    claude_bin = shutil.which("claude") or next(
        (p for p in _fallback_paths if os.path.isfile(p) and os.access(p, os.X_OK)), None
    )
    if claude_bin:
        logger.info("Using CLIProvider (%s) — slow path; subscription OAuth unavailable", claude_bin)
        return CLIProvider(default_model=settings.llm_model, claude_bin=claude_bin)

    # Slot 10 — bare OPENAI_COMPAT_API_KEY (alias: OPENAI_API_KEY — the ambient
    # export this slot guards against), last resort above the loud-fail. BELOW
    # the CLI on purpose: a stray OPENAI_API_KEY export must not break a machine
    # whose subscription CLI works. Task 3's tier maps now translate the
    # Anthropic model names ACE call sites pass (the original 404 hazard is
    # gone for api.openai.com), so the slot CAN move above the CLI — but that
    # promotion is a deliberate provider-preference decision (metered OpenAI
    # vs. paid-for subscription), made as its own follow-up, not a side effect
    # of the maps landing. Skipped under REQUIRE_SUBSCRIPTION (no silent
    # metered billing) and FORCE_CLI_PROVIDER (the operator demanded the
    # subprocess).
    if not _force_cli and not getattr(settings, "require_subscription", False) and settings.openai_compat_api_key:
        logger.info("Using OpenAICompatProvider (https://api.openai.com/v1) — bare OPENAI_COMPAT_API_KEY")
        return OpenAICompatProvider(
            base_url="https://api.openai.com/v1",
            api_key=settings.openai_compat_api_key,
            default_model=settings.openai_compat_model,
            model_map=getattr(settings, "openai_compat_model_map", None),
        )

    logger.warning("No LLM provider available — returning non-functional ClaudeProvider")
    return ClaudeProvider(api_key="", default_model=settings.llm_model)


# Module-level provider — import this everywhere: `from core.engine.core.llm import llm`
#
# Resolved LAZILY on first attribute access, never at import. This was previously
# `llm = get_llm()`, an import-time side effect that could RAISE (e.g. under
# REQUIRE_SUBSCRIPTION=1 with a real-looking LLM_API_KEY) — making this module,
# and the ~50 modules that `import llm`, un-importable during test collection
# unless a conftest pre-set a safe env. The proxy keeps the import free and
# non-raising while preserving singleton semantics: the provider is built once on
# first use and CACHED (required — CLIProvider._stats accumulates per session, so
# re-resolving per call would reset token accounting).
class _LazyLLMProxy:
    """Transparent lazy proxy over the resolved LLM provider.

    Delegates every attribute (complete, stream, default_model, _stats, …) to a
    provider resolved via get_llm() on first use and cached thereafter. Importing
    the proxy is free and never raises; the first real call resolves the provider.
    """

    def __init__(self) -> None:
        # Set via object.__setattr__ so the attribute always exists — __getattr__
        # then never fires for it, and the resolver below cannot recurse.
        object.__setattr__(self, "_cached_provider", None)

    def _resolve(self) -> "LLMProvider":
        provider = self._cached_provider
        if provider is None:
            provider = get_llm()
            object.__setattr__(self, "_cached_provider", provider)
        return provider

    def __getattr__(self, name: str):
        # Only invoked for names absent on the proxy itself (e.g. complete);
        # _cached_provider is set in __init__, so this never recurses.
        return getattr(self._resolve(), name)


llm = _LazyLLMProxy()

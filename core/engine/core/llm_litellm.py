# engine/core/llm_litellm.py
"""LiteLLMProvider — the 100+-provider router, behind the optional `litellm` extra.

This module imports cleanly WITHOUT litellm installed: the SDK import happens
inside ``LiteLLMProvider.__init__`` and raises an actionable error pointing at
``pip install 'ace[litellm]'``. Nothing in the default install may import
litellm at module-import time — tests/llm/test_lazy_extras.py pins that.

SECURITY NOTE (why this is an extra, not a core dep): the March 2026 PyPI
supply-chain compromise of the litellm package itself (1.82.7/1.82.8 shipped a
credential stealer + RCE) and CVE-2026-42208 (pre-auth SQLi, CVSS 9.3) keep
litellm out of the default install. The extra pins ``litellm>=1.83.7`` (the
SQLi fix) — see pyproject.toml.

Model vocabulary: litellm routes by ``provider/model`` strings
("anthropic/claude-sonnet-5", "groq/llama-3.3-70b-versatile", …) — that
syntax IS the tier map for power users. ACE call sites still pass bare
Anthropic tier names, so ModelMapMixin translates per request:

- When ``litellm_model`` targets Anthropic (starts with "anthropic/"), the
  built-in defaults map the four Claude tiers to their "anthropic/"-prefixed
  forms — cost-aware tier routing works out of the box, billing the provider
  the operator already chose. (litellm's registry can resolve bare claude
  names too, but the explicit prefix is litellm's documented recommended form
  and immune to registry lag on new models.)
- When ``litellm_model`` targets any OTHER provider, the map starts EMPTY and
  Anthropic tier names collapse to the configured default model with a
  one-time warning. Deliberate: defaulting tiers to "anthropic/..." here
  would silently re-route ACE's traffic to a metered Anthropic key the
  operator never chose — the same no-silent-billing posture as
  REQUIRE_SUBSCRIPTION. LITELLM_MODEL_MAP restores tiered routing.

JSON/structured discipline: prompt-based only (instruction + fence-strip +
parse), no ``response_format`` negotiation — support for it varies wildly
across litellm's 100+ backends, and the router's job is reach, not format
negotiation. Same caller-visible contract as ClaudeProvider.complete_json.

Cache-control system blocks are flattened to plain text (litellm can forward
them for Anthropic targets, but generic backends can't — flattening is the
lowest-common-denominator discipline shared with OllamaProvider; revisit if a
litellm-Anthropic deployment needs stable_prefix caching, where ClaudeProvider
is the better tool anyway).

Usage persistence: per-call, fail-open, source="litellm",
billing="metered_estimate" — litellm fronts metered APIs, and the cost is an
estimate (litellm's own ``response_cost`` hidden param when present, else
model_costs.cost_for_call, else 0.0). Streaming carries no usage by default
(stream_options.include_usage is not requested — same deliberate scope cut as
OpenAICompatProvider).
"""

from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator

from pydantic import BaseModel

from core.engine.core.llm import ModelMapMixin, _persist_usage_row

logger = logging.getLogger(__name__)

_INSTALL_HINT = (
    "LiteLLMProvider requires the optional 'litellm' extra, which is not installed.\n"
    "Install it with:\n"
    "    pip install 'ace[litellm]'    # or: uv sync --extra litellm\n"
    "Security floor: litellm>=1.83.7 (March 2026 supply-chain compromise and "
    "CVE-2026-42208 are fixed there) — never pin below it."
)

# Built-in tier translations applied ONLY when the configured default model
# already targets Anthropic ("anthropic/..."): same billing target, so mapping
# ACE's four Claude tiers to their prefixed forms preserves cost-aware routing with
# zero config. Any other target starts with an EMPTY map (see module docstring).
_ANTHROPIC_PREFIX_TIER_DEFAULTS: dict[str, str] = {
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4-5-20251001",
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
    "claude-opus-4-8": "anthropic/claude-opus-4-8",
    "claude-fable-5": "anthropic/claude-fable-5",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4-6",
    "claude-opus-4-6": "anthropic/claude-opus-4-6",
}


def _flatten_system(system: str | list[dict] | None) -> str | None:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        # Flatten content blocks — no cache_control on the generic router wire.
        return " ".join(b.get("text", "") for b in system if isinstance(b, dict))
    return None


def _extract_content(response) -> str:
    """OpenAI-format response → text. `content` may be null (refusals)."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return getattr(message, "content", None) or ""


class LiteLLMProvider(ModelMapMixin):
    """LLMProvider over ``litellm.acompletion`` (OpenAI-format responses)."""

    _map_setting_name = "LITELLM_MODEL_MAP"

    def __init__(self, default_model: str, model_map: dict[str, str] | None = None) -> None:
        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError(_INSTALL_HINT) from exc
        # Module reference, attribute looked up per call — keeps monkeypatching
        # litellm.acompletion effective in the conformance wiring.
        self._litellm = litellm
        self._default_model = default_model
        defaults = _ANTHROPIC_PREFIX_TIER_DEFAULTS if default_model.startswith("anthropic/") else None
        self._init_model_map(model_map, defaults)

    def _model(self, model: str | None) -> str:
        return self._resolve_model(model)

    @staticmethod
    def _messages(prompt: str, system: str | list[dict] | None) -> list[dict]:
        messages: list[dict] = []
        sys_text = _flatten_system(system)
        if sys_text is not None:
            messages.append({"role": "system", "content": sys_text})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def _persist_usage(self, response, model_name: str) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        # litellm reports its own cost estimate in hidden params when it knows
        # the model's rates — prefer it over ACE's bounded static table.
        hidden = getattr(response, "_hidden_params", None)
        cost = hidden.get("response_cost") if isinstance(hidden, dict) else None
        await _persist_usage_row(
            model_name=model_name,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            task_id="litellm_provider",
            task_type="chat_completion",
            source="litellm",
            billing="metered_estimate",
            cost_usd=cost,
        )

    async def _acomplete(self, messages: list[dict], model: str | None, max_tokens: int) -> str:
        resolved = self._model(model)
        response = await self._litellm.acompletion(model=resolved, messages=messages, max_tokens=max_tokens)
        await self._persist_usage(response, resolved)
        return _extract_content(response)

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | list[dict] | None = None,
    ) -> str:
        return await self._acomplete(self._messages(prompt, system), model, max_tokens)

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
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    async def complete_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> BaseModel:
        schema_str = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        full_prompt = (
            f"{prompt}\n\n"
            f"Return JSON that strictly matches this schema:\n{schema_str}\n\n"
            f"Return JSON only. No markdown."
        )
        text = (await self.complete(full_prompt, model=model, max_tokens=max_tokens)).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", r"\1", text, flags=re.DOTALL).strip()
        return schema.model_validate_json(text)

    async def _stream(self, messages: list[dict], model: str | None, max_tokens: int) -> AsyncIterator[str]:
        stream = await self._litellm.acompletion(
            model=self._model(model),
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            text = getattr(delta, "content", None)
            if text:
                yield text

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        async for chunk in self._stream([{"role": "user", "content": prompt}], model, max_tokens):
            yield chunk

    async def stream_messages(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        # The router wire speaks message arrays natively — no prompt flattening.
        msgs: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            msgs.append({"role": msg.get("role", "user"), "content": content})
        async for chunk in self._stream(msgs, model, max_tokens):
            yield chunk

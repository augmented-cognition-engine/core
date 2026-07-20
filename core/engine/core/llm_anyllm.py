# engine/core/llm_anyllm.py
"""AnyLLMProvider — Mozilla AI's any-llm router, behind the optional `any-llm` extra.

This module imports cleanly WITHOUT any-llm-sdk installed: the SDK import
happens inside ``AnyLLMProvider.__init__`` and raises an actionable error
pointing at ``pip install 'ace[any-llm]'``. Nothing in the default install may
import any_llm at module-import time — tests/llm/test_lazy_extras.py pins that.

Why a second router extra: any-llm-sdk (Apache-2.0 — license-matched to ACE)
has a clean vulnerability record and per-provider extras, offered alongside
litellm so adopters can pick their risk posture (litellm carries the March
2026 supply-chain history; see llm_litellm.py and pyproject.toml). Since
v1.10 any-llm also ships an Anthropic Messages compat layer; ACE doesn't use
it — this adapter speaks any-llm's native OpenAI-format completion API.

Model vocabulary: any-llm's current docs recommend passing ``provider=`` and
``model=`` separately (the combined "provider/model" / "provider:model"
strings are accepted but deprecated). ACE config keeps ONE string for
ergonomics — ``ANYLLM_MODEL="anthropic/claude-sonnet-5"`` — and this
adapter splits the provider prefix off at the call boundary, so the
deprecated combined path never reaches the SDK. ModelMapMixin translation
mirrors llm_litellm.py:

- Default model targeting Anthropic ("anthropic/...") → built-in defaults map
  ACE's four Claude tiers to their prefixed forms (same billing target the operator
  chose; tier routing works out of the box).
- Any other provider → EMPTY map; Anthropic tier names collapse to the
  configured default with a one-time warning (no silent re-routing to a
  provider the operator didn't pick). ANYLLM_MODEL_MAP restores tiering —
  values use the combined "provider/model" form.

JSON/structured discipline: prompt-based only (instruction + fence-strip +
parse) — any-llm's ``response_format`` accepts a pydantic model, but support
varies per backend; the lowest-common-denominator contract stays uniform with
LiteLLMProvider. Cache-control system blocks are flattened (no cache_control
on the generic router wire).

Usage persistence: per-call, fail-open, source="anyllm",
billing="metered_estimate". any-llm exposes no per-call cost figure, so
cost_usd comes from model_costs.cost_for_call (unknown wire names record 0.0
— unknown-model grace). Streaming carries no usage by default (same scope cut
as OpenAICompatProvider).
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
    "AnyLLMProvider requires the optional 'any-llm' extra, which is not installed.\n"
    "Install it with:\n"
    "    pip install 'ace[any-llm]'    # or: uv sync --extra any-llm\n"
    "Note: any-llm itself ships per-provider extras — the backend named by "
    "ANYLLM_MODEL's provider prefix must be installed too "
    "(e.g. pip install 'any-llm-sdk[anthropic]')."
)

# Built-in tier translations applied ONLY when the configured default model
# already targets Anthropic — same rationale as llm_litellm.py: same billing
# target, zero-config tier routing; any other target starts EMPTY.
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
        return " ".join(b.get("text", "") for b in system if isinstance(b, dict))
    return None


def _extract_content(response) -> str:
    """OpenAI-format ChatCompletion → text. `content` may be null (refusals)."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return getattr(message, "content", None) or ""


def _split_provider(model_string: str) -> tuple[str | None, str]:
    """Split "provider:model" / "provider/model" into (provider, model).

    ':' wins over '/' so "huggingface:org/model" keeps the slash inside the
    model name; with '/' only, the FIRST segment is the provider (the rest may
    legitimately contain more slashes). No separator → (None, model): the SDK
    raises its own provider-required error, which names the real problem.
    """
    if ":" in model_string:
        provider, _, name = model_string.partition(":")
        return provider, name
    if "/" in model_string:
        provider, _, name = model_string.partition("/")
        return provider, name
    return None, model_string


class AnyLLMProvider(ModelMapMixin):
    """LLMProvider over ``any_llm.acompletion`` (OpenAI-format responses)."""

    _map_setting_name = "ANYLLM_MODEL_MAP"

    def __init__(self, default_model: str, model_map: dict[str, str] | None = None) -> None:
        try:
            import any_llm
        except ImportError as exc:
            raise RuntimeError(_INSTALL_HINT) from exc
        # Module reference, attribute looked up per call — keeps monkeypatching
        # any_llm.acompletion effective in the conformance wiring.
        self._any_llm = any_llm
        self._default_model = default_model
        provider_prefix, _ = _split_provider(default_model)
        defaults = _ANTHROPIC_PREFIX_TIER_DEFAULTS if provider_prefix == "anthropic" else None
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

    def _call_kwargs(self, messages: list[dict], model: str | None, max_tokens: int) -> tuple[dict, str]:
        """Build acompletion kwargs + the combined name used for the ledger.

        provider= and model= go to the SDK separately (its recommended,
        non-deprecated shape); the ledger keeps the combined string so the row
        names the full routing intent.
        """
        resolved = self._model(model)
        provider, name = _split_provider(resolved)
        kwargs: dict = {"model": name, "messages": messages, "max_tokens": max_tokens}
        if provider is not None:
            kwargs["provider"] = provider
        return kwargs, resolved

    async def _persist_usage(self, response, model_name: str) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        await _persist_usage_row(
            model_name=model_name,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            task_id="anyllm_provider",
            task_type="chat_completion",
            source="anyllm",
            billing="metered_estimate",
        )

    async def _acomplete(self, messages: list[dict], model: str | None, max_tokens: int) -> str:
        kwargs, resolved = self._call_kwargs(messages, model, max_tokens)
        response = await self._any_llm.acompletion(**kwargs)
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
        kwargs, _ = self._call_kwargs(messages, model, max_tokens)
        kwargs["stream"] = True
        stream = await self._any_llm.acompletion(**kwargs)
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
        msgs: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            msgs.append({"role": msg.get("role", "user"), "content": content})
        async for chunk in self._stream(msgs, model, max_tokens):
            yield chunk

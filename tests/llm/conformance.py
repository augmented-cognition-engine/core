# tests/llm/conformance.py
"""Provider conformance suite — the LLMProvider Protocol made enforceable.

`core/engine/core/llm.py` declares a `runtime_checkable` Protocol, but a
Protocol only checks method *signatures*. This suite checks *behavior*: every
provider, mocked at its transport layer, must produce the same caller-visible
semantics for the five Protocol methods. The EXISTING providers' behavior
(read end-to-end on 2026-06-11) is the contract — where providers genuinely
diverge for transport reasons, the divergence is encoded in an explicit,
per-provider override knob below, never silently skipped.

Wiring a new provider (e.g. Task 2's OpenAICompatProvider) = ONE small file:

    class TestOpenAICompatConformance(LLMConformanceSuite):
        default_model = "gpt-4o-mini"
        override_model = "gpt-4o"

        @pytest.fixture(autouse=True)
        def _transport(self, monkeypatch):
            ...install the mocked httpx transport on self...

        def make_provider(self): ...
        def respond_text(self, text): ...
        def respond_empty(self): ...
        def respond_stream(self, chunks): ...
        def last_request(self) -> CapturedRequest: ...
        def transport_calls(self) -> int: ...

plus any divergence knobs with a reason string. Nothing here may assume
chat-completions is the only wire shape — hooks speak in normalized
`CapturedRequest` terms, not endpoint shapes.

Contract summary (derived from the existing providers):
- complete() returns the backend's text; honors `model=` override and
  `max_tokens`; defaults to the provider's `default_model`.
- `system` may be a `str` OR a list of cache-control blocks. Backends with
  native cache support pass blocks through verbatim (ClaudeProvider — the
  multiphase `stable_prefix` caching depends on this); all others flatten to
  plain text. Either way every block's text MUST reach the transport.
- complete_json() appends the "Return valid JSON only" instruction, strips
  markdown fences, returns a parsed dict, forwards `system`, and raises
  `json.JSONDecodeError` on garbage. Retry-on-garbage count is per-provider
  (CLI retries 3x against subprocess flake; HTTP providers raise on first
  garbage — that IS the established contract, asserted via knob).
- complete_structured() round-trips a pydantic schema.
- stream() / stream_messages() yield incremental text chunks.
- An empty backend response yields "" from complete() — never None, never an
  exception. Retry-on-empty is CLI-only discipline (knob).
- Callers speak ACE's Anthropic model-name tier vocabulary
  (ANTHROPIC_TIER_MODELS); each provider decides what reaches the wire.
  Anthropic-native transports pass the names through (knob = None); the
  others translate via their Task-3 model maps (knob = expected per-tier
  wire names).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

CACHE_BLOCKS = [
    {"type": "text", "text": "stable prefix", "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": "dynamic suffix"},
]

# The Anthropic tier vocabulary ACE call sites actually pass — discovered from
# settings.llm_budget_model / llm_model / llm_reasoning_model /
# llm_frontier_model and
# runtime/model_config.py's TIER_TO_MODEL. Tier RENAMES are out of scope:
# callers keep these names; providers translate (or pass through) per-request.
ANTHROPIC_TIER_MODELS = (
    "claude-haiku-4-5-20251001",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-fable-5",
)


class ConformanceSchema(BaseModel):
    name: str
    score: float


@dataclass
class CapturedRequest:
    """A provider's outbound request, normalized away from its wire shape."""

    model: str | None = None
    max_tokens: int | None = None
    # `system` exactly as it sits in the outbound payload (str, list, or None).
    system_raw: object = None
    # The system content as flat text (joined block texts for list shapes).
    system_text: str | None = None
    prompt: str | None = None


class LLMConformanceSuite:
    """Subclass per provider; pytest collects the methods via Test*-named subclasses."""

    # --- identity (every wiring sets these) -------------------------------
    default_model: str = ""
    override_model: str = ""

    # --- divergence knobs (override WITH a reason comment) ----------------
    # ClaudeProvider passes cache-control blocks through verbatim; everyone
    # else must flatten (their backends have no cache_control concept).
    passes_cache_blocks_through: bool = False
    # CLIProvider has no max-tokens flag — see its wiring for the reason.
    supports_max_tokens: bool = True
    max_tokens_skip_reason: str = ""
    # What reaches the transport when the caller passes NO system prompt.
    # None = the provider omits the field entirely (HTTP providers).
    # CLIProvider always injects its hermetic default prompt.
    default_system: str | None = None
    # Transport attempts when complete_json() keeps receiving garbage.
    # HTTP providers raise on the first bad parse; CLI retries 3x.
    json_garbage_transport_calls: int = 1
    # Transport attempts when the backend returns an empty completion.
    # Only the CLI retries (subprocess flake discipline); HTTP providers
    # return the empty string after a single round-trip.
    empty_response_transport_calls: int = 1
    # What reaches the wire when callers pass ACE's Anthropic tier names.
    # None = identity (Anthropic-native transports forward the names verbatim).
    # Providers with a Task-3 model map set the expected per-tier translations
    # — the proof that cost-aware routing survives off-Anthropic.
    expected_tier_translations: dict[str, str] | None = None

    # --- hooks each wiring implements --------------------------------------
    def make_provider(self):
        raise NotImplementedError

    def respond_text(self, text: str) -> None:
        """Arrange the mocked transport to answer completions with `text`."""
        raise NotImplementedError

    def respond_empty(self) -> None:
        """Arrange the mocked transport to answer with an empty completion."""
        raise NotImplementedError

    def respond_stream(self, chunks: list[str]) -> None:
        """Arrange the mocked transport to stream `chunks` incrementally."""
        raise NotImplementedError

    def last_request(self) -> CapturedRequest:
        """The most recent outbound request, normalized."""
        raise NotImplementedError

    def transport_calls(self) -> int:
        """How many completion round-trips the transport has served."""
        raise NotImplementedError

    # =======================================================================
    # complete()
    # =======================================================================

    async def test_complete_returns_text(self):
        provider = self.make_provider()
        self.respond_text("hello conformance")
        assert await provider.complete("hi") == "hello conformance"

    async def test_complete_uses_default_model(self):
        provider = self.make_provider()
        self.respond_text("ok")
        await provider.complete("hi")
        assert self.last_request().model == self.default_model

    async def test_complete_honors_model_override(self):
        provider = self.make_provider()
        self.respond_text("ok")
        await provider.complete("hi", model=self.override_model)
        assert self.last_request().model == self.override_model

    async def test_complete_honors_max_tokens(self):
        if not self.supports_max_tokens:
            pytest.skip(self.max_tokens_skip_reason)
        provider = self.make_provider()
        self.respond_text("ok")
        await provider.complete("hi", max_tokens=123)
        assert self.last_request().max_tokens == 123

    async def test_anthropic_tier_names_translate_per_provider_map(self):
        # Callers keep speaking Anthropic model names (tier renames are out of
        # scope) — the provider's model map decides what reaches the wire.
        provider = self.make_provider()
        for tier in ANTHROPIC_TIER_MODELS:
            self.respond_text("ok")
            await provider.complete("hi", model=tier)
            if self.expected_tier_translations is None:
                expected = tier  # identity: Anthropic-native transport
            else:
                expected = self.expected_tier_translations[tier]
            assert self.last_request().model == expected

    # =======================================================================
    # system handling — str AND cache-block list must both produce a valid
    # request; blocks flatten where the backend lacks cache support.
    # =======================================================================

    async def test_complete_system_string_reaches_transport(self):
        provider = self.make_provider()
        self.respond_text("ok")
        await provider.complete("hi", system="Be terse.")
        assert "Be terse." in (self.last_request().system_text or "")

    async def test_complete_cache_block_system_flattened_or_passed_through(self):
        provider = self.make_provider()
        self.respond_text("ok")
        await provider.complete("hi", system=CACHE_BLOCKS)
        req = self.last_request()
        # Every block's text must survive to the transport — never dropped.
        assert "stable prefix" in (req.system_text or "")
        assert "dynamic suffix" in (req.system_text or "")
        if self.passes_cache_blocks_through:
            # Native cache support: blocks verbatim (stable_prefix caching).
            assert req.system_raw == CACHE_BLOCKS
        else:
            # No cache_control downstream: must be a flat string, not dicts.
            assert isinstance(req.system_raw, str)

    async def test_complete_without_system_omits_or_defaults(self):
        provider = self.make_provider()
        self.respond_text("ok")
        await provider.complete("hi")
        req = self.last_request()
        if self.default_system is None:
            assert req.system_raw is None
        else:
            assert req.system_text == self.default_system

    # =======================================================================
    # complete_json()
    # =======================================================================

    async def test_complete_json_returns_parsed_dict(self):
        provider = self.make_provider()
        self.respond_text('{"key": "value"}')
        assert await provider.complete_json("give json") == {"key": "value"}
        # Shared discipline: every provider appends the JSON-only instruction.
        assert "Return valid JSON" in (self.last_request().prompt or "")

    async def test_complete_json_strips_markdown_fences(self):
        provider = self.make_provider()
        self.respond_text('```json\n{"key": "value"}\n```')
        assert await provider.complete_json("give json") == {"key": "value"}

    async def test_complete_json_forwards_system(self):
        provider = self.make_provider()
        self.respond_text('{"ok": true}')
        await provider.complete_json("give json", system="JSON expert.")
        assert "JSON expert." in (self.last_request().system_text or "")

    async def test_complete_json_raises_on_garbage(self):
        provider = self.make_provider()
        self.respond_text("definitely not json {{{")
        with pytest.raises(json.JSONDecodeError):
            await provider.complete_json("give json")
        assert self.transport_calls() == self.json_garbage_transport_calls

    # =======================================================================
    # complete_structured()
    # =======================================================================

    async def test_complete_structured_round_trips_schema(self):
        provider = self.make_provider()
        self.respond_text('{"name": "ace", "score": 0.9}')
        result = await provider.complete_structured("rate this", ConformanceSchema)
        assert isinstance(result, ConformanceSchema)
        assert result.name == "ace"
        assert result.score == pytest.approx(0.9)

    # =======================================================================
    # stream() / stream_messages()
    # =======================================================================

    async def test_stream_yields_incremental_chunks(self):
        provider = self.make_provider()
        self.respond_stream(["alpha", " beta", " gamma"])
        chunks = [c async for c in provider.stream("go")]
        assert chunks == ["alpha", " beta", " gamma"]

    async def test_stream_messages_yields_chunks(self):
        provider = self.make_provider()
        self.respond_stream(["one", " two"])
        chunks = [
            c
            async for c in provider.stream_messages(
                system="You are helpful.",
                messages=[{"role": "user", "content": "Hi"}],
            )
        ]
        assert chunks == ["one", " two"]

    # =======================================================================
    # empty-response handling
    # =======================================================================

    async def test_empty_response_returns_empty_string(self):
        provider = self.make_provider()
        self.respond_empty()
        assert await provider.complete("hi") == ""
        assert self.transport_calls() == self.empty_response_transport_calls

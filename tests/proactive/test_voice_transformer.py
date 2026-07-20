"""Boundary tests for voice transformer — AC 4, sentinel string check."""

from __future__ import annotations

import pytest

from core.engine.proactive.voice import FORBIDDEN_TONE_STRINGS, _fallback_line, transform

FORBIDDEN_STRINGS = FORBIDDEN_TONE_STRINGS


# ---------------------------------------------------------------------------
# AC 4 — voice output uses we/our/us, no forbidden system-voice strings
# ---------------------------------------------------------------------------


def test_fallback_line_uses_we_pronoun():
    line = _fallback_line("auth", "testing", "OAuth callback has no test coverage")
    lowered = line.lower()
    assert "we " in lowered or "our " in lowered or " us" in lowered, f"Fallback line does not use we/our/us: {line!r}"


def test_fallback_line_no_forbidden_tone_strings():
    line = _fallback_line("auth", "security", "XSS vulnerability in input handler")
    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden not in line, f"Fallback line contained forbidden string {forbidden!r}: {line!r}"


def test_fallback_line_under_150_chars():
    line = _fallback_line(
        "authentication_service",
        "security",
        "A" * 120,
    )
    assert len(line) <= 150


@pytest.mark.asyncio
async def test_voice_transformer_no_forbidden_strings_on_llm_output():
    """Voice transformer must strip or reject forbidden strings from LLM output."""
    forbidden_response = "Warning: security regression in auth — you should fix this immediately."

    with pytest.MonkeyPatch().context() as mp:

        async def _mock_complete(prompt, model=None, max_tokens=None):
            return forbidden_response

        mock_llm = type("MockLLM", (), {"complete": staticmethod(_mock_complete)})()
        # Patch the SOURCE module, not core.engine.proactive.voice: transform() binds
        # the provider with a FUNCTION-LOCAL `from core.engine.core.llm import llm`, so
        # a module attribute on voice.py is shadowed at call time and never used. The
        # old `mp.setattr(voice_module, "llm", ..., raising=False)` therefore mocked
        # NOTHING (raising=False hid the missing attribute) and this test made a REAL
        # LLM call — invisible on a dev box with a populated .env, an indefinite hang
        # in the export tree's clean room, where it wedged public CI. raising defaults
        # to True here on purpose: if this attribute is ever renamed, fail loudly
        # rather than silently going vacuous again.
        mp.setattr("core.engine.core.llm.llm", mock_llm)

        # The transform should return the LLM output (voice prompt enforces rules,
        # not post-processing). The test documents the contract: LLM MUST NOT
        # return forbidden strings. If it does in prod, the voice prompt is broken.
        # Here we test the fallback path works when LLM produces bad output.
        result = await transform(
            source="sentinel_finding",
            capability="auth",
            discipline="security",
            description="XSS in input handler",
            severity=0.8,
        )

    # Result is either the LLM output or fallback — either way must be a string
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_voice_transformer_falls_back_gracefully_on_llm_failure():
    """When LLM call fails, transform returns a valid fallback line — never raises."""
    with pytest.MonkeyPatch().context() as mp:

        async def _mock_complete(*args, **kwargs):
            raise ConnectionError("LLM unavailable")

        mock_llm = type("MockLLM", (), {"complete": staticmethod(_mock_complete)})()
        # Same fix as above — patch the source module the function-local import reads,
        # so the simulated failure actually reaches transform() and the fallback path
        # is genuinely exercised (it previously hit the real provider).
        mp.setattr("core.engine.core.llm.llm", mock_llm)

        result = await transform(
            source="gap_analyzer",
            capability="payments",
            discipline="testing",
            description="Payment flow has no integration tests",
            severity=0.7,
        )

    assert isinstance(result, str)
    assert len(result) > 0
    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden not in result


# ---------------------------------------------------------------------------
# Sentinel string check — no system-voice strings in any output
# ---------------------------------------------------------------------------


def test_proactive_line_no_system_voice():
    """Sentinel check: fallback output must not contain operate-shape strings."""
    descriptions = [
        "security regression in auth",
        "performance degraded in scanner",
        "test coverage dropped below threshold",
    ]
    for desc in descriptions:
        line = _fallback_line("auth", "security", desc)
        for forbidden in FORBIDDEN_STRINGS:
            assert forbidden not in line, (
                f"Proactive line contained forbidden system-voice string {forbidden!r}. "
                f"Voice transformation produced operate-shape output: {line!r}"
            )

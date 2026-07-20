"""Item K — cross-model grader via a local Ollama peer (un-starve calibration, keystone #1).

The grader must use a NON-Claude peer (local Ollama) when configured, so it stops self-grading
Claude's output. Critically, enabling the grader peer must NOT flip the global brain to Ollama
(get_llm reads settings.ollama_host; the grader uses a DEDICATED config + builds the provider
directly). See docs/superpowers/specs/2026-06-22-cross-model-grader-ollama-design.md.
"""

from __future__ import annotations


def test_make_grader_default_is_claude(monkeypatch):
    """No cross-model peer configured → default GraderAgent (Claude CLI path, no injected provider)."""
    import core.engine.core.config as cfg
    from core.engine.verification.grader import make_grader

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", None, raising=False)
    g = make_grader()
    assert g._provider is None, "default grader must have no injected provider (Claude CLI)"


def test_make_grader_uses_ollama_peer_when_configured(monkeypatch):
    """cross_model_grader_host set → GraderAgent with an OllamaProvider on that host + the peer model."""
    import core.engine.core.config as cfg
    from core.engine.core.llm import OllamaProvider
    from core.engine.verification.grader import make_grader

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    monkeypatch.setattr(cfg.settings, "cross_model_grader_model", "qwen2.5-coder:14b", raising=False)
    g = make_grader()
    assert isinstance(g._provider, OllamaProvider), "configured grader must inject an OllamaProvider (cross-model)"
    assert g._model == "qwen2.5-coder:14b"


def test_make_grader_does_not_flip_global_brain(monkeypatch):
    """Enabling the grader peer must NOT set the global ollama_host (which would route the whole brain
    to the local model via get_llm). The brain stays Claude; only the grader is cross-model."""
    import core.engine.core.config as cfg
    from core.engine.verification.grader import make_grader

    monkeypatch.setattr(cfg.settings, "ollama_host", None, raising=False)
    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    make_grader()
    assert cfg.settings.ollama_host is None, "grader peer config must never set the global ollama_host"


import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_complete_falls_back_to_claude_when_peer_fails(monkeypatch):
    """A configured-but-down peer must fall back to the Claude CLI, never collapse the grade to 0.0
    (review IMPORTANT: the cross-model grader must never be WORSE than the Claude baseline)."""
    from core.engine.verification.grader import GraderAgent

    class _BoomProvider:
        async def complete(self, *a, **k):
            raise RuntimeError("ollama unreachable")

    g = GraderAgent(model="qwen2.5-coder:14b", provider=_BoomProvider())
    fell_back = {}

    async def fake_run(prompt, timeout=90.0):
        fell_back["yes"] = True
        return '{"graded": true}'

    monkeypatch.setattr(g, "_run", fake_run)
    out = await g._complete("grade this artifact")
    assert fell_back.get("yes"), "must fall back to the Claude CLI when the peer raises"
    assert out == '{"graded": true}'


@pytest.mark.asyncio
async def test_complete_fail_closed_raises_when_fallback_disabled(monkeypatch):
    """FAIL-CLOSED (allow_fallback=False): a down peer must RAISE, never silently Claude-grade. The
    calibration grading engine needs this so a same-family grade is never mislabeled cross_model."""
    from core.engine.verification.grader import GraderAgent

    class _BoomProvider:
        async def complete(self, *a, **k):
            raise RuntimeError("ollama unreachable")

    g = GraderAgent(model="qwen2.5-coder:14b", provider=_BoomProvider(), allow_fallback=False)
    ran_claude = {}

    async def fake_run(prompt, timeout=90.0):
        ran_claude["yes"] = True
        return "{}"

    monkeypatch.setattr(g, "_run", fake_run)
    with pytest.raises(RuntimeError):
        await g._complete("grade this artifact")
    assert not ran_claude.get("yes"), "fail-closed must NOT fall back to the Claude CLI"


def test_make_grader_passes_fail_closed(monkeypatch):
    """make_grader(allow_fallback=False) builds a fail-closed cross-model grader."""
    import core.engine.core.config as cfg
    from core.engine.verification.grader import make_grader

    monkeypatch.setattr(cfg.settings, "cross_model_grader_host", "http://localhost:11434", raising=False)
    g = make_grader(allow_fallback=False)
    assert g._allow_fallback is False

# tests/verification/test_grader_cross_model.py
"""Phase 0 — make GraderAgent provider-injectable for cross-family grading.

The grader's score is the independent verification signal. Today it hard-spawns
the Claude CLI, so it can only grade with a Claude model — and a same-family judge
inflates scores ~15-20%. Injecting an alternate (non-Claude) provider lets the
grader produce a genuinely cross-family signal. Default (no provider) behaviour —
the isolated Claude CLI subprocess — is unchanged.
"""

import pytest

from core.engine.verification.grader import GraderAgent

_VALID = '{"criteria_results": [{"criterion": "c1", "status": "met", "reasoning": "ok"}]}'


@pytest.mark.asyncio
async def test_grader_uses_injected_provider():
    """When a provider is injected, the grader evaluates through it (not the CLI),
    passing the grader system prompt and the cross-model model name."""

    class _Provider:
        def __init__(self):
            self.calls = []

        async def complete(self, prompt, system=None, model=None, **kwargs):
            self.calls.append((system, model))
            return _VALID

    prov = _Provider()
    grader = GraderAgent(model="gemini-2.0-flash", provider=prov)
    out = await grader.evaluate("task", ["c1"], "artifact text")

    assert out["score"] == 1.0
    assert out["met_count"] == 1
    assert prov.calls, "expected the injected provider to be used"
    system, model = prov.calls[0]
    assert model == "gemini-2.0-flash"
    assert "grader" in (system or "").lower()


@pytest.mark.asyncio
async def test_grader_default_uses_subprocess_not_provider(monkeypatch):
    """No provider → the existing isolated subprocess path (`_run`) is used."""
    grader = GraderAgent()  # no provider
    called = {}

    async def _fake_run(prompt, timeout=90.0):
        called["run"] = True
        return _VALID

    monkeypatch.setattr(grader, "_run", _fake_run)
    out = await grader.evaluate("task", ["c1"], "art")

    assert called.get("run") is True
    assert out["score"] == 1.0


@pytest.mark.asyncio
async def test_grader_provider_error_returns_unclear_not_raise():
    """A provider failure is non-fatal — returns 'unclear' verdicts, never raises."""

    class _BoomProvider:
        async def complete(self, prompt, system=None, model=None, **kwargs):
            raise RuntimeError("provider down")

    grader = GraderAgent(model="gemini-2.0-flash", provider=_BoomProvider())
    out = await grader.evaluate("task", ["c1", "c2"], "art")

    assert out["score"] == 0.0
    assert out["total"] == 2
    assert all(r["status"] == "unclear" for r in out["criteria_results"])

import inspect

from core.engine.orchestrator.executor import _build_intel_context


def test_max_tokens_reduces_output():
    """_build_intel_context with small max_tokens produces shorter output than large."""
    snapshot = {
        "insights": [
            {
                "content": "a" * 500,
                "confidence": 0.9,
                "tier": "universal",
                "insight_type": "pattern",
                "id": f"insight:{i}",
                "source_graph": "specialty",
            }
            for i in range(20)
        ],
        "specialty_insights": [],
        "org_insights": [],
    }
    short_ctx = _build_intel_context(snapshot, max_tokens=50)
    long_ctx = _build_intel_context(snapshot, max_tokens=6000)
    assert len(short_ctx) < len(long_ctx)


def test_max_tokens_default_is_6000():
    """_build_intel_context has max_tokens parameter with default 6000."""
    sig = inspect.signature(_build_intel_context)
    param = sig.parameters.get("max_tokens")
    assert param is not None, "max_tokens parameter missing"
    assert param.default == 6000


def test_shell_composer_passes_max_tokens():
    """ShellComposer.compose() accepts max_tokens and passes it to _build_intel_context."""
    from unittest.mock import patch

    from core.engine.orchestration.shell import ShellComposer

    snapshot = {"insights": [], "specialty_insights": [], "org_insights": []}
    classification = {
        "archetype": "executor",
        "mode": "reactive",
        "discipline": "api_design",
        "specialties": [],
    }

    captured = {}

    def fake_build_intel_context(snap, max_tokens=6000):
        captured["max_tokens"] = max_tokens
        return ""

    with patch("core.engine.orchestrator.executor._build_intel_context", side_effect=fake_build_intel_context):
        composer = ShellComposer()
        composer.compose(classification, snapshot, "test task", max_tokens=400)

    assert captured.get("max_tokens") == 400

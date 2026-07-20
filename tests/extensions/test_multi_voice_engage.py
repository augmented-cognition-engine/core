"""Tests for multi-voice-engage — the in-recipe wrapper around execute_engagement.

Resolves the spec's open question: how does a recipe phase engage multiple
archetypes from inside the recipe? Answer: a bespoke instrument that
constructs an engagement-shaped classification and calls execute_engagement.
"""

import pytest


@pytest.mark.unit
async def test_multi_voice_engage_invokes_execute_engagement_with_archetypes(monkeypatch):
    """run() must call execute_engagement with perspectives = ['pm', 'skeptic', 'ux_designer']."""
    from extensions.reference.instruments import multi_voice_engage

    captured: dict = {}

    async def _fake_execute_engagement(task_description, classification, product_id, **kwargs):
        captured["task"] = task_description
        captured["perspectives"] = classification.get("engagement", {}).get("perspectives")
        captured["product_id"] = product_id

        # Return a minimal EngagementResult-shaped object the instrument can summarize
        class _R:
            merged_output = "PM: do it. Skeptic: but watch X. UX: nudge the migration."
            spins = []

        return _R()

    monkeypatch.setattr(multi_voice_engage, "execute_engagement", _fake_execute_engagement)

    result = await multi_voice_engage.run(
        thought="should we sunset the legacy importer?",
        product_id="product:platform",
    )
    assert captured["perspectives"] == ["pm", "skeptic", "ux_designer"]
    assert captured["task"] == "should we sunset the legacy importer?"
    assert captured["product_id"] == "product:platform"
    assert "PM:" in result["merged_output"]
    assert result["perspectives"] == ["pm", "skeptic", "ux_designer"]

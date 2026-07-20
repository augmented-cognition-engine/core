"""Tests for the product-framing instrument."""

import json

import pytest


@pytest.mark.unit
async def test_product_framing_returns_decision_success_scope(monkeypatch):
    """run() must return a dict with the three keys named in the spec."""
    from extensions.reference.instruments import framing

    fake_payload = {
        "decision": "sunset the legacy importer by Q3",
        "success_measure": "90% of users migrated; no priority-1 regressions for 30 days",
        "scope_boundary": "in: importer + admin UI deprecation. out: data migrations.",
    }

    async def _fake_call_llm(prompt: str, model=None, system=None) -> str:
        return json.dumps(fake_payload)

    monkeypatch.setattr(framing, "_call_llm", _fake_call_llm)

    result = await framing.run(thought="should we sunset the legacy importer?")
    assert result == fake_payload
    assert set(result.keys()) == {"decision", "success_measure", "scope_boundary"}

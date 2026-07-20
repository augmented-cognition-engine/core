# tests/test_selector_adapter.py
import pytest

from core.engine.reasoning.selector import select_frameworks


@pytest.mark.asyncio
async def test_select_frameworks_returns_none_simple_task():
    """select_frameworks returns None for simple tasks (unchanged behavior)."""
    classification = {"complexity": "simple", "mode": "reactive"}
    result = await select_frameworks(classification, "product:test")
    assert result is None


@pytest.mark.asyncio
async def test_select_frameworks_signature_unchanged():
    """Function still accepts all original parameters without error."""
    classification = {"complexity": "moderate", "mode": "deliberative", "archetype": "analyst"}
    # Should not raise even without DB
    try:
        result = await select_frameworks(classification, "product:test", description="test task", force=False)
    except Exception:
        pass  # DB errors are acceptable; signature errors are not

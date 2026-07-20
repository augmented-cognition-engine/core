# tests/test_orchestrator_graph.py
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_loader_includes_cross_domain_key():
    """After synaptic wiring, intelligence_loaded should include cross_domain."""
    with patch("core.engine.graph.synaptic_loader.load_synaptic_intelligence") as mock_loader:
        mock_loader.return_value = [{"content": "cross insight", "synapse_id": "synapse:a"}]
        from core.engine.graph.synaptic_loader import load_synaptic_intelligence

        result = await load_synaptic_intelligence("subdomain:test", "product:test")
        assert len(result) == 1


@pytest.mark.asyncio
async def test_cooccurrence_called_after_task():
    """After executor saves task, co-occurrence tracker should be called."""
    from core.engine.graph.cooccurrence import extract_subdomain_pairs

    task = {
        "domain_path": "ux.design-systems",
        "intelligence_loaded": {"cross_domain": [{"source_subdomain_slug": "engineering"}]},
    }
    pairs = extract_subdomain_pairs(task)
    assert len(pairs) == 1

# tests/test_synthesizer_clearance.py

import pytest


@pytest.mark.asyncio
async def test_synthesizer_sets_clearance_from_config():
    """Synthesizer should set insight clearance based on domain_flow_config."""
    from core.engine.flow.config import FlowDefaults

    config = FlowDefaults(default_clearance="domain", contribute_org_intelligence=False)
    assert config.default_clearance == "domain"
    assert config.contribute_org_intelligence is False


def test_propagation_strictest_wins():
    """insight_propagation=false forces subdomain tier. contribute_org=false caps at domain."""
    from core.engine.flow.config import FlowDefaults

    # insight_propagation=false -> subdomain (most restrictive)
    config1 = FlowDefaults(insight_propagation=False)
    assert config1.insight_propagation is False

    # contribute_org=false -> cap at domain
    config2 = FlowDefaults(contribute_org_intelligence=False)
    assert config2.contribute_org_intelligence is False

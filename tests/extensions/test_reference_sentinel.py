"""The reference (product) extension registers a worked sentinel example."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_extensions


@pytest.mark.integration
def test_product_extension_registers_heartbeat_sentinel():
    from core.engine.extensions.loader import ensure_loaded
    from core.engine.sentinel.registry import get_engine

    ensure_loaded()
    entry = get_engine("product_heartbeat")
    assert entry is not None
    assert entry["cron"] == "0 6 * * *"

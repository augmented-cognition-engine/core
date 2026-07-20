"""Tests for partner_panel_enabled feature flag."""

from __future__ import annotations

import pytest

from core.engine.core.db import pool
from core.engine.voice.feature_flag import (
    is_partner_panel_enabled,
    set_partner_panel_enabled,
)

pytestmark = pytest.mark.usefixtures("db_pool")


@pytest.mark.asyncio
async def test_default_off():
    assert await is_partner_panel_enabled(pool, "product:test_default_off") is False


@pytest.mark.asyncio
async def test_set_then_get():
    pid = "product:test_set_then_get"
    await set_partner_panel_enabled(pool, pid, True)
    assert await is_partner_panel_enabled(pool, pid) is True
    await set_partner_panel_enabled(pool, pid, False)
    assert await is_partner_panel_enabled(pool, pid) is False

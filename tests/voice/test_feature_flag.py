import pytest


@pytest.mark.asyncio
async def test_voice_continuity_enabled_default_false(db_pool):
    from core.engine.voice.feature_flag import is_voice_continuity_enabled

    assert await is_voice_continuity_enabled(db_pool, "product:platform") is False


@pytest.mark.asyncio
async def test_voice_continuity_round_trip(db_pool):
    from core.engine.voice.feature_flag import (
        is_voice_continuity_enabled,
        set_voice_continuity_enabled,
    )

    pid = "product:platform"
    await set_voice_continuity_enabled(db_pool, pid, True)
    try:
        assert await is_voice_continuity_enabled(db_pool, pid) is True
    finally:
        await set_voice_continuity_enabled(db_pool, pid, False)
    assert await is_voice_continuity_enabled(db_pool, pid) is False

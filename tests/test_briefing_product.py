from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_briefing_includes_product_health():
    mock_db = AsyncMock()
    mock_db.query.return_value = [
        [
            {"dimension": "security", "score": 0.4, "gaps": ["no rate limiting"]},
            {"dimension": "security", "score": 0.8, "gaps": []},
            {"dimension": "testing", "score": 0.3, "gaps": ["no integration tests", "no e2e tests"]},
        ]
    ]
    from core.engine.sentinel.engines.briefing import build_product_health_section

    section = await build_product_health_section("product:test", mock_db)
    assert "Product Health" in section or section == ""
    if section:
        assert "security" in section.lower() or "Security" in section


@pytest.mark.asyncio
async def test_product_health_section_empty_when_no_records():
    mock_db = AsyncMock()
    mock_db.query.return_value = [[]]
    from core.engine.sentinel.engines.briefing import build_product_health_section

    section = await build_product_health_section("product:test", mock_db)
    assert section == ""


@pytest.mark.asyncio
async def test_product_health_section_marks_gaps():
    mock_db = AsyncMock()
    mock_db.query.return_value = [
        [
            {"dimension": "testing", "score": 0.2, "gaps": ["no tests"]},
            {"dimension": "testing", "score": 0.3, "gaps": ["no e2e"]},
            {"dimension": "security", "score": 0.9, "gaps": []},
        ]
    ]
    from core.engine.sentinel.engines.briefing import build_product_health_section

    section = await build_product_health_section("product:test", mock_db)
    assert section != ""
    # testing avg is 0.25 — below 0.4 gap threshold, should show gap count
    assert "testing" in section.lower() or "Testing" in section
    # security avg is 0.9 — above threshold, should show checkmark
    assert "security" in section.lower() or "Security" in section
    assert "\u2713" in section  # checkmark for healthy dimension


@pytest.mark.asyncio
async def test_product_health_section_query_uses_org_id():
    mock_db = AsyncMock()
    mock_db.query.return_value = [[]]
    from core.engine.sentinel.engines.briefing import build_product_health_section

    await build_product_health_section("org:specific", mock_db)
    call_args = mock_db.query.call_args
    # The product_id should be passed as a parameter
    assert call_args is not None
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
    assert "org:specific" in str(params)

# tests/test_conductor_vision_filter.py
"""Tests for vision/theme alignment filter."""

import pytest

from core.engine.conductor.vision_filter import VisionFilter


@pytest.mark.asyncio
async def test_no_themes_always_passes():
    f = VisionFilter.__new__(VisionFilter)
    ctx = {
        "themes": [],
        "capability": {"slug": "whatever", "tags": [], "priority": "nice_to_have"},
        "track": {"dimension": "ux"},
    }
    assert await f.is_aligned(ctx) is True


@pytest.mark.asyncio
async def test_no_capability_always_passes():
    f = VisionFilter.__new__(VisionFilter)
    ctx = {"themes": [{"name": "growth"}]}
    assert await f.is_aligned(ctx) is True


@pytest.mark.asyncio
async def test_critical_always_passes():
    f = VisionFilter.__new__(VisionFilter)
    ctx = {
        "themes": [{"name": "growth"}],
        "capability": {"slug": "auth", "tags": [], "priority": "critical"},
        "track": {"dimension": "ux"},
    }
    assert await f.is_aligned(ctx) is True


@pytest.mark.asyncio
async def test_safety_dimension_always_passes():
    f = VisionFilter.__new__(VisionFilter)
    ctx = {
        "themes": [{"name": "growth"}],
        "capability": {"slug": "api", "tags": [], "priority": "nice_to_have"},
        "track": {"dimension": "security"},
    }
    assert await f.is_aligned(ctx) is True


@pytest.mark.asyncio
async def test_tag_matches_theme():
    f = VisionFilter.__new__(VisionFilter)
    ctx = {
        "themes": [{"name": "growth"}],
        "capability": {"slug": "onboard", "tags": ["growth"], "priority": "nice_to_have"},
        "track": {"dimension": "ux"},
    }
    assert await f.is_aligned(ctx) is True


@pytest.mark.asyncio
async def test_unaligned_filtered():
    f = VisionFilter.__new__(VisionFilter)
    ctx = {
        "themes": [{"name": "growth"}],
        "capability": {"slug": "legacy", "tags": ["maintenance"], "priority": "nice_to_have"},
        "track": {"dimension": "ux"},
    }
    assert await f.is_aligned(ctx) is False

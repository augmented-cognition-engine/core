# tests/test_cognition_classifier.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.cognition.classifier import FrameworkClassifier
from core.engine.cognition.models import InstrumentSpec


@pytest.fixture
def classifier():
    return FrameworkClassifier()


@pytest.mark.asyncio
async def test_resolve_returns_fallback_when_no_db_rows(classifier):
    spec = InstrumentSpec(slug=None, family_hint="diagnostic", fallback_slug="first-principles")
    with patch("core.engine.cognition.classifier.pool") as mock_pool:
        mock_db = MagicMock()
        mock_db.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await classifier.resolve_instrument(spec, "code", "architecture", "product:test")
    assert result == "first-principles"


@pytest.mark.asyncio
async def test_resolve_returns_explicit_slug_directly(classifier):
    spec = InstrumentSpec(slug="constraint-theory", fallback_slug="first-principles")
    # No DB call needed for explicit slug
    result = await classifier.resolve_instrument(spec, "code", "architecture", "product:test")
    assert result == "constraint-theory"


@pytest.mark.asyncio
async def test_resolve_uses_learned_when_enough_samples(classifier):
    spec = InstrumentSpec(slug=None, family_hint="diagnostic", fallback_slug="first-principles")
    learned_rows = [
        {"framework_slug": "constraint-theory", "avg_score": 0.9, "sample_count": 25},
    ]
    with patch("core.engine.cognition.classifier.pool") as mock_pool:
        mock_db = MagicMock()
        mock_db.query = AsyncMock(return_value=[learned_rows])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await classifier.resolve_instrument(spec, "code", "architecture", "product:test")
    assert result == "constraint-theory"


def test_blend_weight_cold_start(classifier):
    assert classifier._blend_weight(0) == 0.0
    assert classifier._blend_weight(4) == 0.0


def test_blend_weight_warm(classifier):
    weight = classifier._blend_weight(10)
    assert 0.6 < weight < 0.8  # 70% learned at 10 samples


def test_blend_weight_mature(classifier):
    weight = classifier._blend_weight(25)
    assert weight == pytest.approx(0.9)

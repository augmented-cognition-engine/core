from core.engine.product.models import PHASES, PRODUCT_SCALES, PRODUCT_TYPES


def test_product_types():
    assert "ai_native" in PRODUCT_TYPES
    assert "trading_system" in PRODUCT_TYPES
    assert "mobile_consumer_app" in PRODUCT_TYPES
    assert "internal_tool" in PRODUCT_TYPES
    assert len(PRODUCT_TYPES) >= 9


def test_product_scales():
    assert PRODUCT_SCALES == ["atomic", "component", "application", "platform", "enterprise"]


def test_phases():
    assert PHASES == ["discovery", "poc", "alpha", "beta", "ga", "mature"]

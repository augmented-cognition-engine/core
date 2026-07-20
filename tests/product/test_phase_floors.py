from core.engine.product.phase_floors import (
    DEFAULT_PILLAR_FLOORS,
    effective_floor,
)
from core.engine.product.pillars import Pillar


def test_default_floors_complete():
    for pillar in Pillar:
        for phase in ["discovery", "poc", "alpha", "beta", "ga", "mature"]:
            assert (pillar, phase) in DEFAULT_PILLAR_FLOORS
            assert 0.0 <= DEFAULT_PILLAR_FLOORS[(pillar, phase)] <= 1.0


def test_default_floor_for_experience_at_poc():
    assert DEFAULT_PILLAR_FLOORS[(Pillar.EXPERIENCE, "poc")] == 0.55


def test_effective_floor_no_modifiers():
    floor = effective_floor(
        pillar=Pillar.EXPERIENCE,
        phase="poc",
        product_type="default",
        scale="application",
    )
    assert floor == 0.55


def test_effective_floor_with_ai_native_type():
    floor = effective_floor(
        pillar=Pillar.EXPERIENCE,
        phase="poc",
        product_type="ai_native",
        scale="application",
    )
    assert abs(floor - 0.70) < 0.001


def test_effective_floor_atomic_scale_excludes_operations():
    floor = effective_floor(
        pillar=Pillar.OPERATIONS,
        phase="poc",
        product_type="default",
        scale="atomic",
    )
    assert floor == 0.0


def test_effective_floor_enterprise_clipped_to_one():
    floor = effective_floor(
        pillar=Pillar.TRUST,
        phase="ga",
        product_type="trading_system",
        scale="enterprise",
    )
    assert floor == 1.0

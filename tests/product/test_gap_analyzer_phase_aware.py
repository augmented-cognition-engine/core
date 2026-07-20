from core.engine.product.phase_floors import effective_floor
from core.engine.product.pillars import Pillar
from core.engine.sentinel.engines.gap_analyzer import phase_aware_gap_severity


def test_gap_severity_zero_when_at_floor():
    floor = effective_floor(Pillar.OPERATIONS, "poc", "default", "application")
    sev = phase_aware_gap_severity(score=floor, floor=floor)
    assert sev == 0.0


def test_gap_severity_positive_when_below_floor():
    floor = effective_floor(Pillar.EXPERIENCE, "poc", "ai_native", "application")
    sev = phase_aware_gap_severity(score=0.4, floor=floor)
    assert abs(sev - 0.3 / 0.7) < 0.001


def test_gap_severity_zero_when_above_floor():
    floor = effective_floor(Pillar.EXPERIENCE, "poc", "default", "application")
    sev = phase_aware_gap_severity(score=0.8, floor=floor)
    assert sev == 0.0


def test_gap_severity_handles_zero_floor():
    sev = phase_aware_gap_severity(score=0.0, floor=0.0)
    assert sev == 0.0

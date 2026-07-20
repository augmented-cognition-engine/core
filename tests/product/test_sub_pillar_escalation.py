from core.engine.product.sub_pillar_escalation import (
    DisciplineSignal,
    escalate_critical_disciplines,
)


def test_no_escalation_below_threshold():
    sigs = [
        DisciplineSignal(pillar="experience", discipline="ux", score=0.5, floor=0.7),
    ]
    escalated = escalate_critical_disciplines(sigs)
    assert escalated == []


def test_escalation_above_threshold():
    sigs = [
        DisciplineSignal(pillar="experience", discipline="aix", score=0.0, floor=0.7),
    ]
    escalated = escalate_critical_disciplines(sigs)
    assert len(escalated) == 1
    assert escalated[0].discipline == "aix"


def test_only_critical_discipline_escalates():
    sigs = [
        DisciplineSignal(pillar="experience", discipline="ux", score=0.5, floor=0.7),
        DisciplineSignal(pillar="experience", discipline="aix", score=0.0, floor=0.7),
    ]
    escalated = escalate_critical_disciplines(sigs)
    assert len(escalated) == 1
    assert escalated[0].discipline == "aix"

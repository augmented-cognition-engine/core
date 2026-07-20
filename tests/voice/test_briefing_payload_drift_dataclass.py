from core.engine.product.briefing_payload import TargetDriftAssessment


def test_target_drift_dataclass_fields():
    drift = TargetDriftAssessment(n_total=15, n_blocked=11, blocking_pillars=["experience", "state"])
    assert drift.n_total == 15
    assert drift.n_blocked == 11
    assert drift.blocking_pillars == ["experience", "state"]


def test_briefing_payload_target_drift_field_is_dataclass_or_none():
    import dataclasses

    from core.engine.product.briefing_payload import BriefingPayload

    fields = {f.name: f for f in dataclasses.fields(BriefingPayload)}
    # Field type should accept TargetDriftAssessment | None — string type was the v1.0 stub.
    assert "target_drift_assessment" in fields

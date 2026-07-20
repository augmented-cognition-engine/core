import pytest

from core.engine.product.models import (
    CapabilityCreate,
    CapabilityProposal,
    QualityAssessment,
    QuestionCreate,
    ThemeCreate,
    VisionCreate,
)


def test_capability_create_valid():
    c = CapabilityCreate(name="Authentication", slug="auth", description="User auth system")
    assert c.slug == "auth"
    assert c.status == "built"


def test_capability_create_invalid_status():
    with pytest.raises(ValueError):
        CapabilityCreate(name="X", slug="x", description="X", status="invalid")


def test_capability_proposal_has_confidence():
    p = CapabilityProposal(
        name="Auth",
        slug="auth",
        description="Auth system",
        file_glob="engine/auth/**",
        file_ids=["graph_file:abc"],
        confidence=0.8,
    )
    assert 0.0 <= p.confidence <= 1.0


def test_vision_create():
    v = VisionCreate(
        name="Autonomous PM for builder teams",
        description="AI that acts as PM for small teams",
    )
    assert v.active is True


def test_vision_create_minimal():
    v = VisionCreate(name="Ship fast")
    assert v.description == ""
    assert v.active is True


def test_theme_create():
    t = ThemeCreate(name="GTM Strategy")
    assert t.status == "active"
    assert t.description == ""


def test_theme_create_with_description():
    t = ThemeCreate(name="Enterprise Readiness", description="Security + compliance hardening")
    assert t.name == "Enterprise Readiness"


def test_quality_assessment_score_bounds():
    q = QualityAssessment(dimension="security", score=0.6, gaps=["no rate limiting"])
    assert q.score == 0.6
    with pytest.raises(ValueError):
        QualityAssessment(dimension="security", score=1.5)


def test_question_create_valid_category():
    q = QuestionCreate(
        question="Does auth have rate limiting?",
        category="downward",
        source="gap_analyzer",
        priority="high",
    )
    assert q.status == "open"

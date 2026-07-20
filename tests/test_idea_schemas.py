# tests/test_idea_schemas.py
import pytest
from pydantic import ValidationError


def test_idea_classification_valid():
    from core.engine.ideas.schemas import IdeaClassification

    c = IdeaClassification(
        domain_path="architecture",
        type="feature",
        complexity="moderate",
        title="Multi-brand token architecture",
        summary="A system to support multiple brand themes in one token set.",
    )
    assert c.domain_path == "architecture"
    assert c.type == "feature"
    assert c.complexity == "moderate"


def test_idea_classification_rejects_invalid_type():
    from core.engine.ideas.schemas import IdeaClassification

    with pytest.raises(ValidationError):
        IdeaClassification(
            domain_path="tech",
            type="invalid_type",
            complexity="simple",
            title="x",
            summary="x",
        )


def test_idea_classification_rejects_invalid_complexity():
    from core.engine.ideas.schemas import IdeaClassification

    with pytest.raises(ValidationError):
        IdeaClassification(
            domain_path="tech",
            type="feature",
            complexity="insane",
            title="x",
            summary="x",
        )


def test_qualification_result_ready():
    from core.engine.ideas.schemas import QualificationResult

    r = QualificationResult(status="ready", questions=[])
    assert r.status == "ready"
    assert r.questions == []


def test_qualification_result_needs_questions():
    from core.engine.ideas.schemas import QualificationResult

    r = QualificationResult(status="needs_questions", questions=["For how many brands?", "Which brands?"])
    assert len(r.questions) == 2


def test_qualification_result_rejects_more_than_2_questions():
    from core.engine.ideas.schemas import QualificationResult

    with pytest.raises(ValidationError):
        QualificationResult(status="needs_questions", questions=["Q1?", "Q2?", "Q3?"])


def test_incubation_brief_valid():
    from core.engine.ideas.schemas import IncubationBrief

    brief = IncubationBrief(
        what="A multi-brand token system",
        why="Support Acme, Bolt, Crest from one codebase",
        what_we_know="Token pipeline exists, single-brand only",
        open_questions=["How to handle brand-specific overrides?"],
        approach="Phase 1: schema, Phase 2: generator, Phase 3: integration",
        effort="2-3 weeks",
        risks=["Performance overhead per brand"],
        first_step="Audit current token schema for extension points",
    )
    assert brief.what == "A multi-brand token system"
    assert len(brief.risks) == 1


def test_idea_connection_valid():
    from core.engine.ideas.schemas import IdeaConnection

    conn = IdeaConnection(
        insight_id="insight:abc123",
        content_preview="Token naming uses kebab-case",
        relevance="direct",
    )
    assert conn.relevance == "direct"


def test_idea_connection_rejects_invalid_relevance():
    from core.engine.ideas.schemas import IdeaConnection

    with pytest.raises(ValidationError):
        IdeaConnection(
            insight_id="insight:abc",
            content_preview="x",
            relevance="vague",
        )


def test_schemas_produce_json_schema():
    from core.engine.ideas.schemas import IdeaClassification, IncubationBrief, QualificationResult

    assert IdeaClassification.model_json_schema()["type"] == "object"
    assert IncubationBrief.model_json_schema()["type"] == "object"
    assert QualificationResult.model_json_schema()["type"] == "object"

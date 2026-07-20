# tests/test_skill_models.py
from core.engine.skills.models import Job, Skill, SkillMatch


def test_job_defaults():
    job = Job(name="analyze", archetype="analyst", mode="deliberative")
    assert job.frameworks == []
    assert job.output_format == "prose"
    assert job.description == ""


def test_skill_with_jobs():
    skill = Skill(
        slug="deep-research",
        name="Deep Research",
        description="Multi-step research skill",
        jobs=[
            Job(name="gather", archetype="researcher", mode="exploratory"),
            Job(name="analyze", archetype="analyst", mode="deliberative"),
        ],
        activation_signals=["research", "investigate", "deep dive"],
    )
    assert len(skill.jobs) == 2
    assert skill.tier == "built-in"
    assert skill.domain_path is None


def test_skill_match():
    skill = Skill(
        slug="test",
        name="Test",
        description="test",
        jobs=[Job(name="s1", archetype="executor", mode="reactive")],
    )
    match = SkillMatch(skill=skill, score=0.75, matched_signals=["research", "deep"])
    assert match.score == 0.75
    assert len(match.matched_signals) == 2


def test_skill_json_roundtrip():
    skill = Skill(
        slug="test-rt",
        name="Roundtrip",
        description="JSON test",
        domain_path="architecture",
        tier="custom",
        jobs=[
            Job(name="job1", archetype="creator", mode="deliberative", frameworks=["mece"]),
        ],
        activation_signals=["create", "build"],
    )
    data = skill.model_dump()
    restored = Skill(**data)
    assert restored.slug == "test-rt"
    assert restored.jobs[0].frameworks == ["mece"]

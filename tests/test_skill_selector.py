# tests/test_skill_selector.py
from core.engine.skills.models import Job, Skill
from core.engine.skills.selector import MATCH_THRESHOLD, _tokenize, score_skill


def _make_skill(slug="test", signals=None, domain_path=None):
    return Skill(
        slug=slug,
        name="Test Skill",
        description="test",
        domain_path=domain_path,
        jobs=[Job(name="s1", archetype="executor", mode="reactive")],
        activation_signals=signals or [],
    )


def test_tokenize():
    tokens = _tokenize("Deep Research on React Components")
    assert "deep" in tokens
    assert "research" in tokens
    assert "react" in tokens
    assert "components" in tokens
    assert "on" in tokens  # tokenizer doesn't strip stopwords (selector is keyword overlap)


def test_score_skill_matches_signals():
    skill = _make_skill(signals=["research", "investigate", "deep dive"])
    tokens = _tokenize("I need to research this topic deeply")
    match = score_skill(skill, tokens, "architecture")
    assert match is not None
    assert match.score > 0
    assert "research" in match.matched_signals


def test_score_skill_no_match():
    skill = _make_skill(signals=["deploy", "kubernetes", "infrastructure"])
    tokens = _tokenize("Write a React component")
    match = score_skill(skill, tokens, "architecture")
    assert match is None


def test_score_skill_domain_bonus():
    skill = _make_skill(signals=["research", "analyze"], domain_path="architecture")
    tokens = _tokenize("research this architecture topic")
    # discipline is now a flat string — exact match against skill.domain_path
    match = score_skill(skill, tokens, "architecture")
    assert match is not None
    # Should have discipline bonus: 2/2 signals (score=1.0) + 0.2 → capped at 1.0
    assert match.score > 0.5


def test_score_skill_below_threshold():
    skill = _make_skill(signals=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"])
    tokens = _tokenize("only matches a")
    match = score_skill(skill, tokens, "architecture")
    # 1/10 = 0.1 < 0.3 threshold
    assert match is None


def test_score_skill_empty_signals():
    skill = _make_skill(signals=[])
    tokens = _tokenize("anything")
    match = score_skill(skill, tokens, "architecture")
    assert match is None


def test_threshold_value():
    assert MATCH_THRESHOLD == 0.3

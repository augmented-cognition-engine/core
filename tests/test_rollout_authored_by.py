"""Tests for _assign_branch_authorship — rollout branches get distinct authoring archetypes."""

from core.engine.foresight.models import RolloutBranch
from core.engine.foresight.planner import _assign_branch_authorship


def _mkbr(score: float, risk: str, override: dict | None = None) -> RolloutBranch:
    return RolloutBranch(path=["decision:x"], terminal_score=score, top_risk=risk, state_override=override or {})


def test_distinct_authors_for_three_branches():
    branches = [
        _mkbr(0.9, "minor risk", {"capability:a": 0.6}),
        _mkbr(0.7, "this is a much longer risk statement describing many problems", {"capability:a": 0.8}),
        _mkbr(0.8, "ok", {"capability:a": 0.52}),
    ]
    _assign_branch_authorship(branches)
    authors = [b.authored_by_archetype for b in branches]
    assert len(set(authors)) == 3
    # The highest terminal_score branch (0.9) is PM
    assert branches[0].authored_by_archetype == "pm"
    # The longest-risk branch is skeptic
    assert branches[1].authored_by_archetype == "skeptic"
    # The most-incremental (0.52 close to 0.5) is technical_architect
    assert branches[2].authored_by_archetype == "technical_architect"


def test_empty_branches_no_op():
    branches: list[RolloutBranch] = []
    _assign_branch_authorship(branches)
    assert branches == []


def test_single_branch_gets_pm():
    branches = [_mkbr(0.5, "x")]
    _assign_branch_authorship(branches)
    assert branches[0].authored_by_archetype == "pm"


def test_two_branches_get_distinct_pm_and_skeptic():
    branches = [_mkbr(0.5, "x"), _mkbr(0.8, "longer risk")]
    _assign_branch_authorship(branches)
    archetypes = {b.authored_by_archetype for b in branches}
    assert "pm" in archetypes
    assert "skeptic" in archetypes


def test_default_authored_by_is_empty_string():
    """RolloutBranch defaults authored_by_archetype to empty string when not assigned."""
    b = _mkbr(0.5, "x")
    assert b.authored_by_archetype == ""

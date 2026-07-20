# tests/test_review_judge.py
"""Tests for the Judge agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.review.judge import Judge
from core.engine.review.models import ReviewFinding, ReviewPass, ReviewSynthesis


def _make_passes() -> list[ReviewPass]:
    return [
        ReviewPass(
            discipline="security",
            findings=[
                ReviewFinding(
                    file="auth.py",
                    line=12,
                    message="Missing input validation on token",
                    severity="high",
                    discipline="security",
                    confidence=0.9,
                ),
                ReviewFinding(
                    file="auth.py",
                    line=30,
                    message="Hardcoded secret key",
                    severity="critical",
                    discipline="security",
                    confidence=0.95,
                ),
            ],
            pass_summary="2 security issues found",
        ),
        ReviewPass(
            discipline="architecture",
            findings=[
                ReviewFinding(
                    file="auth.py",
                    line=12,
                    message="Token validation should use shared utility",
                    severity="medium",
                    discipline="architecture",
                    confidence=0.7,
                ),
                ReviewFinding(
                    file="api.py",
                    line=5,
                    message="Missing error boundary",
                    severity="medium",
                    discipline="architecture",
                    confidence=0.6,
                ),
            ],
            pass_summary="2 architecture suggestions",
        ),
        ReviewPass(
            discipline="testing",
            findings=[
                ReviewFinding(
                    file="auth.py",
                    line=12,
                    message="No test coverage for token edge cases",
                    severity="medium",
                    discipline="testing",
                    confidence=0.85,
                ),
            ],
            pass_summary="1 testing gap",
        ),
    ]


def test_judge_deduplicates_same_file_line():
    judge = Judge()
    all_findings = [f for p in _make_passes() for f in p.findings]
    groups = judge.group_findings(all_findings)
    key = ("auth.py", 12)
    assert key in groups
    assert len(groups[key]) == 3  # security + architecture + testing on same line


def test_judge_scores_disciplines():
    judge = Judge()
    scores = judge.score_disciplines(_make_passes())
    assert scores["security"] < scores["testing"]  # critical finding penalises more
    assert 0.0 <= scores["security"] <= 1.0


@pytest.mark.asyncio
async def test_judge_synthesize_returns_result():
    judge = Judge()
    mock_verdicts = [
        {"finding_index": 0, "action": "keep"},
        {"finding_index": 1, "action": "keep"},
        {"finding_index": 2, "action": "merge", "merged_with": 0},
        {"finding_index": 3, "action": "keep"},
        {"finding_index": 4, "action": "keep"},
    ]
    with patch.object(judge, "_llm_judge", new_callable=AsyncMock, return_value=mock_verdicts):
        result = await judge.synthesize(_make_passes())
    assert isinstance(result, ReviewSynthesis)
    assert result.findings_before_judge == 5
    assert result.findings_after_judge == 4  # 1 merged
    assert result.passes_run == 3


def test_judge_quality_gate_fails_on_critical():
    judge = Judge()
    findings = [
        ReviewFinding(
            file="auth.py",
            line=30,
            message="Hardcoded secret",
            severity="critical",
            discipline="security",
        )
    ]
    gate = judge.check_quality_gate(findings)
    assert gate.pass_quality_gate is False
    assert any("critical" in f.lower() for f in gate.gate_failures)


def test_judge_quality_gate_passes_on_medium():
    judge = Judge()
    findings = [
        ReviewFinding(
            file="auth.py",
            line=12,
            message="Consider refactoring",
            severity="medium",
            discipline="architecture",
        )
    ]
    gate = judge.check_quality_gate(findings)
    assert gate.pass_quality_gate is True


# ------------------------------------------------------------------
# Additional coverage
# ------------------------------------------------------------------


def test_group_findings_multiple_locations():
    judge = Judge()
    findings = [
        ReviewFinding(file="a.py", line=1, message="issue A", severity="high", discipline="security"),
        ReviewFinding(file="a.py", line=1, message="issue B", severity="medium", discipline="testing"),
        ReviewFinding(file="b.py", line=5, message="issue C", severity="low", discipline="architecture"),
    ]
    groups = judge.group_findings(findings)
    assert len(groups[("a.py", 1)]) == 2
    assert len(groups[("b.py", 5)]) == 1


def test_score_disciplines_clamps_to_zero():
    judge = Judge()
    # Many criticals should clamp to 0.0
    passes = [
        ReviewPass(
            discipline="security",
            findings=[
                ReviewFinding(file="x.py", line=i, message="crit", severity="critical", discipline="security")
                for i in range(10)
            ],
        )
    ]
    scores = judge.score_disciplines(passes)
    assert scores["security"] == 0.0


def test_score_disciplines_empty_pass():
    judge = Judge()
    passes = [ReviewPass(discipline="testing", findings=[])]
    scores = judge.score_disciplines(passes)
    assert scores["testing"] == 1.0


@pytest.mark.asyncio
async def test_synthesize_no_findings_returns_clean():
    judge = Judge()
    passes = [ReviewPass(discipline="security", findings=[], pass_summary="all clear")]
    result = await judge.synthesize(passes)
    assert result.pass_quality_gate is True
    assert result.findings_after_judge == 0
    assert result.findings_before_judge == 0
    assert result.passes_run == 1


@pytest.mark.asyncio
async def test_synthesize_sorts_critical_first():
    judge = Judge()
    passes = [
        ReviewPass(
            discipline="security",
            findings=[
                ReviewFinding(file="a.py", line=1, message="low issue", severity="low", discipline="security"),
                ReviewFinding(
                    file="a.py", line=2, message="critical issue", severity="critical", discipline="security"
                ),
                ReviewFinding(file="a.py", line=3, message="high issue", severity="high", discipline="security"),
            ],
        )
    ]
    mock_verdicts = [{"finding_index": i, "action": "keep"} for i in range(3)]
    with patch.object(judge, "_llm_judge", new_callable=AsyncMock, return_value=mock_verdicts):
        result = await judge.synthesize(passes)
    assert result.findings[0].severity == "critical"
    assert result.findings[1].severity == "high"
    assert result.findings[2].severity == "low"


def test_parse_verdicts_valid_json():
    judge = Judge()
    raw = '[{"finding_index": 0, "action": "keep"}, {"finding_index": 1, "action": "discard"}]'
    verdicts = judge._parse_verdicts(raw)
    assert len(verdicts) == 2
    assert verdicts[0]["action"] == "keep"


def test_parse_verdicts_strips_markdown():
    judge = Judge()
    raw = '```json\n[{"finding_index": 0, "action": "keep"}]\n```'
    verdicts = judge._parse_verdicts(raw)
    assert len(verdicts) == 1


def test_parse_verdicts_invalid_returns_empty():
    judge = Judge()
    verdicts = judge._parse_verdicts("not valid json at all ~~")
    assert verdicts == []


@pytest.mark.asyncio
async def test_llm_judge_skips_llm_for_two_or_fewer():
    judge = Judge()
    findings = [
        ReviewFinding(file="a.py", line=1, message="issue", severity="high", discipline="security"),
        ReviewFinding(file="a.py", line=2, message="issue2", severity="low", discipline="security"),
    ]
    with patch("core.engine.review.judge.llm") as mock_llm:
        result = await judge._llm_judge(findings)
    mock_llm.complete.assert_not_called()
    assert all(v["action"] == "keep" for v in result)


def test_build_summary_includes_counts():
    judge = Judge()
    findings = [
        ReviewFinding(file="a.py", line=1, message="crit", severity="critical", discipline="security"),
        ReviewFinding(file="b.py", line=2, message="med", severity="medium", discipline="architecture"),
    ]
    passes = [
        ReviewPass(discipline="security", findings=[]),
        ReviewPass(discipline="architecture", findings=[]),
    ]
    summary = judge._build_summary(findings, passes)
    assert "critical" in summary
    assert "medium" in summary
    assert "security" in summary
    assert "architecture" in summary


def test_quality_gate_fails_on_too_many_high():
    judge = Judge()
    findings = [
        ReviewFinding(file="a.py", line=i, message="high issue", severity="high", discipline="security")
        for i in range(5)
    ]
    gate = judge.check_quality_gate(findings, high_threshold=3)
    assert gate.pass_quality_gate is False
    assert any("high" in f.lower() for f in gate.gate_failures)

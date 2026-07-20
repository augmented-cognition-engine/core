# tests/test_discovery_sprint.py
"""Tests for P4 Component 1 — Discovery Sprint Packager.

TDD order:
1. Report data models (DiscoveryReport, AutomationCandidate, SpecStub)
2. Report generator (markdown + JSON export)
3. DiscoverySprintPackager.generate() — full pipeline
4. Exec summary plain-language gate (no jargon)
5. ROI calculation
6. Fallback when synthesizer output absent
"""

from __future__ import annotations

import json

import pytest

# ── SpecStub model tests ──────────────────────────────────────────────────────


def test_spec_stub_has_required_fields():
    """SpecStub has title, acceptance_criteria, and estimated_scope."""
    from core.engine.product.report_models import SpecStub

    stub = SpecStub(
        title="Implement JWT authentication middleware",
        acceptance_criteria=[
            "All API endpoints return 401 for unauthenticated requests",
            "JWT tokens are validated on every request",
        ],
        estimated_scope="medium",
    )
    assert stub.title == "Implement JWT authentication middleware"
    assert len(stub.acceptance_criteria) == 2
    assert stub.estimated_scope == "medium"


def test_spec_stub_scope_must_be_valid():
    """SpecStub estimated_scope must be low, medium, or high."""
    from core.engine.product.report_models import SpecStub

    with pytest.raises(ValueError, match="estimated_scope"):
        SpecStub(
            title="Test",
            acceptance_criteria=["criterion"],
            estimated_scope="huge",
        )


def test_spec_stub_to_dict_is_ace_create_spec_compatible():
    """SpecStub.to_dict() produces a dict directly passable to ace_create_spec."""
    from core.engine.product.report_models import SpecStub

    stub = SpecStub(
        title="Add circuit breaker to service calls",
        acceptance_criteria=[
            "Circuit breaker trips after 5 consecutive failures",
            "Calls resume after 30s cooldown",
        ],
        estimated_scope="low",
    )
    d = stub.to_dict()

    # ace_create_spec expects: objective, acceptance_criteria (as list of strings)
    assert "objective" in d
    assert "acceptance_criteria" in d
    assert isinstance(d["acceptance_criteria"], list)
    assert d["estimated_scope"] in ("low", "medium", "high")


# ── AutomationCandidate model tests ───────────────────────────────────────────


def test_automation_candidate_has_required_fields():
    """AutomationCandidate captures the automation opportunity with ROI estimate."""
    from core.engine.product.report_models import AutomationCandidate

    candidate = AutomationCandidate(
        title="Automate weekly status report generation",
        description="Replace manual weekly report compilation with automated data aggregation",
        hours_per_week_saved=3.0,
        loaded_hourly_rate=150.0,
        effort_tier="medium",
        spec_stub=None,
    )
    assert candidate.title == "Automate weekly status report generation"
    assert candidate.hours_per_week_saved == 3.0
    assert candidate.loaded_hourly_rate == 150.0


def test_automation_candidate_annual_value_is_computed():
    """AutomationCandidate.annual_value = hours/week * rate * 52."""
    from core.engine.product.report_models import AutomationCandidate

    candidate = AutomationCandidate(
        title="Automate deploy pipeline",
        description="Replace manual deploy steps",
        hours_per_week_saved=2.0,
        loaded_hourly_rate=200.0,
        effort_tier="low",
        spec_stub=None,
    )
    assert candidate.annual_value == pytest.approx(2.0 * 200.0 * 52)


def test_automation_candidate_effort_tier_must_be_valid():
    """AutomationCandidate effort_tier must be low, medium, or high."""
    from core.engine.product.report_models import AutomationCandidate

    with pytest.raises(ValueError, match="effort_tier"):
        AutomationCandidate(
            title="Test",
            description="Test",
            hours_per_week_saved=1.0,
            loaded_hourly_rate=100.0,
            effort_tier="extreme",
            spec_stub=None,
        )


def test_automation_candidate_to_dict_is_serializable():
    """AutomationCandidate.to_dict() includes annual_value."""
    from core.engine.product.report_models import AutomationCandidate

    candidate = AutomationCandidate(
        title="Automate invoicing",
        description="Replace manual invoice creation",
        hours_per_week_saved=4.0,
        loaded_hourly_rate=120.0,
        effort_tier="high",
        spec_stub=None,
    )
    d = candidate.to_dict()
    assert "annual_value" in d
    assert d["annual_value"] == pytest.approx(4.0 * 120.0 * 52)
    assert d["effort_tier"] == "high"


# ── DiscoveryReport model tests ───────────────────────────────────────────────


def _make_report(**overrides):
    """Build a minimal valid DiscoveryReport."""
    from core.engine.product.report_models import AutomationCandidate, DiscoveryReport

    defaults = {
        "product_id": "product:test",
        "client_name": "Acme Corp",
        "executive_summary": "Acme operates manual billing that costs 8 hours per week. "
        "Three high-value automations will recover 14 hours per week, worth $109,200 annually.",
        "automation_candidates": [
            AutomationCandidate(
                title="Automate billing reconciliation",
                description="Replace manual billing with automated reconciliation",
                hours_per_week_saved=8.0,
                loaded_hourly_rate=150.0,
                effort_tier="medium",
                spec_stub=None,
            )
        ],
        "systems_map_summary": "Core systems: billing, CRM, payment gateway. Weak integration between billing and CRM.",
        "preliminary": False,
    }
    defaults.update(overrides)
    return DiscoveryReport(**defaults)


def test_discovery_report_has_required_fields():
    """DiscoveryReport captures all required fields."""

    report = _make_report()
    assert report.product_id == "product:test"
    assert report.client_name == "Acme Corp"
    assert len(report.automation_candidates) == 1
    assert report.preliminary is False


def test_discovery_report_to_json_is_valid():
    """DiscoveryReport.to_json() produces valid JSON."""
    report = _make_report()
    raw = report.to_json()
    data = json.loads(raw)
    assert data["client_name"] == "Acme Corp"
    assert "automation_candidates" in data


def test_discovery_report_to_markdown_contains_exec_summary():
    """DiscoveryReport.to_markdown() includes the executive summary."""
    report = _make_report()
    md = report.to_markdown()
    assert "Acme Corp" in md
    assert "billing" in md.lower()


def test_discovery_report_exec_summary_has_no_jargon():
    """Executive summary must not contain technical jargon words."""

    _JARGON = ["discipline", "graph node", "archetype", "synthesis"]

    report = _make_report(
        executive_summary="This system has architecture gaps in the discipline layer "
        "caused by archetype mismatches in the synthesis pipeline."
    )
    for word in _JARGON:
        if word in report.executive_summary.lower():
            # The validator should flag this
            with pytest.raises(ValueError, match="jargon"):
                report.validate_exec_summary()
            return
    # If no jargon, validate_exec_summary must pass silently
    report.validate_exec_summary()


def test_discovery_report_validate_exec_summary_passes_clean_text():
    """validate_exec_summary() does not raise when summary is jargon-free."""
    report = _make_report(
        executive_summary="Acme's billing team spends 8 hours per week on manual reconciliation. "
        "Automating this process saves $62,400 annually at current staffing levels."
    )
    report.validate_exec_summary()  # must not raise


def test_discovery_report_preliminary_flag_marks_sections():
    """A preliminary report to_markdown() includes a preliminary warning."""
    report = _make_report(preliminary=True)
    md = report.to_markdown()
    assert "preliminary" in md.lower()


# ── ReportGenerator tests ─────────────────────────────────────────────────────


def test_report_generator_renders_markdown():
    """ReportGenerator.to_markdown() returns a non-empty string."""
    from core.engine.product.report_generator import ReportGenerator

    report = _make_report()
    generator = ReportGenerator(report)
    md = generator.to_markdown()
    assert isinstance(md, str)
    assert len(md) > 100
    assert "Acme Corp" in md


def test_report_generator_renders_json():
    """ReportGenerator.to_json() returns valid JSON."""
    from core.engine.product.report_generator import ReportGenerator

    report = _make_report()
    generator = ReportGenerator(report)
    raw = generator.to_json()
    data = json.loads(raw)
    assert data["client_name"] == "Acme Corp"


def test_report_generator_markdown_has_automation_section():
    """Rendered markdown includes automation candidates section."""
    from core.engine.product.report_generator import ReportGenerator

    report = _make_report()
    generator = ReportGenerator(report)
    md = generator.to_markdown()
    assert "Automate billing reconciliation" in md
    assert "$" in md  # ROI figures present


def test_report_generator_markdown_exec_summary_under_300_words():
    """Executive summary in rendered markdown is ≤ 300 words."""
    from core.engine.product.report_generator import ReportGenerator

    report = _make_report()
    generator = ReportGenerator(report)
    md = generator.to_markdown()

    # Extract the exec summary section (between ## Executive Summary and next ##)
    lines = md.split("\n")
    in_summary = False
    summary_words = 0
    for line in lines:
        if line.startswith("## Executive Summary"):
            in_summary = True
            continue
        if in_summary and line.startswith("##"):
            break
        if in_summary:
            summary_words += len(line.split())

    assert summary_words <= 300, f"Executive summary is {summary_words} words, must be ≤ 300"


# ── DiscoverySprintPackager tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_packager_generates_report_from_inputs(mock_packager_inputs):
    """DiscoverySprintPackager.generate() returns a DiscoveryReport."""
    from core.engine.product.discovery_sprint import DiscoverySprintPackager
    from core.engine.product.report_models import DiscoveryReport

    packager = DiscoverySprintPackager()
    report = await packager.generate(
        product_id="product:test",
        client_name="Test Client",
        scan_result=mock_packager_inputs["scan"],
        gaps_result=mock_packager_inputs["gaps"],
        recommend_result=mock_packager_inputs["recommend"],
        synthesis_result=mock_packager_inputs["synthesis"],
        loaded_hourly_rate=150.0,
    )
    assert isinstance(report, DiscoveryReport)
    assert report.product_id == "product:test"
    assert report.client_name == "Test Client"
    assert len(report.automation_candidates) > 0


@pytest.mark.asyncio
async def test_packager_falls_back_when_synthesis_absent(mock_packager_inputs):
    """Packager works without synthesis result — marks report as preliminary."""
    from core.engine.product.discovery_sprint import DiscoverySprintPackager

    packager = DiscoverySprintPackager()
    report = await packager.generate(
        product_id="product:test",
        client_name="Test Client",
        scan_result=mock_packager_inputs["scan"],
        gaps_result=mock_packager_inputs["gaps"],
        recommend_result=mock_packager_inputs["recommend"],
        synthesis_result=None,  # absent
        loaded_hourly_rate=150.0,
    )
    assert report.preliminary is True


@pytest.mark.asyncio
async def test_packager_spec_stubs_are_ace_create_spec_compatible(mock_packager_inputs):
    """Each automation candidate's spec_stub is directly passable to ace_create_spec."""
    from core.engine.product.discovery_sprint import DiscoverySprintPackager

    packager = DiscoverySprintPackager()
    report = await packager.generate(
        product_id="product:test",
        client_name="Test Client",
        scan_result=mock_packager_inputs["scan"],
        gaps_result=mock_packager_inputs["gaps"],
        recommend_result=mock_packager_inputs["recommend"],
        synthesis_result=mock_packager_inputs["synthesis"],
        loaded_hourly_rate=150.0,
    )
    for candidate in report.automation_candidates:
        if candidate.spec_stub is not None:
            d = candidate.spec_stub.to_dict()
            assert "objective" in d
            assert "acceptance_criteria" in d
            assert len(d["acceptance_criteria"]) > 0


@pytest.mark.asyncio
async def test_packager_roi_is_grounded(mock_packager_inputs):
    """ROI in the report is computed numerically, not qualitative strings."""
    from core.engine.product.discovery_sprint import DiscoverySprintPackager

    packager = DiscoverySprintPackager()
    report = await packager.generate(
        product_id="product:test",
        client_name="Test Client",
        scan_result=mock_packager_inputs["scan"],
        gaps_result=mock_packager_inputs["gaps"],
        recommend_result=mock_packager_inputs["recommend"],
        synthesis_result=mock_packager_inputs["synthesis"],
        loaded_hourly_rate=150.0,
    )
    for candidate in report.automation_candidates:
        # annual_value must be a real number > 0, not a string like "high"
        assert isinstance(candidate.annual_value, (int, float))
        assert candidate.annual_value > 0


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_packager_inputs():
    """Minimal scan/gaps/recommend/synthesis inputs for packager tests."""
    return {
        "scan": {
            "capabilities": [
                {"slug": "billing-reconciliation", "description": "Manual billing process"},
                {"slug": "report-generation", "description": "Manual weekly reports"},
                {"slug": "deploy-pipeline", "description": "Manual deployment steps"},
            ],
            "total_files": 142,
            "languages": ["Python", "TypeScript"],
        },
        "gaps": [
            {
                "slug": "billing-automation",
                "description": "No automated billing reconciliation",
                "discipline": "business_logic",
                "severity": "high",
            },
            {
                "slug": "report-automation",
                "description": "No automated report generation",
                "discipline": "business_logic",
                "severity": "medium",
            },
            {
                "slug": "deploy-automation",
                "description": "No CI/CD pipeline",
                "discipline": "devops",
                "severity": "high",
            },
        ],
        "recommend": [
            {
                "title": "Automate billing reconciliation",
                "rationale": "Saves 8h/week of manual work",
                "priority": 1,
                "hours_per_week_saved": 8.0,
            },
            {
                "title": "Automate report generation",
                "rationale": "Saves 3h/week of manual compilation",
                "priority": 2,
                "hours_per_week_saved": 3.0,
            },
            {
                "title": "Implement CI/CD pipeline",
                "rationale": "Saves 5h/week of manual deploy steps",
                "priority": 3,
                "hours_per_week_saved": 5.0,
            },
        ],
        "synthesis": {
            "leverage_points": [
                {
                    "rank": 1,
                    "discipline": "business_logic",
                    "intervention": "automate billing reconciliation",
                    "impact_score": 0.9,
                    "cascade_description": "billing → reporting → compliance",
                }
            ],
            "systems_map": {
                "nodes": [
                    {"discipline": "business_logic", "score": 0.3, "key_findings": ["manual billing"]},
                    {"discipline": "devops", "score": 0.4, "key_findings": ["no CI/CD"]},
                ],
                "edges": [],
            },
        },
    }

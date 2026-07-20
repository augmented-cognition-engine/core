# tests/test_hardening.py
"""Tests for engine.scanner.hardening and tool adapters."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.scanner.hardening import Finding, HardeningReport, rank_findings

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


def _finding(discipline="security", severity="high", file="engine/foo.py", tool="semgrep"):
    return Finding(
        discipline=discipline,
        severity=severity,
        file=file,
        line=10,
        message="test finding",
        tool=tool,
        rule_id="TEST001",
    )


# ── Unit: rank_findings ───────────────────────────────────────────────────────


def test_rank_findings_critical_security_first():
    findings = [
        _finding("code_conventions", "low"),
        _finding("security", "critical"),
        _finding("dependency_management", "high"),
    ]
    ranked = rank_findings(findings)
    assert ranked[0].severity == "critical"
    assert ranked[0].discipline == "security"


def test_rank_findings_same_severity_security_beats_code_conventions():
    findings = [
        _finding("code_conventions", "high"),
        _finding("security", "high"),
    ]
    ranked = rank_findings(findings)
    assert ranked[0].discipline == "security"


def test_rank_findings_empty():
    assert rank_findings([]) == []


def test_rank_findings_single():
    f = _finding()
    assert rank_findings([f]) == [f]


# ── Unit: _detect_stack_filesystem ────────────────────────────────────────────


def test_detect_stack_filesystem_python(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    from core.engine.scanner.hardening import _detect_stack_filesystem

    stack = _detect_stack_filesystem(str(tmp_path))
    assert "python" in stack


def test_detect_stack_filesystem_node(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "test"}')
    from core.engine.scanner.hardening import _detect_stack_filesystem

    stack = _detect_stack_filesystem(str(tmp_path))
    assert "node" in stack


def test_detect_stack_filesystem_multiple(tmp_path):
    (tmp_path / "main.py").write_text("x = 1")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "main.tf").write_text('resource "aws_s3_bucket" "b" {}')
    from core.engine.scanner.hardening import _detect_stack_filesystem

    stack = _detect_stack_filesystem(str(tmp_path))
    assert "python" in stack
    assert "node" in stack
    assert "terraform" in stack


# ── Unit: _detect_stack (DB path) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_stack_db_path(mock_pool, tmp_path):
    mock_p, mock_db = mock_pool
    lang_rows = [{"language": "python", "n": 50}, {"language": "typescript", "n": 20}]

    with (
        patch("core.engine.core.db.pool", mock_p),
        patch("core.engine.core.db.parse_rows", return_value=lang_rows),
    ):
        from core.engine.scanner import hardening

        stack = await hardening._detect_stack(str(tmp_path))
    assert "python" in stack
    assert "typescript" in stack


@pytest.mark.asyncio
async def test_detect_stack_falls_back_to_filesystem_on_db_error(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")
    from core.engine.scanner import hardening

    # Make parse_rows raise so the DB path fails and filesystem fallback kicks in
    with patch("core.engine.core.db.parse_rows", side_effect=Exception("DB unavailable")):
        stack = await hardening._detect_stack(str(tmp_path))
    # Falls back to filesystem — should detect python
    assert "python" in stack


# ── Unit: bandit_runner._parse ────────────────────────────────────────────────


def test_bandit_parse_high_high_maps_to_critical():
    from core.engine.scanner.bandit_runner import _parse

    raw = [
        {
            "issue_severity": "HIGH",
            "issue_confidence": "HIGH",
            "filename": "/repo/engine/auth.py",
            "line_number": 42,
            "issue_text": "Use of exec detected",
            "test_id": "B102",
        }
    ]
    findings = _parse(raw, "/repo")
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].file == "engine/auth.py"
    assert findings[0].line == 42
    assert findings[0].rule_id == "B102"
    assert findings[0].discipline == "security"


def test_bandit_parse_high_low_maps_to_high():
    from core.engine.scanner.bandit_runner import _parse

    raw = [
        {
            "issue_severity": "HIGH",
            "issue_confidence": "LOW",
            "filename": "/repo/engine/foo.py",
            "line_number": 5,
            "issue_text": "Possible SQL injection",
            "test_id": "B608",
        }
    ]
    findings = _parse(raw, "/repo")
    assert findings[0].severity == "high"


def test_bandit_parse_medium_maps_to_medium():
    from core.engine.scanner.bandit_runner import _parse

    raw = [
        {
            "issue_severity": "MEDIUM",
            "issue_confidence": "HIGH",
            "filename": "/repo/engine/x.py",
            "line_number": 1,
            "issue_text": "Weak hash",
            "test_id": "B324",
        }
    ]
    assert _parse(raw, "/repo")[0].severity == "medium"


def test_bandit_parse_strips_repo_prefix():
    from core.engine.scanner.bandit_runner import _parse

    raw = [
        {
            "issue_severity": "LOW",
            "issue_confidence": "LOW",
            "filename": "/home/user/myrepo/engine/auth.py",
            "line_number": 1,
            "issue_text": "x",
            "test_id": "B999",
        }
    ]
    findings = _parse(raw, "/home/user/myrepo")
    assert findings[0].file == "engine/auth.py"


def test_bandit_parse_empty():
    from core.engine.scanner.bandit_runner import _parse

    assert _parse([], "/repo") == []


# ── Unit: ruff_runner._parse + _rule_to_discipline ────────────────────────────


def test_ruff_rule_to_discipline_security():
    from core.engine.scanner.ruff_runner import _rule_to_discipline

    assert _rule_to_discipline("S101") == "security"


def test_ruff_rule_to_discipline_complexity():
    from core.engine.scanner.ruff_runner import _rule_to_discipline

    assert _rule_to_discipline("C901") == "performance"


def test_ruff_rule_to_discipline_default():
    from core.engine.scanner.ruff_runner import _rule_to_discipline

    assert _rule_to_discipline("E501") == "code_conventions"


def test_ruff_parse_security_rule_maps_to_high():
    from core.engine.scanner.ruff_runner import _parse

    raw = [
        {
            "code": "S102",
            "filename": "/repo/engine/cli.py",
            "message": "Use of exec",
            "location": {"row": 10, "column": 4},
            "fix": None,
        }
    ]
    findings = _parse(raw, "/repo")
    assert findings[0].severity == "high"
    assert findings[0].discipline == "security"


def test_ruff_parse_fixable_populates_fix_command():
    from core.engine.scanner.ruff_runner import _parse

    raw = [
        {
            "code": "E501",
            "filename": "/repo/engine/foo.py",
            "message": "Line too long",
            "location": {"row": 5, "column": 80},
            "fix": {"message": "Remove extra chars"},
        }
    ]
    findings = _parse(raw, "/repo")
    assert "ruff check --fix" in findings[0].fix_command


def test_ruff_parse_strips_repo_prefix():
    from core.engine.scanner.ruff_runner import _parse

    raw = [
        {
            "code": "W291",
            "filename": "/home/user/repo/engine/foo.py",
            "message": "Trailing whitespace",
            "location": {"row": 3, "column": 0},
            "fix": None,
        }
    ]
    findings = _parse(raw, "/home/user/repo")
    assert findings[0].file == "engine/foo.py"


# ── Unit: pip_audit_runner._parse ────────────────────────────────────────────


def test_pip_audit_parse_with_fix_version():
    from core.engine.scanner.pip_audit_runner import _parse

    raw = [
        {
            "name": "requests",
            "version": "2.20.0",
            "vulns": [
                {
                    "id": "PYSEC-2023-001",
                    "description": "HTTP redirect vulnerability",
                    "fix_versions": ["2.31.0"],
                }
            ],
        }
    ]
    findings = _parse(raw, "/repo")
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "high"
    assert f.discipline == "dependency_management"
    assert "requests" in f.message
    assert "2.31.0" in f.fix_command
    assert f.tool == "pip_audit"


def test_pip_audit_parse_no_fix_version_maps_medium():
    from core.engine.scanner.pip_audit_runner import _parse

    raw = [
        {
            "name": "cryptography",
            "version": "1.0.0",
            "vulns": [{"id": "CVE-2023-0001", "description": "Weak cipher", "fix_versions": []}],
        }
    ]
    findings = _parse(raw, "/repo")
    assert findings[0].severity == "medium"


def test_pip_audit_parse_no_vulns():
    from core.engine.scanner.pip_audit_runner import _parse

    assert _parse([{"name": "boto3", "version": "1.0.0", "vulns": []}], "/repo") == []


# ── Unit: trufflehog_runner._parse ────────────────────────────────────────────


def test_trufflehog_parse_ndjson():
    from core.engine.scanner.trufflehog_runner import _parse

    record = {
        "DetectorName": "AWS",
        "SourceMetadata": {
            "Data": {
                "Filesystem": {
                    "file": "/repo/config/secrets.py",
                    "line": 7,
                }
            }
        },
    }
    raw = json.dumps(record).encode()
    findings = _parse(raw, "/repo")
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "critical"
    assert f.discipline == "security"
    assert f.tool == "trufflehog"
    assert f.file == "config/secrets.py"
    assert f.line == 7
    # Credential value must be redacted
    assert "redacted" in f.message.lower()


def test_trufflehog_parse_redacts_credential_value():
    """The raw credential value must not appear in the stored message."""
    from core.engine.scanner.trufflehog_runner import _parse

    record = {
        "DetectorName": "GitHub",
        "Raw": "ghp_supersecrettoken12345",
        "SourceMetadata": {"Data": {"Filesystem": {"file": "/repo/.env", "line": 1}}},
    }
    raw = json.dumps(record).encode()
    findings = _parse(raw, "/repo")
    assert "supersecrettoken" not in findings[0].message


def test_trufflehog_parse_empty_output():
    from core.engine.scanner.trufflehog_runner import _parse

    assert _parse(b"", "/repo") == []


def test_trufflehog_parse_skips_invalid_json_lines():
    from core.engine.scanner.trufflehog_runner import _parse

    raw = b'{"DetectorName": "AWS", "SourceMetadata": {"Data": {"Filesystem": {"file": "/repo/a.py", "line": 1}}}}\nnot-valid-json\n'
    findings = _parse(raw, "/repo")
    assert len(findings) == 1  # Only valid line parsed


# ── Integration: run_hardening ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_hardening_returns_report_structure(tmp_path):
    """run_hardening returns a HardeningReport even when all tools are absent."""
    from core.engine.scanner.hardening import run_hardening

    # All adapters will return [] (tools not installed in test env)
    report = await run_hardening(repo_path=str(tmp_path), stack=["python"])
    assert isinstance(report, HardeningReport)
    assert isinstance(report.findings, list)
    assert isinstance(report.tools_run, list)
    assert isinstance(report.tools_skipped, list)
    assert report.scan_id  # UUID present
    assert report.stack == ["python"]
    assert report.duration_seconds >= 0


@pytest.mark.asyncio
async def test_run_hardening_fast_mode_skips_most_tools(tmp_path):
    """fast=True only dispatches TruffleHog + Semgrep critical."""
    from core.engine.scanner.hardening import run_hardening

    report = await run_hardening(repo_path=str(tmp_path), stack=["python"], fast=True)
    # In fast mode, bandit/ruff/pip_audit should NOT appear in tools_run
    assert "bandit" not in report.tools_run
    assert "ruff" not in report.tools_run
    assert "pip_audit" not in report.tools_run


@pytest.mark.asyncio
async def test_run_hardening_integrates_findings(tmp_path):
    """Findings from mocked adapters are ranked and included in report."""
    critical_finding = _finding("security", "critical")
    low_finding = _finding("code_conventions", "low")

    from core.engine.scanner import hardening

    with (
        patch("core.engine.scanner.hardening._detect_stack", return_value=["python"]),
        patch("core.engine.scanner.hardening._run_semgrep_full", return_value=[low_finding]),
        patch("core.engine.scanner.trufflehog_runner.run", return_value=[]),
        patch("core.engine.scanner.bandit_runner.run", return_value=[critical_finding]),
        patch("core.engine.scanner.ruff_runner.run", return_value=[]),
        patch("core.engine.scanner.pip_audit_runner.run", return_value=[]),
    ):
        report = await hardening.run_hardening(repo_path=str(tmp_path))

    assert len(report.findings) == 2
    # Critical security sorts before low code_conventions
    assert report.findings[0].severity == "critical"
    assert "security" in report.summary
    assert "bandit" in report.tools_run


# ── Integration: _write_findings ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_findings_calls_db_for_each_finding(mock_pool):
    mock_p, mock_db = mock_pool
    findings = [_finding(), _finding("dependency_management", "high", "requirements.txt", "pip_audit")]

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.scanner import hardening

        with patch.object(hardening, "_link_finding_to_capability", return_value=None):
            count = await hardening._write_findings(findings, "scan-123", "product:platform")

    assert count == 2
    assert mock_db.query.call_count == 2


@pytest.mark.asyncio
async def test_write_findings_empty_list(mock_pool):
    mock_p, _ = mock_pool

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.scanner import hardening

        count = await hardening._write_findings([], "scan-xyz", "product:platform")

    assert count == 0


# ── Integration: ace_scan_hardening MCP tool ─────────────────────────────────


@pytest.mark.asyncio
async def test_ace_scan_hardening_returns_dict(tmp_path):
    """ace_scan_hardening returns required keys even with no findings."""
    from core.engine.mcp.tools import ace_scan_hardening

    with patch("core.engine.scanner.hardening.run_hardening") as mock_run:
        from core.engine.scanner.hardening import HardeningReport

        mock_run.return_value = HardeningReport(
            findings=[],
            tools_run=["semgrep"],
            tools_skipped=["trufflehog"],
            scan_id="scan-abc",
            repo_path=str(tmp_path),
            stack=["python"],
            duration_seconds=1.5,
            summary={},
        )
        result = await ace_scan_hardening(repo_path=str(tmp_path), store=False)

    assert "scan_id" in result
    assert "tools_run" in result
    assert "total_findings" in result
    assert "summary" in result
    assert result["stored"] is False


@pytest.mark.asyncio
async def test_ace_scan_hardening_stores_findings(tmp_path, mock_pool):
    """ace_scan_hardening calls _write_findings when store=True and findings exist."""
    mock_p, _ = mock_pool

    from core.engine.scanner.hardening import HardeningReport

    mock_report = HardeningReport(
        findings=[_finding()],
        tools_run=["bandit"],
        tools_skipped=[],
        scan_id="scan-def",
        repo_path=str(tmp_path),
        stack=["python"],
        duration_seconds=2.0,
        summary={"security": {"high": 1}},
    )

    from core.engine.mcp.tools import ace_scan_hardening

    with (
        patch("core.engine.scanner.hardening.run_hardening", return_value=mock_report),
        patch("core.engine.scanner.hardening._write_findings", new_callable=AsyncMock, return_value=1) as mock_write,
        patch("core.engine.core.db.pool", mock_p),
    ):
        result = await ace_scan_hardening(repo_path=str(tmp_path), store=True)

    mock_write.assert_called_once()
    assert result["stored"] is True
    assert result["total_findings"] == 1

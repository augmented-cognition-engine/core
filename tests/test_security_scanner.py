def test_scan_empty_files_returns_list():
    import asyncio

    from core.engine.scanner.security_scanner import scan_files

    result = asyncio.run(scan_files([], "/tmp"))
    assert isinstance(result, list)


def test_finding_dataclass_fields():
    from core.engine.scanner.security_scanner import SecurityFinding

    f = SecurityFinding(
        rule_id="python.lang.security.audit.hardcoded-password",
        severity="ERROR",
        message="Hardcoded password",
        file="config.py",
        line=1,
    )
    assert f.severity in ("ERROR", "WARNING", "INFO")
    assert f.rule_id


def test_scan_missing_semgrep_returns_empty():
    import asyncio
    from unittest.mock import patch

    from core.engine.scanner.security_scanner import scan_files

    with patch("core.engine.scanner.security_scanner._semgrep_available", False):
        result = asyncio.run(scan_files(["any.py"], "/tmp"))
        assert result == []


def test_findings_to_intelligence_format():
    from core.engine.scanner.security_scanner import SecurityFinding, findings_to_intelligence

    findings = [
        SecurityFinding("rule.sql-injection", "ERROR", "SQL injection risk", "api.py", 42),
        SecurityFinding("rule.xss", "WARNING", "XSS risk", "views.py", 10),
    ]
    intel = findings_to_intelligence(findings)
    assert "Security" in intel
    assert "sql-injection" in intel or "ERROR" in intel


def test_findings_to_intelligence_empty():
    from core.engine.scanner.security_scanner import findings_to_intelligence

    assert findings_to_intelligence([]) == ""

# tests/test_wiring_auditor.py
"""Tests for WiringAuditor — detects built-but-not-connected components.

Three checks:
  1. MCP parity: ace_* functions in tools.py with no registration in server.py
  2. Idle validators: _validate_* functions defined but never called
  3. run() integration: reads real files, returns structured report
"""

from __future__ import annotations

# ── check_mcp_parity ─────────────────────────────────────────────────────────


def test_mcp_parity_detects_unregistered_tool():
    """Function in tools.py not referenced in server.py is reported as a gap."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    tools_src = "async def ace_foo(x: str): ...\nasync def ace_bar(y: str): ..."
    # server only imports ace_foo
    server_src = (
        "from engine.mcp.tools import ace_foo as _fn\n"
        "@mcp.tool()\nasync def ace_foo_handler(x: str): return await _fn(x)"
    )

    gaps = WiringAuditor().check_mcp_parity(tools_src, server_src)
    assert "ace_bar" in gaps
    assert "ace_foo" not in gaps


def test_mcp_parity_no_gaps_when_all_tools_registered():
    """No gaps reported when every ace_* function appears in server.py."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    tools_src = "async def ace_foo(x: str): ..."
    server_src = "from engine.mcp.tools import ace_foo as _fn\n@mcp.tool()\ndef ace_foo_handler(): ..."

    gaps = WiringAuditor().check_mcp_parity(tools_src, server_src)
    assert gaps == []


def test_mcp_parity_ignores_non_ace_functions():
    """Helper functions (no ace_ prefix) are not checked for MCP registration."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    tools_src = "def _build_payload(x): ...\nasync def ace_foo(x: str): ..."
    server_src = "from engine.mcp.tools import ace_foo as _fn"

    gaps = WiringAuditor().check_mcp_parity(tools_src, server_src)
    assert "_build_payload" not in gaps
    assert gaps == []


def test_mcp_parity_empty_tools_returns_no_gaps():
    """No functions in tools.py → no gaps."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    gaps = WiringAuditor().check_mcp_parity("", "")
    assert gaps == []


# ── check_idle_validators ─────────────────────────────────────────────────────


def test_idle_validators_detects_uncalled_validate():
    """_validate_foo() defined but never called is reported as idle."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    source_files = {"engine/foo/bar.py": "def _validate_widget(x):\n    pass\n\ndef real_func():\n    pass"}
    # all_source includes the definition but no call
    all_source = "def _validate_widget(x):\n    pass\n\ndef real_func():\n    pass"

    idle = WiringAuditor().check_idle_validators(source_files, all_source)
    assert "_validate_widget" in idle


def test_idle_validators_no_idle_when_called():
    """_validate_foo() that has a call site is not reported as idle."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    source_files = {"engine/foo/bar.py": "def _validate_widget(x):\n    pass"}
    all_source = "def _validate_widget(x):\n    pass\n\ndef real_func():\n    _validate_widget(value)"

    idle = WiringAuditor().check_idle_validators(source_files, all_source)
    assert "_validate_widget" not in idle


def test_idle_validators_ignores_test_files():
    """Validators defined only in test files are not considered idle."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    source_files = {"tests/test_something.py": "def _validate_helper(x):\n    pass"}
    all_source = "def _validate_helper(x):\n    pass"

    idle = WiringAuditor().check_idle_validators(source_files, all_source)
    # test-file validators are excluded from the check
    assert "_validate_helper" not in idle


def test_idle_validators_multiple_files():
    """Detects idle validators across multiple source files."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    source_files = {
        "engine/a.py": "def _validate_alpha(x): ...",
        "engine/b.py": "def _validate_beta(x): ...",
    }
    # beta is called, alpha is not
    all_source = "def _validate_alpha(x): ...\ndef _validate_beta(x): ...\n_validate_beta(val)"

    idle = WiringAuditor().check_idle_validators(source_files, all_source)
    assert "_validate_alpha" in idle
    assert "_validate_beta" not in idle


# ── run() integration ─────────────────────────────────────────────────────────


def test_run_returns_structured_report(monkeypatch):
    """run() returns a dict with mcp_parity_gaps, idle_validators, total_gaps, clean."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    auditor = WiringAuditor()

    # Patch file reading so the test is hermetic
    monkeypatch.setattr(
        auditor,
        "_read_tools_source",
        lambda: "async def ace_foo(x): ...\nasync def ace_missing(y): ...",
    )
    monkeypatch.setattr(
        auditor,
        "_read_server_source",
        lambda: "from engine.mcp.tools import ace_foo as _fn",
    )
    monkeypatch.setattr(
        auditor,
        "_collect_source_files",
        lambda: {
            "engine/foo.py": "def _validate_orphan(x): pass",
        },
    )

    report = auditor.run()

    assert "mcp_parity_gaps" in report
    assert "idle_validators" in report
    assert "total_gaps" in report
    assert "clean" in report
    assert "ace_missing" in report["mcp_parity_gaps"]
    assert "_validate_orphan" in report["idle_validators"]
    assert report["clean"] is False
    assert report["total_gaps"] >= 2


def test_run_clean_when_fully_wired(monkeypatch):
    """run() reports clean=True when no gaps found."""
    from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

    auditor = WiringAuditor()
    monkeypatch.setattr(auditor, "_read_tools_source", lambda: "async def ace_foo(x): ...")
    monkeypatch.setattr(
        auditor,
        "_read_server_source",
        lambda: "from engine.mcp.tools import ace_foo as _fn",
    )
    monkeypatch.setattr(
        auditor,
        "_collect_source_files",
        lambda: {"engine/foo.py": "def _validate_thing(x): ...\n_validate_thing(v)"},
    )

    report = auditor.run()
    assert report["clean"] is True
    assert report["total_gaps"] == 0

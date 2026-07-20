"""Tests for coverage_extractor: cobertura XML parsing and CoverageRow properties."""

import os
import tempfile

import pytest

from core.engine.scanner.coverage_extractor import (
    CoverageRow,
    _parse_cobertura,
    run_coverage,
)

# ── CoverageRow properties ─────────────────────────────────────────────────


def test_line_pct_zero_when_no_lines():
    row = CoverageRow(file="x.py", lines_covered=0, lines_total=0)
    assert row.line_pct == 0.0


def test_line_pct_calculated():
    row = CoverageRow(file="x.py", lines_covered=80, lines_total=100)
    assert row.line_pct == 0.8


def test_branch_pct_zero_when_no_branches():
    row = CoverageRow(file="x.py", lines_covered=5, lines_total=10)
    assert row.branch_pct == 0.0


def test_branch_pct_calculated():
    row = CoverageRow(file="x.py", lines_covered=5, lines_total=10, branches_covered=3, branches_total=4)
    assert row.branch_pct == 0.75


def test_function_pct_zero_when_no_functions():
    row = CoverageRow(file="x.py", lines_covered=0, lines_total=0)
    assert row.function_pct == 0.0


def test_function_pct_calculated():
    row = CoverageRow(file="x.py", lines_covered=0, lines_total=0, functions_covered=3, functions_total=4)
    assert row.function_pct == 0.75


# ── _parse_cobertura ───────────────────────────────────────────────────────


_COBERTURA_XML = """\
<?xml version="1.0" ?>
<coverage>
  <packages>
    <package>
      <classes>
        <class filename="/repo/engine/foo.py" name="foo">
          <methods>
            <method name="tested_fn">
              <lines><line hits="1" number="5"/></lines>
            </method>
            <method name="untested_fn">
              <lines><line hits="0" number="12"/></lines>
            </method>
          </methods>
          <lines>
            <line hits="1" number="1"/>
            <line hits="1" number="5"/>
            <line hits="0" number="12"/>
            <line branch="true" hits="1" number="20"/>
            <line branch="true" hits="0" number="21"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


def test_parse_cobertura_path_normalized():
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write(_COBERTURA_XML)
        path = f.name
    try:
        rows = _parse_cobertura(path, "/repo")
        assert len(rows) == 1
        assert rows[0].file == "engine/foo.py"
    finally:
        os.unlink(path)


def test_parse_cobertura_line_counts():
    # cls.iter("line") yields ALL <line> elements in the class subtree,
    # including those nested inside <method> elements (2 + 5 = 7 total).
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write(_COBERTURA_XML)
        path = f.name
    try:
        rows = _parse_cobertura(path, "/repo")
        r = rows[0]
        assert r.lines_total == 7  # 2 method lines + 5 class lines
        assert r.lines_covered == 4  # hits>0: method-line5, class1, class5, class20
    finally:
        os.unlink(path)


def test_parse_cobertura_branch_counts():
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write(_COBERTURA_XML)
        path = f.name
    try:
        rows = _parse_cobertura(path, "/repo")
        r = rows[0]
        assert r.branches_total == 2
        assert r.branches_covered == 1
    finally:
        os.unlink(path)


def test_parse_cobertura_untested_functions():
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write(_COBERTURA_XML)
        path = f.name
    try:
        rows = _parse_cobertura(path, "/repo")
        r = rows[0]
        assert r.functions_total == 2
        assert r.functions_covered == 1
        assert "untested_fn" in r.untested_functions
        assert "tested_fn" not in r.untested_functions
    finally:
        os.unlink(path)


def test_parse_cobertura_missing_file_returns_empty():
    rows = _parse_cobertura("/nonexistent/coverage.xml", "/repo")
    assert rows == []


def test_parse_cobertura_invalid_xml_returns_empty():
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write("not xml at all <<<")
        path = f.name
    try:
        rows = _parse_cobertura(path, "/repo")
        assert rows == []
    finally:
        os.unlink(path)


# ── run_coverage graceful degradation ─────────────────────────────────────


@pytest.mark.asyncio
async def test_run_coverage_unsupported_stack_returns_empty():
    report = await run_coverage("/tmp", stack="cobol")
    assert report.rows == []
    assert report.tool == "none"


@pytest.mark.asyncio
async def test_run_coverage_node_deferred_returns_empty():
    report = await run_coverage("/tmp", stack="node")
    assert report.rows == []
    assert report.tool == "c8"


@pytest.mark.asyncio
async def test_run_coverage_go_deferred_returns_empty():
    report = await run_coverage("/tmp", stack="go")
    assert report.rows == []
    assert report.tool == "go-cover"

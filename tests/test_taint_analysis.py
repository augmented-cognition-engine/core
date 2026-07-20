"""Tests for taint analysis engine."""

from core.engine.review.taint import TaintAnalyzer, TaintReport, _classify_flow

PYTHON_WITH_TAINT = """
from flask import request
import subprocess

def handle():
    user_input = request.args.get("cmd")
    result = subprocess.run(user_input, shell=True)
    return result.stdout
"""

PYTHON_SAFE = """
import os

def get_config():
    return {"debug": False}
"""

PYTHON_SQL_INJECTION = """
from flask import request
import sqlite3

def search(db):
    query = request.args.get("q")
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM users WHERE name = '{query}'")
    return cursor.fetchall()
"""

JS_XSS = """
app.get("/profile", (req, res) => {
    const name = req.params.name;
    res.send(`<h1>Hello ${name}</h1>`);
});
"""


def test_detect_python_sources_and_sinks():
    analyzer = TaintAnalyzer()
    sources, sinks = analyzer.analyze_file("app.py", PYTHON_WITH_TAINT, "python")
    assert len(sources) >= 1
    assert len(sinks) >= 1


def test_safe_code_no_flows():
    analyzer = TaintAnalyzer()
    sources, sinks = analyzer.analyze_file("config.py", PYTHON_SAFE, "python")
    assert len(sinks) == 0


def test_same_file_flow_detected():
    analyzer = TaintAnalyzer()
    report = analyzer.analyze_diff_files([{"path": "app.py", "content": PYTHON_WITH_TAINT, "language": "python"}])
    assert len(report.flows) > 0
    assert report.flows[0].severity == "critical"
    assert report.flows[0].flow_type == "command_injection"


def test_sql_injection_detected():
    analyzer = TaintAnalyzer()
    report = analyzer.analyze_diff_files([{"path": "search.py", "content": PYTHON_SQL_INJECTION, "language": "python"}])
    sql_flows = [f for f in report.flows if f.flow_type == "sql_injection"]
    assert len(sql_flows) > 0


def test_js_xss_detected():
    analyzer = TaintAnalyzer()
    report = analyzer.analyze_diff_files([{"path": "server.js", "content": JS_XSS, "language": "javascript"}])
    assert len(report.flows) > 0
    xss_flows = [f for f in report.flows if f.flow_type == "xss"]
    assert len(xss_flows) > 0


def test_cross_file_flows():
    analyzer = TaintAnalyzer()
    report = analyzer.analyze_diff_files(
        [
            {
                "path": "input.py",
                "content": "from flask import request\ndef get_input():\n    return request.args.get('x')\n",
                "language": "python",
            },
            {
                "path": "db.py",
                "content": "def save(data):\n    cursor.execute(f'INSERT INTO t VALUES ({data})')\n",
                "language": "python",
            },
        ]
    )
    cross = [f for f in report.flows if f.source_file != f.sink_file]
    assert len(cross) > 0
    assert cross[0].severity == "high"  # lower confidence for cross-file
    assert cross[0].confidence < 0.7


def test_empty_files():
    analyzer = TaintAnalyzer()
    report = analyzer.analyze_diff_files([])
    assert report.flows == []
    assert report.files_analyzed == 0


def test_unknown_language_skipped():
    analyzer = TaintAnalyzer()
    report = analyzer.analyze_diff_files([{"path": "data.csv", "content": "a,b,c", "language": "unknown"}])
    assert report.flows == []


def test_classify_flow():
    assert _classify_flow("execute(") == "sql_injection"
    assert _classify_flow("subprocess.run") == "command_injection"
    assert _classify_flow("eval(") == "code_injection"
    assert _classify_flow("innerHTML") == "xss"


def test_report_has_critical():
    report = TaintReport()
    assert report.has_critical is False


def test_comments_skipped():
    analyzer = TaintAnalyzer()
    code = "# request.args.get('x')\n# eval(data)\n"
    sources, sinks = analyzer.analyze_file("test.py", code, "python")
    assert len(sources) == 0
    assert len(sinks) == 0

"""Tests for engine.scanner.pattern_search — structural AST pattern search."""

from __future__ import annotations

from core.engine.scanner.pattern_search import find_calls, find_definitions, search_pattern


def test_find_calls_python():
    code = "def main():\n    foo()\n    bar(x=1)\n"
    calls = find_calls(code, "python", "foo")
    assert len(calls) == 1
    assert calls[0]["name"] == "foo"
    assert calls[0]["line"] == 2


def test_find_calls_multiple():
    code = "foo()\nfoo(1, 2)\n"
    calls = find_calls(code, "python", "foo")
    assert len(calls) == 2


def test_find_definitions_python():
    code = "def foo():\n    pass\nclass Bar:\n    pass\n"
    defs = find_definitions(code, "python")
    names = [d["name"] for d in defs]
    assert "foo" in names
    assert "Bar" in names


def test_find_definitions_typescript():
    code = "function greet(name: string): void {\n  console.log(name);\n}\n"
    defs = find_definitions(code, "typescript")
    assert any(d["name"] == "greet" for d in defs)


def test_search_pattern_python():
    code = "x = 1\ny = x + 2\n"
    matches = search_pattern(code, "python", "$A = $B")
    assert len(matches) >= 1


def test_find_calls_no_match():
    code = "def main():\n    pass\n"
    calls = find_calls(code, "python", "nonexistent")
    assert calls == []


def test_unsupported_language_returns_empty():
    result = find_calls("some code", "cobol", "foo")
    assert result == []

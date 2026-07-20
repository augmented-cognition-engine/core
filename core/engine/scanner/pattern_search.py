"""Structural AST pattern search using ast-grep-py.

Finds call sites, definitions, and custom patterns across supported languages.
Used by graph_builder for symbol→symbol call edges and by seam extractors.

Currently _ASTGREP_LANG covers 13 languages. find_calls() works for all of them.
find_definitions() has patterns for Python, TypeScript/JS, Go, Rust only —
Java, Ruby, C#, Kotlin return [] from _def_patterns until Task 4 adds those.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ASTGREP_LANG: dict[str, str] = {
    "python": "python",
    "typescript": "typescript",
    "tsx": "tsx",
    "javascript": "javascript",
    "rust": "rust",
    "go": "go",
    "ruby": "ruby",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "c_sharp": "csharp",
    "swift": "swift",
    "kotlin": "kotlin",
}


def _get_lang(lang: str) -> str | None:
    return _ASTGREP_LANG.get(lang)


def find_calls(code: str, lang: str, callee: str) -> list[dict]:
    """Find all call sites of `callee` in code.

    Returns list of {name, line, text}.
    """
    astgrep_lang = _get_lang(lang)
    if not astgrep_lang:
        return []
    try:
        from ast_grep_py import SgRoot

        root = SgRoot(code, astgrep_lang)
        matches = root.root().find_all(pattern=f"{callee}($$$ARGS)")
        return [{"name": callee, "line": m.range().start.line + 1, "text": m.text()} for m in matches]
    except Exception as exc:
        logger.debug("ast-grep find_calls failed lang=%s: %s", lang, exc)
        return []


def find_definitions(code: str, lang: str) -> list[dict]:
    """Find all function and class definitions.

    Returns list of {name, kind, line}.
    """
    astgrep_lang = _get_lang(lang)
    if not astgrep_lang:
        return []
    try:
        from ast_grep_py import SgRoot

        root = SgRoot(code, astgrep_lang)
        node = root.root()
        results = []
        seen: set[tuple[str, int]] = set()
        for pattern, kind in _def_patterns(lang):
            for m in node.find_all(pattern=pattern):
                name_node = m.get_match("NAME")
                name = name_node.text() if name_node else m.text()[:40]
                line = m.range().start.line + 1
                key = (name, line)
                if key in seen:
                    continue
                seen.add(key)
                results.append({"name": name, "kind": kind, "line": line})
        return results
    except Exception as exc:
        logger.debug("ast-grep find_definitions failed lang=%s: %s", lang, exc)
        return []


def search_pattern(code: str, lang: str, pattern: str) -> list[dict]:
    """Generic structural pattern search. Returns list of {line, text}."""
    astgrep_lang = _get_lang(lang)
    if not astgrep_lang:
        return []
    try:
        from ast_grep_py import SgRoot

        matches = SgRoot(code, astgrep_lang).root().find_all(pattern=pattern)
        return [{"line": m.range().start.line + 1, "text": m.text()} for m in matches]
    except Exception as exc:
        logger.debug("ast-grep search_pattern failed: %s", exc)
        return []


def _def_patterns(lang: str) -> list[tuple[str, str]]:
    if lang == "python":
        return [
            ("def $NAME($$$): $$$", "function"),
            ("async def $NAME($$$): $$$", "function"),
            ("class $NAME: $$$", "class"),
            ("class $NAME($$$): $$$", "class"),
        ]
    if lang in ("typescript", "tsx", "javascript"):
        return [
            # with return type annotation (e.g. TypeScript typed functions)
            ("function $NAME($$$): $RTYPE { $$$ }", "function"),
            # without return type annotation (plain JS or inferred TS)
            ("function $NAME($$$) { $$$ }", "function"),
            ("const $NAME = ($$$) => $$$", "function"),
            ("class $NAME { $$$ }", "class"),
        ]
    if lang == "go":
        return [
            ("func $NAME($$$) $$$", "function"),
            ("type $NAME struct { $$$ }", "class"),
        ]
    if lang == "rust":
        return [
            ("fn $NAME($$$) $$$", "function"),
            ("struct $NAME { $$$ }", "class"),
        ]
    # java, ruby, c_sharp, kotlin: patterns added in Task 4 (language expansion)
    return []

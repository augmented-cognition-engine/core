"""Language detection — walk a repo and identify languages by file extension."""

from __future__ import annotations

import os
from dataclasses import dataclass

SKIP_DIRS = {
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    ".hg",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".cargo",
    # Reference repos — analyzed separately, not part of the product
    "claude-repo",
}

EXTENSION_MAP = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".lua": "lua",
    ".zig": "zig",
}


@dataclass
class LanguageInfo:
    name: str
    file_count: int
    percentage: float
    extensions: list[str]


def detect_languages(repo_path: str) -> list[LanguageInfo]:
    """Walk a repo, count files by language, return ranked list."""
    repo_path = os.path.abspath(repo_path)
    lang_counts: dict[str, int] = {}
    lang_extensions: dict[str, set[str]] = {}

    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            _, ext = os.path.splitext(fname)
            lang = EXTENSION_MAP.get(ext)
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
                lang_extensions.setdefault(lang, set()).add(ext)

    total = sum(lang_counts.values())
    if total == 0:
        return []

    result = []
    for lang, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True):
        result.append(
            LanguageInfo(
                name=lang,
                file_count=count,
                percentage=round(count / total * 100, 1),
                extensions=sorted(lang_extensions.get(lang, set())),
            )
        )
    return result

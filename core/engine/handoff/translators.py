"""Agent-specific log → plain-language translators.

v1: full Claude Code translator. Other agents get stub pass-through.
"""

from __future__ import annotations

import re

# Raw log patterns that must not appear in plain_language output (AC 4)
_FORBIDDEN_LOG_PREFIXES = re.compile(r"^\[(?:INFO|ERROR|WARN|DEBUG|TRACE)\]", re.IGNORECASE)
_MONOSPACE_PATH = re.compile(r"`[^`]+`")

# Claude Code log pattern matchers → (regex, plain-language template)
_CLAUDE_CODE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Editing file:\s*(\S+)", re.IGNORECASE), "updating {0}"),
    (re.compile(r"Writing file:\s*(\S+)", re.IGNORECASE), "writing {0}"),
    (re.compile(r"Reading file:\s*(\S+)", re.IGNORECASE), "reviewing {0}"),
    (
        re.compile(r"Running tests?.*?(\d+)\s+passed.*?(\d+)\s+failed", re.IGNORECASE),
        "ran tests — {0} passed, {1} failed",
    ),
    (re.compile(r"Running tests?.*?(\d+)\s+passed", re.IGNORECASE), "ran tests — {0} passing"),
    (re.compile(r"Running(?:\s+\w+)?\s+tests?", re.IGNORECASE), "running tests"),
    (re.compile(r"Creating file:\s*(\S+)", re.IGNORECASE), "creating {0}"),
    (re.compile(r"Deleting file:\s*(\S+)", re.IGNORECASE), "removing {0}"),
    (re.compile(r"Bash(?:Tool)?:\s*(.*)", re.IGNORECASE), "running a shell command"),
    (re.compile(r"git\s+(commit|push|add|stash)", re.IGNORECASE), "committing changes"),
    (
        re.compile(r"Composer applied\s+(\d+)\s+edits?\s+across\s+(\d+)\s+files?", re.IGNORECASE),
        "made {0} edits across {1} files",
    ),
    (
        re.compile(r"Sandbox exec:.*?(\d+)\s+passed.*?(\d+)\s+failed", re.IGNORECASE),
        "ran sandbox tests — {0} passed, {1} failed",
    ),
]


def translate_claude_code(raw_log: str) -> str:
    """Translate a Claude Code log line into partner-voice plain language."""
    line = raw_log.strip()

    for pattern, template in _CLAUDE_CODE_PATTERNS:
        m = pattern.search(line)
        if m:
            groups = [_clean_path(g) for g in m.groups()]
            return template.format(*groups)

    # Fallback: strip forbidden prefixes and monospace paths, return cleaned text
    cleaned = _FORBIDDEN_LOG_PREFIXES.sub("", line).strip()
    cleaned = _MONOSPACE_PATH.sub(lambda m: m.group(0)[1:-1], cleaned)
    if len(cleaned) > 80:
        cleaned = cleaned[:77] + "..."
    return cleaned or "working on it"


def translate_generic(raw_log: str) -> str:
    """Stub translator for non-Claude-Code agents — returns sanitized log line."""
    line = raw_log.strip()
    cleaned = _FORBIDDEN_LOG_PREFIXES.sub("", line).strip()
    return cleaned[:120] if cleaned else "processing"


def translate(agent: str, raw_log: str) -> str:
    """Route to the correct translator for an agent."""
    if agent == "claude_code":
        return translate_claude_code(raw_log)
    return translate_generic(raw_log)


def _clean_path(path: str) -> str:
    """Extract the human-readable module name from a file path."""
    if not path:
        return path
    # engine/auth/oauth.py → "the auth module"
    parts = path.replace("\\", "/").split("/")
    stem = parts[-1].replace(".py", "").replace("_", " ")
    if len(parts) >= 3:
        module = parts[-2].replace("_", " ")
        return f"the {module} {stem}"
    return stem

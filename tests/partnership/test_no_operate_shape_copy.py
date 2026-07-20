"""Enforce partnership voice — no operate-shape copy in prompts or UI strings.

Forbidden strings are the tell of a tool relationship, not a partnership.
This test fails the build when operate-shape language appears in any ACE-
generated string: prompt templates, voice transformers, UI copy.

See docs/voice-style-guide.md for the full rule set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Strings that signal "you are operating a tool" rather than "we are partners"
FORBIDDEN_PRODUCT_COPY = [
    "Welcome!",
    "Get started",
    "Click here",
    "Tutorial",
    "Onboarding",
    "Loading...",
    "Processing...",
    "Thinking...",
    "Please wait",
    "[INFO]",
    "[ERROR]",
    "Successfully created",
    "Successfully updated",
    "Sign up",
    "New conversation",
    "Start a new chat",
    "Clear chat",
    "Session ended",
    "Session started",
    "Reset conversation",
]

# Paths that contain ACE-generated strings
_SCAN_PATHS = [
    Path("engine/synthesis/templates"),
    Path("core/engine/sentinel/engines"),
    Path("core/engine/proactive"),
    Path("core/engine/voice"),
    Path("core/engine/handoff"),
    Path("engine/pushback"),
    Path("portal/src/lib"),
]

_EXTENSIONS = {".py", ".md", ".ts", ".tsx"}


def _collect_files() -> list[Path]:
    files: list[Path] = []
    for base in _SCAN_PATHS:
        if base.exists():
            for ext in _EXTENSIONS:
                files.extend(base.rglob(f"*{ext}"))
    return files


# Lines tagged with this marker are exempt from the audit. Use sparingly — only
# for files that legitimately *reference* forbidden strings as part of their
# purpose (e.g. defining the canonical forbidden list, or instructing the model
# "never say [INFO]"). The marker must appear on the same line as the violation.
_AUDIT_EXEMPT_MARKER = "voice-audit:exempt"


def test_no_forbidden_strings_in_product_copy() -> None:
    """No operate-shape copy in ACE prompt templates or UI strings."""
    files = _collect_files()
    if not files:
        pytest.skip("No ACE-generated string files found yet — skipping until C4 paths exist")

    violations: list[tuple[str, str, int]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for forbidden in FORBIDDEN_PRODUCT_COPY:
            if forbidden not in text:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if forbidden not in line:
                    continue
                if _AUDIT_EXEMPT_MARKER in line:
                    continue
                # "Never use: X, Y, Z" / "NEVER say ..." instruction lines
                # legitimately list forbidden strings to constrain LLM output —
                # they are not themselves forbidden output.
                lower = line.lower()
                if "never use" in lower or "never say" in lower:
                    continue
                violations.append((str(path), forbidden, lineno))

    if violations:
        lines = "\n".join(f"  {p}:{lineno}: '{s}'" for p, s, lineno in violations)
        pytest.fail(
            f"Operate-shape copy found in ACE-generated strings:\n{lines}\n"
            f"See docs/voice-style-guide.md — replace with partnership voice.\n"
            f"If a line must reference a forbidden string by purpose (e.g. listing "
            f"it as forbidden), add a `# {_AUDIT_EXEMPT_MARKER}` comment to the line."
        )

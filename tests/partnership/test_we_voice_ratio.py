"""Enforce we:I voice ratio in ACE-generated strings.

ACE speaks as a partner, not a tool. "We/our/us" must dominate "I/you/your"
across prompt templates and voice transformer outputs by a ratio of > 3:1.

See docs/voice-style-guide.md — allowed exceptions: pushback dissent ("I'd
push back — we agreed...") and confidence texture ("I'm not sure about this").
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Templates that contain ACE_VOICE_TEMPLATE = """...""" pattern
_TEMPLATE_PATTERN = re.compile(r'ACE_VOICE_TEMPLATE\s*=\s*"""(.*?)"""', re.DOTALL)

_TEMPLATE_DIRS = [
    Path("engine/synthesis/templates"),
]

_VOICE_SOURCE_DIRS = [
    Path("core/engine/proactive"),
    Path("core/engine/handoff"),
    Path("engine/pushback"),
    Path("core/engine/sentinel/engines"),
]

_WE_PATTERN = re.compile(r"\b(we|our|us)\b", re.IGNORECASE)
_IY_PATTERN = re.compile(r"\b(i|you|your)\b", re.IGNORECASE)

MINIMUM_RATIO = 3.0


def _collect_ace_voice_strings() -> list[tuple[str, str]]:
    """Return (path, text) pairs for every ACE-generated string."""
    results: list[tuple[str, str]] = []

    # Full .md template files
    for d in _TEMPLATE_DIRS:
        if d.exists():
            for f in d.rglob("*.md"):
                results.append((str(f), f.read_text(encoding="utf-8", errors="ignore")))

    # ACE_VOICE_TEMPLATE embedded strings in Python source
    for d in _VOICE_SOURCE_DIRS:
        if d.exists():
            for f in d.rglob("*.py"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                for match in _TEMPLATE_PATTERN.finditer(text):
                    results.append((str(f), match.group(1)))

    return results


def test_we_voice_ratio_above_threshold() -> None:
    """ACE voice ratio (we:I) must be > 3.0 across all templates."""
    strings = _collect_ace_voice_strings()
    if not strings:
        pytest.skip("No ACE voice templates found yet — skipping until synthesis templates exist")

    we_count = 0
    iy_count = 0
    for _, text in strings:
        we_count += len(_WE_PATTERN.findall(text))
        iy_count += len(_IY_PATTERN.findall(text))

    if iy_count == 0:
        return  # All "we" — passing trivially

    ratio = we_count / iy_count
    assert ratio > MINIMUM_RATIO, (
        f"ACE voice ratio (we:I) is {ratio:.2f} — must be > {MINIMUM_RATIO}. "
        f"we/our/us={we_count}, I/you/your={iy_count}. "
        f"Run: grep -rn '\\\\bI\\\\b\\|\\\\byou\\\\b' engine/synthesis/templates/ "
        f"to find offending strings. See docs/voice-style-guide.md."
    )

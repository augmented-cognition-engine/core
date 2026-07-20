"""Extract user-visible static string literals from partner-voice .tsx components.

Used by the voice-audit registry to score the `drawer` surface against the
chrome strings shipped in BriefingDrawer + sibling components. Pragmatic
regex extraction — focuses on:
  1. JSX text content (text between `>` and `<` tags) — the most user-visible
  2. Double-quoted single-line string literals that LOOK like prose

Strings missed here are not gated; future runtime-rendered surfaces will catch
them. This extractor is one gate in a defense-in-depth strategy, not the only
one.
"""

from __future__ import annotations

import re
from pathlib import Path

# Resolves to the ACE repo root regardless of where this module is loaded from.
# core/engine/voice/static_copy_extractor.py is 4 parents deep from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PARTNER_VOICE_DIR = _REPO_ROOT / "portal" / "src" / "components" / "partner-voice"

# JSX text content: anything between a closing `>` and an opening `<` that
# isn't itself JSX syntax. Capture group is the inner text.
_JSX_TEXT = re.compile(r">\s*([^<>{}\n][^<>{}\n]{8,}?)\s*<")

# Single-line double-quoted string literal (no embedded newline, no escape).
# Min length 10 chars to skip things like "\n", "px", "true".
_DOUBLE_QUOTED = re.compile(r'"((?:[^"\\\n]){10,})"')

# Single-line single-quoted string literal — for cases like 'open · raised this week'.
_SINGLE_QUOTED = re.compile(r"'((?:[^'\\\n]){10,})'")

# Strings matching any of these are framework/syntax noise.
_NOISE_EXACT = {
    "use client",
    "use server",
    "react",
    "use strict",
}
_NOISE_SUBSTRINGS = (
    "var(--",
    "rgba(",
    "rgb(",
    "px ",
    "rem ",
    "ease-",
    "infinite",
    "monospace",
    "linear-gradient",
    "1fr",
    "border-",
    "@/",
    "./",
    "../",
)


def _looks_like_code(s: str) -> bool:
    """Heuristic: does this string contain TS/TSX syntax markers?"""
    code_markers = ("=>", "{{", "}}", "${", "&&", "||", "::", "===", "!==", "//", "/*")
    return any(m in s for m in code_markers)


def _looks_like_classname(s: str) -> bool:
    """Tailwind-style multi-token class strings: 3+ space-separated tokens, no punctuation."""
    tokens = s.split()
    if len(tokens) < 3:
        return False
    # Real prose has sentence punctuation; class strings don't.
    if any(c in s for c in ".?!,—"):
        return False
    # Tailwind tokens are mostly hyphenated lowercase.
    hyphen_lower = sum(1 for t in tokens if t.islower() and "-" in t)
    return hyphen_lower >= len(tokens) // 2


def _is_user_copy(s: str) -> bool:
    """Heuristic: does this string look like user-visible copy vs framework noise?"""
    s_stripped = s.strip()
    if not s_stripped or s_stripped.lower() in _NOISE_EXACT:
        return False
    s_lower = s_stripped.lower()
    if any(sub in s_lower for sub in _NOISE_SUBSTRINGS):
        return False
    if _looks_like_code(s_stripped):
        return False
    if _looks_like_classname(s_stripped):
        return False
    # Filter pure path/url/identifier candidates (no spaces or punctuation).
    if " " not in s_stripped and not any(c in s_stripped for c in ".?!,—"):
        return False
    # JS object-literal fragments like ", letterSpacing:" or trailing ":" / "{".
    if s_stripped.startswith((", ", "{ ", "} ")) or s_stripped.endswith((":", "{", "}")):
        return False
    # Strings ending mid-word (apostrophe-split escapes) — heuristic: if the
    # last character is a lowercase letter and the string contains no sentence
    # punctuation, skip. Real prose ends in a punctuation mark or capital.
    if s_stripped[-1].islower() and not any(c in s_stripped for c in ".?!→·") and len(s_stripped) < 25:
        return False
    return True


def extract_partner_voice_strings() -> list[str]:
    """Return user-visible static strings across partner-voice/ .tsx files.

    Excludes __tests__/ and any *.test.tsx files. Returns empty list if the
    directory is missing (acceptable in dev environments without portal).
    """
    if not _PARTNER_VOICE_DIR.exists():
        return []
    out: list[str] = []
    for tsx in sorted(_PARTNER_VOICE_DIR.rglob("*.tsx")):
        if "__tests__" in tsx.parts or tsx.name.endswith(".test.tsx"):
            continue
        try:
            text = tsx.read_text(encoding="utf-8")
        except OSError:
            continue
        seen_in_file: set[str] = set()
        for pattern in (_JSX_TEXT, _DOUBLE_QUOTED, _SINGLE_QUOTED):
            for match in pattern.findall(text):
                # Collapse whitespace so JSX text with surrounding indentation
                # normalizes to its rendered form.
                normalized = " ".join(match.split())
                if normalized in seen_in_file:
                    continue
                if _is_user_copy(normalized):
                    seen_in_file.add(normalized)
                    out.append(normalized)
    return out

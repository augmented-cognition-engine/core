"""Python mirror of the canvas design-system enforcement battery
(core/ui/canvas/src/design/__enforcement__/). A fast, in-process, worktree-friendly regex gate
for the Design arm's critic — run_tests cannot run the canonical TS vitest suite in a worktree
(no node_modules, no env), so this mirrors its regex rules for effective in-loop repair. The TS
suite remains the source of truth at merge/CI. Each rule names its source test."""

from __future__ import annotations

import os
import re

# (label, compiled regex) — each mirrors a rule in design/__enforcement__/.
_RULES = [
    (
        "inline hex color literal (use var(--ace-*))",  # noInlineStyleHex.test.ts
        re.compile(r"""['"`]#[0-9a-fA-F]{3,8}['"`]"""),
    ),
    (
        "inline rgba() literal (use a token)",  # noInlineStyleHex.test.ts
        re.compile(r"rgba\(\s*\d"),
    ),
    (
        "native <input> (use design-system Input)",  # noInlineFormElements.test.ts
        re.compile(r"<input[\s>/]"),
    ),
    (
        "native <textarea> (use Textarea)",  # noInlineFormElements.test.ts
        re.compile(r"<textarea[\s>/]"),
    ),
    (
        "native <select> (use Select)",  # noInlineFormElements.test.ts
        re.compile(r"<select[\s>/]"),
    ),
    (
        "native <button> (use Button)",  # noInlineFormElements.test.ts
        re.compile(r"<button[\s>/]"),
    ),
    (
        "direct @radix-ui import (use design/components wrapper)",  # noRadixImports.test.ts
        re.compile(r"""(from\s+['"`]@radix-ui/|import\s+['"`]@radix-ui/)"""),
    ),
    (
        "inline borderLeft (use ContributionLane/VoiceCallout/...)",  # noInlineBorderLeft.test.ts
        re.compile(r"\bborderLeft(Color|Style|Width)?\s*:"),
    ),
    (
        "emoji in JSX/TS (use Glyph/Icon)",  # noEmojiInJsx.test.ts
        re.compile("[\U0001f300-\U0001faff✨✅❌⚠]"),
    ),
    (
        "white/light text on a light surface (invisible text)",  # noLightTextOnLightCard.test.ts
        re.compile(
            r"(?=.*(?:bg-(?:anchor|card|background)\b|bg-(?:brand|success|live)/))"
            r"(?=.*\btext-(?:primary-foreground|white|background)\b)"
        ),
    ),
]

# Deferred to the canonical TS suite at merge/CI (not cleanly regex-portable in-loop):
# contrastAA.test.ts (numeric WCAG ratios), tokensContract.test.ts (cross-file tokens.css<->
# tokens.ts), noExtensionLeakage.test.ts (camelCase brand-boundary lookbehind). The TS battery
# runs where node_modules + the full suite exist; the rules above are the fast in-loop mirror.

_EXCLUDE_DIRS = {"node_modules", "dist", "build", ".git", "__enforcement__", "__tests__"}
_EXTS = (".tsx", ".ts")


def scan_design_violations(root: str) -> list[str]:
    """Return human-readable violations found under root (file:line label). Empty == clean."""
    violations: list[str] = []
    if not root or not os.path.isdir(root):
        return violations
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
        for fn in filenames:
            if not fn.endswith(_EXTS):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        for label, rx in _RULES:
                            if rx.search(line):
                                rel = os.path.relpath(path, root)
                                violations.append(f"{rel}:{lineno} {label}")
            except (OSError, UnicodeDecodeError):
                continue
    return violations

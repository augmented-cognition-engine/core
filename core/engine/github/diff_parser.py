# engine/github/diff_parser.py
"""Parse unified diffs into structured FileDiff objects."""

from __future__ import annotations

import re

from core.engine.github.models import DiffHunk, FileDiff

# Matches: diff --git a/<path> b/<path>
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$")

# Matches: @@ -old_start[,old_count] +new_start[,new_count] @@ [header]
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def parse_diff(diff_text: str) -> list[FileDiff]:
    """Parse a unified diff string into a list of FileDiff objects.

    Handles:
    - Standard modifications
    - New files (``new file mode``)
    - Deleted files (``deleted file mode``)
    - Renamed files (``rename from / rename to``)
    - Multiple hunks per file
    - Addition / deletion line counts
    """
    if not diff_text or not diff_text.strip():
        return []

    files: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk: DiffHunk | None = None

    for line in diff_text.splitlines():
        # ── New file section ──────────────────────────────────────────────
        diff_match = _DIFF_HEADER_RE.match(line)
        if diff_match:
            # Flush previous hunk / file
            if current_hunk is not None and current_file is not None:
                current_file.hunks.append(current_hunk)
                current_hunk = None
            if current_file is not None:
                files.append(current_file)

            old_path_raw = diff_match.group(1)
            new_path_raw = diff_match.group(2)
            current_file = FileDiff(path=new_path_raw, old_path=old_path_raw)
            continue

        if current_file is None:
            continue

        # ── File status markers ───────────────────────────────────────────
        if line.startswith("new file mode"):
            current_file.status = "added"
            continue

        if line.startswith("deleted file mode"):
            current_file.status = "deleted"
            continue

        if line.startswith("rename from "):
            current_file.old_path = line[len("rename from ") :]
            current_file.status = "renamed"
            continue

        if line.startswith("rename to "):
            current_file.path = line[len("rename to ") :]
            continue

        # ── Hunk header ───────────────────────────────────────────────────
        hunk_match = _HUNK_HEADER_RE.match(line)
        if hunk_match:
            if current_hunk is not None:
                current_file.hunks.append(current_hunk)

            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4)) if hunk_match.group(4) is not None else 1
            header = hunk_match.group(5).strip()

            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                header=header,
            )
            continue

        # ── Diff content lines ────────────────────────────────────────────
        if current_hunk is not None:
            if line.startswith("+") and not line.startswith("+++"):
                current_hunk.lines.append(line)
                current_file.additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                current_hunk.lines.append(line)
                current_file.deletions += 1
            elif line.startswith(" "):
                current_hunk.lines.append(line)
            # lines like "\ No newline at end of file" are silently ignored

    # Flush last hunk and file
    if current_hunk is not None and current_file is not None:
        current_file.hunks.append(current_hunk)
    if current_file is not None:
        files.append(current_file)

    return files

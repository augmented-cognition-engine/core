"""Local-source change detection (PI7).

Diffs two acquisition inventories — the previous scan and the current one — into the change set a
revision engine needs: which files were added, modified, removed, or left unchanged since last
time. "Modified" is detected by a content-digest mismatch, not a timestamp, so a rewritten file
with identical bytes is correctly unchanged and a touched-but-identical file raises no revision.

This is the pure detection primitive for J6's append-only "what changed and why" revision. It reads
no files and holds no clock; it operates on `AcquiredLocalFile` records the acquisition port
already produced.
"""

from __future__ import annotations

from dataclasses import dataclass

from ace.application.local_source_acquisition import AcquiredLocalFile


@dataclass(frozen=True, slots=True)
class AcquisitionChangeSet:
    """What changed between two acquisition inventories, by workspace-relative path."""

    added: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.removed)


def diff_acquisitions(
    previous: tuple[AcquiredLocalFile, ...],
    current: tuple[AcquiredLocalFile, ...],
) -> AcquisitionChangeSet:
    """Diff two acquisition inventories into added/modified/removed/unchanged paths."""
    prev_by_path = {f.relative_path: f for f in previous}
    curr_by_path = {f.relative_path: f for f in current}

    added: list[str] = []
    modified: list[str] = []
    unchanged: list[str] = []
    for path, curr_file in curr_by_path.items():
        prev_file = prev_by_path.get(path)
        if prev_file is None:
            added.append(path)
        elif prev_file.byte_digest != curr_file.byte_digest:
            modified.append(path)
        else:
            unchanged.append(path)

    removed = [path for path in prev_by_path if path not in curr_by_path]

    return AcquisitionChangeSet(
        added=tuple(sorted(added)),
        modified=tuple(sorted(modified)),
        removed=tuple(sorted(removed)),
        unchanged=tuple(sorted(unchanged)),
    )

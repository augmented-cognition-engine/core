"""Read-only repository-layout helpers used by portable test harnesses."""

from __future__ import annotations

from pathlib import Path


def source_revision(root: Path) -> str:
    """Resolve HEAD in ordinary checkouts and linked worktrees without invoking git."""

    marker = root / ".git"
    if marker.is_dir():
        git_dir = marker
    else:
        declaration = marker.read_text(encoding="utf-8").strip()
        if not declaration.startswith("gitdir: "):
            raise ValueError(".git file must declare one gitdir")
        declared = Path(declaration.removeprefix("gitdir: "))
        git_dir = (root / declared).resolve() if not declared.is_absolute() else declared.resolve()
    common_dir = git_dir
    common_marker = git_dir / "commondir"
    if common_marker.exists():
        declared_common = Path(common_marker.read_text(encoding="utf-8").strip())
        common_dir = (
            (git_dir / declared_common).resolve() if not declared_common.is_absolute() else declared_common.resolve()
        )
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    ref = head.removeprefix("ref: ")
    for candidate in dict.fromkeys((git_dir, common_dir)):
        loose_ref = candidate / ref
        if loose_ref.exists():
            return loose_ref.read_text(encoding="utf-8").strip()
        packed_refs = candidate / "packed-refs"
        if packed_refs.exists():
            for line in packed_refs.read_text(encoding="utf-8").splitlines():
                if not line.startswith(("#", "^")) and line.endswith(f" {ref}"):
                    return line.split(" ", 1)[0]
    raise ValueError(f"unable to resolve source revision {ref}")


__all__ = ["source_revision"]

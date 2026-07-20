"""Action executors — the safety core. Every filesystem op is path-confined to the
workspace root; an escape (.. or symlink) raises ExecutionError and writes nothing."""

from __future__ import annotations

import os
from typing import Callable

_EXECUTORS: dict[str, Callable[[str, dict], str]] = {}


class ExecutionError(Exception):
    """A refused/failed executor action (e.g. a path-confinement escape)."""


def register_executor(verb: str):
    def _wrap(fn: Callable[[str, dict], str]) -> Callable[[str, dict], str]:
        _EXECUTORS[verb] = fn
        return fn

    return _wrap


def get_executor(verb: str) -> Callable[[str, dict], str] | None:
    return _EXECUTORS.get(verb)


def _confine(workspace_path: str, rel_path: str) -> str:
    """Resolve rel_path under workspace_path and assert it cannot escape (.. / symlink)."""
    root = os.path.realpath(workspace_path)
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        raise ExecutionError(f"path escape refused: {rel_path}")
    return target


# A rewrite that leaves an existing file below this fraction of its original size is refused. The
# arm writes WHOLE files, and until now it never READ the file it was modifying — so a model that
# guessed could return a stub and silently delete a module. The workspace is reversible, but a build
# that "passed" while gutting a file is precisely the silent catastrophe this codebase keeps finding.
#
# 0.35 is deliberately generous: a real refactor that halves a file still lands (0.5 > 0.35). Only a
# catastrophic gutting — a 3KB module coming back as "# TODO: implement" — is refused.
_MIN_REWRITE_RATIO = 0.35
_MIN_GUARDED_SIZE = 200  # bytes; below this a file is too small for the ratio to mean anything


@register_executor("write_file")
def write_file(workspace_path: str, args: dict) -> str:
    target = _confine(workspace_path, args["path"])
    content = args.get("content", "")

    # Modifying an existing file? Refuse to gut it. (Creating one is unguarded — nothing to protect.)
    if os.path.exists(target):
        try:
            with open(target) as f:
                original = f.read()
        except Exception:  # unreadable (binary, permissions) — nothing to compare, let the write run
            original = ""
        if len(original) >= _MIN_GUARDED_SIZE and len(content) < len(original) * _MIN_REWRITE_RATIO:
            raise ValueError(
                f"refusing to write {args['path']}: it would truncate the file from {len(original)} "
                f"to {len(content)} bytes ({len(content) / max(1, len(original)):.0%} of the original). "
                "A whole-file write that shrinks a module this much is a fragment, not an edit — "
                "return the file's COMPLETE new content."
            )

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w") as f:
        f.write(content)
    return f"wrote {args['path']}"


@register_executor("read_file")
def read_file(workspace_path: str, args: dict) -> str:
    target = _confine(workspace_path, args["path"])
    with open(target) as f:
        return f.read()

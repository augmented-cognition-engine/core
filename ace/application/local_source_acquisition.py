"""Governed local-source acquisition port.

This is the trust boundary for reading a person's authorized local files. It owns the
security-sensitive plumbing so no third-party adapter has to: walking an authorized folder,
enforcing read-only access and include/exclude scope, refusing paths that escape the root,
digesting exact bytes, and dispatching each file to an injected format adapter.

It imports no adapter package. The caller injects a ``dispatch`` callable that maps a file
extension and its bytes to a JSON-serializable structured payload (or ``None`` for an unsupported
format). The port produces one :class:`AcquiredLocalFile` per file — including unsupported files,
which are inventoried with a digest but no payload — for the admission layer to wrap into the
canonical recorded-source material. See
docs/design/personal-intelligence-local-source-adapters-v1.md.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ace.core.contracts import canonical_json

Dispatch = Callable[[str, bytes], object | None]


@dataclass(frozen=True, slots=True)
class AcquiredLocalFile:
    """One authorized local file read under the governed acquisition contract."""

    relative_path: str
    extension: str
    byte_digest: str
    size_bytes: int
    status: Literal["acquired", "unsupported"]
    structured_payload_json: str | None


def _glob_files(root: Path, patterns: tuple[str, ...]) -> set[Path]:
    matched: set[Path] = set()
    for pattern in patterns:
        matched.update(p for p in root.glob(pattern) if p.is_file())
    return matched


def acquire_local_folder(
    root: str | Path,
    *,
    dispatch: Dispatch,
    include: tuple[str, ...] = ("**/*",),
    exclude: tuple[str, ...] = (),
) -> tuple[AcquiredLocalFile, ...]:
    """Read an authorized local folder into acquired-file records, read-only.

    Files are selected by ``include`` and removed by ``exclude`` (glob patterns relative to
    ``root``, with ``**`` matching any depth). A path whose real location escapes ``root`` — for
    example a symlink to an external file — is never read. Results are deterministic, ordered by
    relative path.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        raise ValueError(f"local source root is not a directory: {root_path}")
    real_root = root_path.resolve()

    selected = _glob_files(root_path, include) - _glob_files(root_path, exclude)

    acquired: list[AcquiredLocalFile] = []
    for path in sorted(selected):
        # Refuse anything whose real path escapes the authorized root (symlink escape).
        try:
            path.resolve().relative_to(real_root)
        except (OSError, ValueError):
            continue

        content = path.read_bytes()
        extension = path.suffix.lower().lstrip(".")
        payload = dispatch(extension, content)
        acquired.append(
            AcquiredLocalFile(
                relative_path=path.relative_to(root_path).as_posix(),
                extension=extension,
                byte_digest="sha256:" + hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
                status="acquired" if payload is not None else "unsupported",
                structured_payload_json=canonical_json(payload) if payload is not None else None,
            )
        )

    acquired.sort(key=lambda f: f.relative_path)
    return tuple(acquired)

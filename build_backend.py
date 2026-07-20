"""Setuptools backend wrapper with reproducible source distributions.

Setuptools already applies ``SOURCE_DATE_EPOCH`` to wheels, but its sdist
command records build-time directory metadata, host ownership, and a live gzip
timestamp.  Normalize the completed archive when the caller explicitly opts
into reproducible builds with ``SOURCE_DATE_EPOCH``.
"""

from __future__ import annotations

import gzip
import os
import tarfile
import tempfile
from pathlib import Path

from setuptools.build_meta import (  # noqa: F401
    build_editable,
    build_wheel,
    get_requires_for_build_editable,
    get_requires_for_build_sdist,
    get_requires_for_build_wheel,
    prepare_metadata_for_build_editable,
    prepare_metadata_for_build_wheel,
)
from setuptools.build_meta import (
    build_sdist as _setuptools_build_sdist,
)


def _normalized_mode(member: tarfile.TarInfo) -> int:
    if member.isdir():
        return 0o755
    if member.issym() or member.islnk():
        return 0o777
    return 0o755 if member.mode & 0o111 else 0o644


def _normalize_sdist(path: Path, epoch: int) -> None:
    """Rewrite *path* with stable tar and gzip metadata."""

    path = path.resolve()
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tar.gz", delete=False) as output:
        temporary = Path(output.name)
        try:
            with (
                tarfile.open(path, mode="r:gz") as source,
                gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=epoch) as compressed,
                tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as target,
            ):
                for member in source.getmembers():
                    member.uid = 0
                    member.gid = 0
                    member.uname = ""
                    member.gname = ""
                    member.mtime = epoch
                    member.mode = _normalized_mode(member)
                    member.pax_headers = {}
                    payload = source.extractfile(member) if member.isfile() else None
                    target.addfile(member, payload)
            output.flush()
            os.fsync(output.fileno())
            os.replace(temporary, path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise


def build_sdist(sdist_directory: str, config_settings: dict | None = None) -> str:
    """Build with setuptools, then normalize when a fixed epoch is requested."""

    filename = _setuptools_build_sdist(sdist_directory, config_settings)
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if raw_epoch is not None:
        epoch = int(raw_epoch)
        if epoch < 0:
            raise ValueError("SOURCE_DATE_EPOCH must be non-negative")
        _normalize_sdist(Path(sdist_directory) / filename, epoch)
    return filename

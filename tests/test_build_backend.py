from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import build_backend


def _write_archive(path: Path, *, timestamp: int, uid: int, username: str) -> None:
    with (
        path.open("wb") as output,
        gzip.GzipFile(filename=path.name, mode="wb", fileobj=output, mtime=timestamp) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        directory = tarfile.TarInfo("demo")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o775
        directory.mtime = timestamp
        directory.uid = uid
        directory.uname = username
        archive.addfile(directory)

        content = b"release candidate\n"
        member = tarfile.TarInfo("demo/README.md")
        member.size = len(content)
        member.mode = 0o664
        member.mtime = timestamp
        member.uid = uid
        member.uname = username
        archive.addfile(member, io.BytesIO(content))


def test_sdist_normalization_removes_time_and_owner_variance(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_archive(first, timestamp=100, uid=501, username="first")
    _write_archive(second, timestamp=200, uid=1000, username="second")

    build_backend._normalize_sdist(first, 123456789)
    build_backend._normalize_sdist(second, 123456789)

    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first) as archive:
        for member in archive.getmembers():
            assert member.mtime == 123456789
            assert member.uid == 0
            assert member.gid == 0
            assert member.uname == ""
            assert member.gname == ""

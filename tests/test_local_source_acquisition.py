"""Tests for the governed local-source acquisition port.

The port owns the security-sensitive plumbing — walking an authorized folder, enforcing read-only
and include/exclude scope, digesting exact bytes, and dispatching to an injected format adapter.
It imports no adapter package; the parser is injected.
"""

import hashlib
import json

from ace.application.local_source_acquisition import AcquiredLocalFile, acquire_local_folder


def _echo_dispatch(extension: str, content: bytes) -> dict | None:
    """A fake adapter: 'txt'/'md' are supported and echo their text; others are unsupported."""
    if extension in {"txt", "md"}:
        return {"text": content.decode("utf-8")}
    return None


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def test_one_record_per_file_with_relative_path_and_extension(tmp_path):
    (tmp_path / "a.txt").write_text("alpha")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("beta")

    files = acquire_local_folder(tmp_path, dispatch=_echo_dispatch)

    assert [f.relative_path for f in files] == ["a.txt", "sub/b.md"]
    assert [f.extension for f in files] == ["txt", "md"]


def test_byte_digest_is_sha256_of_exact_bytes(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"alpha")
    (file,) = acquire_local_folder(tmp_path, dispatch=_echo_dispatch)
    assert file.byte_digest == _sha(b"alpha")
    assert file.size_bytes == 5


def test_supported_file_carries_dispatch_output_as_canonical_json(tmp_path):
    (tmp_path / "a.txt").write_text("alpha")
    (file,) = acquire_local_folder(tmp_path, dispatch=_echo_dispatch)
    assert file.status == "acquired"
    assert json.loads(file.structured_payload_json) == {"text": "alpha"}


def test_unsupported_file_is_inventoried_without_a_payload(tmp_path):
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    (file,) = acquire_local_folder(tmp_path, dispatch=_echo_dispatch)
    assert file.status == "unsupported"
    assert file.structured_payload_json is None
    assert file.byte_digest == _sha(b"\x89PNG")  # digest still computed for the inventory


def test_exclude_globs_filter_files(tmp_path):
    (tmp_path / "keep.txt").write_text("k")
    (tmp_path / "skip.txt").write_text("s")
    files = acquire_local_folder(tmp_path, dispatch=_echo_dispatch, exclude=("skip.txt",))
    assert [f.relative_path for f in files] == ["keep.txt"]


def test_results_are_sorted_by_relative_path(tmp_path):
    for name in ("c.txt", "a.txt", "b.txt"):
        (tmp_path / name).write_text(name)
    files = acquire_local_folder(tmp_path, dispatch=_echo_dispatch)
    assert [f.relative_path for f in files] == ["a.txt", "b.txt", "c.txt"]


def test_symlink_escaping_the_root_is_not_read(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret")
    root = tmp_path / "root"
    root.mkdir()
    (root / "here.txt").write_text("here")
    (root / "escape.txt").symlink_to(secret)

    files = acquire_local_folder(root, dispatch=_echo_dispatch)

    assert [f.relative_path for f in files] == ["here.txt"]


def test_missing_root_is_refused(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        acquire_local_folder(tmp_path / "does-not-exist", dispatch=_echo_dispatch)


def test_file_as_root_is_refused(tmp_path):
    import pytest

    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(ValueError):
        acquire_local_folder(f, dispatch=_echo_dispatch)


def test_returned_records_are_the_acquired_local_file_type(tmp_path):
    (tmp_path / "a.txt").write_text("alpha")
    (file,) = acquire_local_folder(tmp_path, dispatch=_echo_dispatch)
    assert isinstance(file, AcquiredLocalFile)

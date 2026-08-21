"""WS1 tests for the local ``source_snapshot`` capability provider.

The provider is a zero-argument composition seam: its identity pins the exact source bytes of
its own module, registration goes through the public ace-core validator, and a snapshot only
forwards the revalidated request scope to the governed acquisition port with the normalizer
dispatch. The real-folder tests exercise that composition end to end over the four supported
formats without any network or provider model.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os.path
from pathlib import Path

import ace_local_source_snapshot.provider as provider_module
import pytest
from ace_local_source_snapshot.provider import (
    LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_ID,
    LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_VERSION,
    LocalSourceSnapshotProvider,
    _dispatch_source_units,
)

from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.source_snapshot_provider import (
    SOURCE_SNAPSHOT_CAPABILITY,
    SOURCE_SNAPSHOT_CONTRACT,
    SourceSnapshotRequestV1Alpha1,
    validate_source_snapshot_provider_registration,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_PDF = _REPO_ROOT / "tests" / "fixtures" / "pi13_ws0" / "sample.pdf"

_MARKDOWN = b"# Notes\nalpha\n"
_CSV = b"name,role\nAda,eng\n"
_JSON = b'{"project": "ace"}'

_SENTINEL_FILES = (
    AcquiredLocalFile(
        relative_path="notes/a.md",
        extension="md",
        byte_digest="sha256:" + "0" * 64,
        size_bytes=5,
        status="acquired",
        structured_payload_json="[]",
    ),
)


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _snapshot(root: Path, **overrides) -> tuple[AcquiredLocalFile, ...]:
    material = {"authorized_root": str(root), "include": ("**/*",)}
    material.update(overrides)
    request = SourceSnapshotRequestV1Alpha1(**material)
    return asyncio.run(LocalSourceSnapshotProvider().snapshot(request))


def test_artifact_identity_pins_the_exact_provider_source_digest() -> None:
    identity = LocalSourceSnapshotProvider.artifact_identity
    assert identity.capability == SOURCE_SNAPSHOT_CAPABILITY == "source_snapshot"
    assert identity.contract == SOURCE_SNAPSHOT_CONTRACT == "ace.source.snapshot/v1alpha1"
    assert identity.implementation_id == LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_ID == "local_source_snapshot"
    assert identity.implementation_version == LOCAL_SOURCE_SNAPSHOT_IMPLEMENTATION_VERSION == "0.1.0"
    assert identity.artifact_digest == _sha(Path(provider_module.__file__).read_bytes())


def test_public_registration_validator_accepts_the_provider() -> None:
    artifact = validate_source_snapshot_provider_registration(LocalSourceSnapshotProvider())
    assert artifact == LocalSourceSnapshotProvider.artifact_identity
    assert artifact is not LocalSourceSnapshotProvider.artifact_identity


def test_construction_never_invokes_the_acquisition_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_module,
        "acquire_local_folder",
        lambda *args, **kwargs: pytest.fail("constructing the provider must not read anything"),
    )
    provider = LocalSourceSnapshotProvider()
    assert isinstance(provider, LocalSourceSnapshotProvider)


def test_snapshot_forwards_the_revalidated_scope_to_the_acquisition_port_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def record(root, *, dispatch, include, exclude):
        calls.append({"root": root, "dispatch": dispatch, "include": include, "exclude": exclude})
        return _SENTINEL_FILES

    monkeypatch.setattr(provider_module, "acquire_local_folder", record)
    request = SourceSnapshotRequestV1Alpha1(
        authorized_root="/authorized/notes",
        include=("**/*.md", "**/*.csv"),
        exclude=("z/**", "a/**"),
    )

    result = asyncio.run(LocalSourceSnapshotProvider().snapshot(request))

    assert result is _SENTINEL_FILES
    (call,) = calls
    assert call["root"] == "/authorized/notes"
    assert os.path.isabs(call["root"])
    assert call["dispatch"] is _dispatch_source_units
    assert call["include"] == ("**/*.csv", "**/*.md")
    assert call["exclude"] == ("a/**", "z/**")
    assert _dispatch_source_units("txt", b"x") is None


def test_snapshot_acquires_all_four_formats_with_structured_payloads_read_only(tmp_path) -> None:
    pdf_bytes = _SAMPLE_PDF.read_bytes()
    originals = {
        "notes.md": _MARKDOWN,
        "table.csv": _CSV,
        "data.json": _JSON,
        "sample.pdf": pdf_bytes,
    }
    for name, content in originals.items():
        (tmp_path / name).write_bytes(content)

    files = _snapshot(tmp_path)

    assert [f.relative_path for f in files] == ["data.json", "notes.md", "sample.pdf", "table.csv"]
    by_path = {f.relative_path: f for f in files}
    for name, content in originals.items():
        assert by_path[name].status == "acquired"
        assert by_path[name].byte_digest == _sha(content)
        assert by_path[name].size_bytes == len(content)
        # Acquisition is read-only: the source bytes are untouched by the snapshot.
        assert (tmp_path / name).read_bytes() == content

    assert json.loads(by_path["notes.md"].structured_payload_json) == [
        {"anchor_kind": "heading", "anchor_value": "Notes", "text": "alpha"}
    ]
    assert json.loads(by_path["table.csv"].structured_payload_json) == [
        {"anchor_kind": "row", "anchor_value": "1", "text": "name: Ada | role: eng"}
    ]
    assert json.loads(by_path["data.json"].structured_payload_json) == [
        {"anchor_kind": "pointer", "anchor_value": "/project", "text": "ace"}
    ]
    (pdf_unit,) = json.loads(by_path["sample.pdf"].structured_payload_json)
    assert pdf_unit["anchor_kind"] == "page"
    assert pdf_unit["anchor_value"] == "1"
    assert "PI13 fixture" in pdf_unit["text"]


def test_include_exclude_and_unsupported_inventory_stay_delegated_to_the_port(tmp_path) -> None:
    (tmp_path / "keep.txt").write_bytes(b"kept")
    (tmp_path / "skip.txt").write_bytes(b"skipped")
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")

    files = _snapshot(tmp_path, include=("**/*.txt",), exclude=("skip.txt",))

    (kept,) = files
    assert kept.relative_path == "keep.txt"
    assert kept.status == "unsupported"
    assert kept.structured_payload_json is None
    assert kept.byte_digest == _sha(b"kept")  # digest still computed for the inventory

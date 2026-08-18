"""The shipped Personal Intelligence pack is a discoverable, valid installed distribution (PI5, J2).

This guards that the pack files that ship (domain_packs/personal_intelligence/) form an installed
Domain Pack that ACE's discovery finds and whose manifest validates — the prerequisite for a user
choosing Personal Intelligence in the catalog. It uses a stub distribution over the real files, so
it exercises the exact discovery path without building or installing a wheel.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

from ace.application.installed_pack_artifacts import discover_installed_domain_pack_previews

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACK_DIR = _REPO_ROOT / "domain_packs" / "personal_intelligence"
_WHEEL_PREFIX = "domain_packs/personal_intelligence"


@dataclass
class _Metadata:
    name: str

    def get(self, key: str):
        return self.name if key == "Name" else None


class _StubDistribution:
    """Minimal installed-distribution stub over the real shipped pack files."""

    def __init__(self, root: Path, name: str, version: str) -> None:
        self.root = root
        self.metadata = _Metadata(name)
        self.version = version
        self.files = tuple(
            PurePosixPath(p.relative_to(root).as_posix()) for p in sorted(root.rglob("*")) if p.is_file()
        )

    def locate_file(self, path) -> Path:
        return self.root / str(path)

    @property
    def entry_points(self):
        raise AssertionError("pack discovery must never inspect entry points")


def _staged_pack(tmp_path: Path) -> Path:
    """Stage the real pack files under the wheel-relative path discovery scans."""
    staged_root = tmp_path / "dist"
    dest = staged_root / _WHEEL_PREFIX
    for src in sorted(_PACK_DIR.rglob("*")):
        if not src.is_file() or src.name == "pyproject.toml":
            continue
        target = dest / src.relative_to(_PACK_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
    return staged_root


def test_shipped_manifest_exists_at_the_discovery_path():
    assert (_PACK_DIR / "manifest.json").is_file()


def test_pack_is_discovered_as_an_installed_distribution(tmp_path: Path):
    staged_root = _staged_pack(tmp_path)
    distribution = _StubDistribution(staged_root, "ace-personal-intelligence-pack", "0.1.0")

    previews = discover_installed_domain_pack_previews([distribution])

    matches = [p for p in previews if p.manifest_resource_path == f"{_WHEEL_PREFIX}/manifest.json"]
    assert len(matches) == 1
    preview = matches[0]
    assert preview.distribution == "ace-personal-intelligence-pack"
    assert preview.distribution_version == "0.1.0"
    # The preview validated the manifest as a DomainPackManifestV1; a bad pack would have raised.
    assert preview.manifest is not None

"""PI11: every first-party adapter's ace-core envelope admits the 1.2 release.

The 1.2 packet's hard precondition: the published workspace-action adapter
pinned ``ace-core>=0.8.0,<1.2``, which the 1.2.0 release would break. A new
distribution with a widened envelope ships before or with the release, and
this guard keeps any adapter from regressing to a sub-1.2 ceiling.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
RELEASE_VERSION = Version("1.2.0")


def _adapter_projects() -> dict[str, dict]:
    return {
        path.parent.name: tomllib.loads(path.read_text())["project"]
        for path in sorted((REPO / "adapters").glob("*/pyproject.toml"))
    }


def test_every_adapter_envelope_admits_the_1_2_release() -> None:
    projects = _adapter_projects()
    assert projects, "adapter family missing"
    for directory, project in projects.items():
        ace_core = [Requirement(item) for item in project.get("dependencies", ()) if item.startswith("ace-core")]
        assert ace_core, f"{directory} declares no ace-core dependency"
        for requirement in ace_core:
            assert requirement.specifier.contains(RELEASE_VERSION, prereleases=False), (
                f"{directory} pins {requirement.specifier}, which refuses ace-core {RELEASE_VERSION}"
            )


def test_workspace_action_adapter_is_re_released_with_the_widened_envelope() -> None:
    project = _adapter_projects()["reference_workspace_action"]
    assert Version(project["version"]) >= Version("0.5.0"), (
        "the widened-envelope workspace-action adapter must ship as a new release, not a mutation of 0.4.1"
    )

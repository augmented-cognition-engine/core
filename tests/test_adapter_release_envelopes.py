"""PI11: every first-party ace-core envelope admits the release being cut.

The 1.2 packet's hard precondition: the published workspace-action adapter
pinned ``ace-core>=0.8.0,<1.2``, which the 1.2.0 release would break. A new
distribution with a widened envelope ships before or with the release, and
this guard keeps any first-party project — adapter, pack, or bundle — from
regressing to an envelope that refuses the core released beside it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]

# The packet freezes 1.2.0 as the release this precondition protects. The new
# first-party artifacts ship with that release (never retroactively with 1.1),
# so the guard binds to the release being cut: the root package version once it
# reaches 1.2.0, and never less.
_ROOT_VERSION = Version(tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"])
RELEASE_VERSION = max(_ROOT_VERSION, Version("1.2.0"))


def _first_party_projects() -> dict[str, dict]:
    paths = [
        *sorted((REPO / "adapters").glob("*/pyproject.toml")),
        *sorted((REPO / "domain_packs").glob("*/pyproject.toml")),
        *sorted((REPO / "solution_bundles").glob("*/pyproject.toml")),
    ]
    return {
        f"{path.parent.parent.name}/{path.parent.name}": tomllib.loads(path.read_text())["project"] for path in paths
    }


def _ace_core_requirements(project: dict) -> list[Requirement]:
    requirements = [Requirement(item) for item in project.get("dependencies", ())]
    return [item for item in requirements if canonicalize_name(item.name) == "ace-core"]


def test_every_first_party_envelope_admits_the_release() -> None:
    projects = _first_party_projects()
    assert projects, "first-party project families missing"
    for directory, project in projects.items():
        for requirement in _ace_core_requirements(project):
            assert requirement.specifier.contains(RELEASE_VERSION, prereleases=True), (
                f"{directory} pins {requirement.specifier}, which refuses ace-core {RELEASE_VERSION}"
            )


def test_every_adapter_declares_its_ace_core_dependency() -> None:
    projects = _first_party_projects()
    adapters = {name: project for name, project in projects.items() if name.startswith("adapters/")}
    assert adapters, "adapter family missing"
    for directory, project in adapters.items():
        assert _ace_core_requirements(project), f"{directory} declares no ace-core dependency"


def test_workspace_action_adapter_is_re_released_with_the_widened_envelope() -> None:
    project = _first_party_projects()["adapters/reference_workspace_action"]
    assert Version(project["version"]) >= Version("0.5.0"), (
        "the widened-envelope workspace-action adapter must ship as a new release, not a mutation of 0.4.1"
    )
    # The separate-adapter dependency boundary: exactly one dependency, the
    # ace-core envelope itself (previously enforced only at release time).
    assert project["dependencies"] == ["ace-core>=0.8.0,<2"]

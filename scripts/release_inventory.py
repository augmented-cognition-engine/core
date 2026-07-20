"""Generate a deterministic dependency and license inventory for an ACE install."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import platform
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def _direct_dependencies() -> set[str]:
    direct: set[str] = set()
    for raw in metadata.requires("ace-core") or []:
        requirement = Requirement(raw)
        if requirement.marker is None or requirement.marker.evaluate():
            direct.add(canonicalize_name(requirement.name))
    return direct


def _license_from_installed_file(dist: metadata.Distribution) -> tuple[str | None, str | None]:
    for file in dist.files or []:
        if "license" not in str(file).lower() and "copying" not in str(file).lower():
            continue
        try:
            text = dist.locate_file(file).read_text(errors="replace")[:4096].lower()
        except OSError:
            continue
        for marker, expression in (
            ("apache license", "Apache-2.0"),
            ("mit license", "MIT"),
            ("bsd 3-clause", "BSD-3-Clause"),
            ("bsd 2-clause", "BSD-2-Clause"),
            ("mozilla public license", "MPL-2.0"),
        ):
            if marker in text:
                return expression, str(file)
    return None, None


def build_inventory() -> dict[str, object]:
    direct = _direct_dependencies()
    packages: list[dict[str, object]] = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or "UNKNOWN"
        canonical_name = canonicalize_name(name)
        expression = dist.metadata.get("License-Expression")
        declared = dist.metadata.get("License")
        classifiers = sorted(
            value for value in dist.metadata.get_all("Classifier", []) if value.startswith("License ::")
        )
        if declared and declared.strip().upper() == "UNKNOWN":
            declared = None
        license_file_value, license_file = _license_from_installed_file(dist)
        license_value = (
            expression
            or declared
            or ("; ".join(classifiers) if classifiers else None)
            or license_file_value
            or "UNKNOWN"
        )
        packages.append(
            {
                "name": name,
                "version": dist.version,
                "direct": canonical_name in direct,
                "license": license_value,
                "license_source": (
                    "License-Expression"
                    if expression
                    else "License"
                    if declared
                    else "Classifier"
                    if classifiers
                    else "installed-license-file"
                    if license_file_value
                    else "missing"
                ),
                "license_file": license_file,
            }
        )
    packages.sort(key=lambda item: (str(item["name"]).lower(), str(item["version"])))
    return {
        "schema": "ace-release-inventory-v1",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "package_count": len(packages),
        "unknown_license_count": sum(item["license"] == "UNKNOWN" for item in packages),
        "packages": packages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args()
    payload = json.dumps(build_inventory(), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()

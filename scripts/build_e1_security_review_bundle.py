"""Build a hashed governed-cognition evidence bundle for independent review.

The bundle runs the provider-free security/conformance gates and hashes the
review surface. It always records ``pending_independent_review``; only a human
reviewer outside the implementation workstream can issue the separate signoff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "ace.e1-security-review-bundle/v1"

REVIEW_SURFACE = (
    ".github/workflows/publish.yml",
    "build_backend.py",
    "pyproject.toml",
    "uv.lock",
    "core/engine/api/auth_routes.py",
    "core/engine/api/cognition.py",
    "core/engine/api/reasoning.py",
    "core/engine/api/self_optimizer.py",
    "core/engine/api/skills.py",
    "core/engine/cognition/contracts.py",
    "core/engine/cognition/catalog.py",
    "core/engine/cognition/composer.py",
    "core/engine/cognition/discovery.py",
    "core/engine/cognition/effectiveness.py",
    "core/engine/cognition/governance.py",
    "core/engine/cognition/governance_persistence.py",
    "core/engine/cognition/legacy_adapters.py",
    "core/engine/cognition/legacy_import.py",
    "core/engine/cognition/lifecycle.py",
    "core/engine/cognition/store.py",
    "core/engine/core/auth.py",
    "core/engine/extensions/loader.py",
    "core/engine/extensions/registry.py",
    "core/engine/cognition/instrument_registry.py",
    "extensions/reference/extension.py",
    "core/schema/v169_governed_cognition_catalog.surql",
    "core/schema/v170_governed_cognition_review.surql",
    "core/schema/v171_governed_cognition_use.surql",
    "docs/design/governed-cognition-extension-threat-model-v1.md",
    "docs/evidence/governed-cognition-independent-security-review-template-v1.md",
    "docs/governed-cognition-operations.md",
    "scripts/build_e1_security_review_bundle.py",
    "scripts/run_governed_cognition_legacy_inventory.py",
    "scripts/verify_e1_package_matrix.py",
    "tests/test_api_auth_switch.py",
    "tests/test_api_cognition.py",
    "tests/test_api_reasoning.py",
    "tests/test_api_self_optimizer.py",
    "tests/test_api_skills.py",
    "tests/test_auth.py",
    "tests/test_auth_separation.py",
    "tests/test_governed_cognition_catalog.py",
    "tests/test_governed_cognition_effectiveness.py",
    "tests/test_governed_cognition_extension_conformance.py",
    "tests/test_governed_cognition_governance.py",
    "tests/test_governed_cognition_discovery.py",
    "tests/test_governed_cognition_legacy_facades.py",
    "tests/test_governed_cognition_legacy_import.py",
    "tests/test_governed_cognition_legacy_inventory_command.py",
    "tests/test_governed_cognition_lifecycle.py",
    "tests/test_governed_cognition_restart_persistence.py",
)

GATES = (
    (
        "security_conformance",
        (
            "-m",
            "pytest",
            "tests/test_governed_cognition_extension_conformance.py",
            "tests/test_governed_cognition_governance.py",
            "tests/test_governed_cognition_discovery.py",
            "tests/test_governed_cognition_lifecycle.py",
            "tests/test_api_auth_switch.py",
            "tests/test_api_cognition.py",
            "tests/test_api_reasoning.py",
            "tests/test_api_self_optimizer.py",
            "tests/test_api_skills.py",
            "tests/test_auth.py",
            "tests/test_auth_separation.py",
            "tests/test_governed_cognition_catalog.py",
            "tests/test_governed_cognition_effectiveness.py",
            "tests/test_governed_cognition_legacy_facades.py",
            "tests/test_governed_cognition_legacy_import.py",
            "tests/test_governed_cognition_legacy_inventory_command.py",
            "-q",
            "--tb=short",
        ),
    ),
    (
        "review_surface_lint",
        (
            "-m",
            "ruff",
            "check",
            "core/engine/cognition",
            "core/engine/extensions/registry.py",
            "extensions/reference/extension.py",
            "scripts/build_e1_security_review_bundle.py",
            "tests/test_api_auth_switch.py",
            "tests/test_api_cognition.py",
            "tests/test_auth.py",
            "tests/test_auth_separation.py",
            "tests/test_governed_cognition_catalog.py",
            "tests/test_governed_cognition_discovery.py",
            "tests/test_governed_cognition_effectiveness.py",
            "tests/test_governed_cognition_extension_conformance.py",
            "tests/test_governed_cognition_governance.py",
            "tests/test_governed_cognition_legacy_facades.py",
            "tests/test_governed_cognition_legacy_import.py",
            "tests/test_governed_cognition_legacy_inventory_command.py",
            "tests/test_governed_cognition_lifecycle.py",
            "tests/test_governed_cognition_restart_persistence.py",
        ),
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gate(name: str, arguments: tuple[str, ...]) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        env={**os.environ, "ACE_DISABLE_EXTENSIONS": "1"},
    )
    output = "\n".join(item for item in (result.stdout.strip(), result.stderr.strip()) if item)
    receipt = {
        "name": name,
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "output_tail": output[-4000:],
    }
    if result.returncode != 0:
        raise RuntimeError(f"security review bundle gate failed: {name}\n{output[-4000:]}")
    return receipt


def _write_once(path: Path, payload: dict[str, Any], *, replace: bool) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing security bundle: {path}")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def build_bundle() -> dict[str, Any]:
    files = []
    for relative in REVIEW_SURFACE:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing security review surface: {relative}")
        files.append({"path": relative, "sha256": _sha256(path), "bytes": path.stat().st_size})
    gates = [_gate(name, arguments) for name, arguments in GATES]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    material = {
        "contract_version": CONTRACT,
        "base_commit": head,
        "files": files,
        "gates": gates,
        "review_status": "pending_independent_review",
        "author_workstream_can_approve": False,
    }
    return {
        **material,
        "created_at": datetime.now(UTC).isoformat(),
        "bundle_sha256": hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "required_review_record": "docs/evidence/governed-cognition-independent-security-review-template-v1.md",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace-output", action="store_true")
    args = parser.parse_args(argv)
    bundle = build_bundle()
    _write_once(args.output, bundle, replace=args.replace_output)
    print(
        json.dumps(
            {
                "bundle_sha256": bundle["bundle_sha256"],
                "review_status": bundle["review_status"],
                "file_count": len(bundle["files"]),
                "gates": [{"name": item["name"], "status": item["status"]} for item in bundle["gates"]],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

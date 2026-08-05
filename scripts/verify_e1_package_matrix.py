"""Build and verify the governed-cognition package compatibility matrix.

This verifier is intentionally network-free. It builds the current worktree,
the declared N-1 git tag, and a generated independent consumer, then exercises
wheel/sdist mixes in isolated Python environments. Publication provenance is a
separate release authority; this receipt proves the artifacts themselves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.scaffold_extension import scaffold

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "ace.e1-package-matrix/v1"
CURRENT_COGNITION_CONTRACT = "ace.cognition.revision/v1"
_JWT_SECRET = "e1-package-matrix-local-secret-000000000000"


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=capture,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no subprocess diagnostics").strip()
        raise RuntimeError(f"package matrix command failed ({args[0]}): {detail[-4000:]}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dependency_site() -> Path:
    for value in sys.path:
        path = Path(value)
        if path.name == "site-packages" and (path / "pydantic").is_dir():
            return path.resolve()
    raise RuntimeError("package matrix requires the repository development dependencies")


def _project_version(source: Path) -> str:
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = str(project["version"])
    if not version:
        raise RuntimeError(f"empty project version in {source}")
    return version


def _source_date_epoch(ref: str) -> int:
    result = _run(
        ["git", "log", "-1", "--format=%ct", ref],
        cwd=ROOT,
        capture=True,
    )
    try:
        epoch = int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"invalid commit timestamp for {ref}") from exc
    if epoch < 0:
        raise RuntimeError(f"negative commit timestamp for {ref}")
    return epoch


def _build(source: Path, destination: Path, *, source_date_epoch: int) -> tuple[Path, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
    _run(["uv", "build", "--out-dir", str(destination)], cwd=source, env=env, capture=True)
    wheels = sorted(destination.glob("*.whl"))
    sdists = sorted(destination.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(f"expected one wheel and one sdist in {destination}")
    return wheels[0], sdists[0]


def _create_env(root: Path, name: str) -> tuple[Path, dict[str, str]]:
    target = root / name
    _run([sys.executable, "-m", "venv", "--system-site-packages", str(target)], cwd=root)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_dependency_site())
    env["JWT_SECRET"] = _JWT_SECRET
    return target / "bin" / "python", env


def _pip(python: Path, artifact: Path, *, cwd: Path, env: dict[str, str], sdist: bool = False) -> None:
    command = [str(python), "-m", "pip", "install", "--no-deps"]
    if sdist:
        command.append("--no-build-isolation")
    command.append(str(artifact))
    _run(command, cwd=cwd, env=env, capture=True)


def _probe(python: Path, code: str, *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    result = _run([str(python), "-c", code], cwd=cwd, env=env, capture=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("package matrix probe returned no receipt")
    return json.loads(lines[-1])


def _artifact_exclusions(wheel: Path) -> dict[str, Any]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    forbidden = [
        name
        for name in names
        if "/tests/" in f"/{name}"
        or name.endswith("/.env")
        or Path(name).name == ".env"
        or "credentials" in name.lower()
        or "secrets" in name.lower()
    ]
    if forbidden:
        raise RuntimeError(f"forbidden wheel payloads: {forbidden}")
    return {"status": "passed", "forbidden_payloads": []}


def _extract_tag(tag: str, destination: Path) -> None:
    archive = destination.parent / f"{tag}.tar"
    _run(
        ["git", "archive", "--format=tar", f"--output={archive}", tag],
        cwd=ROOT,
    )
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")


def verify(*, n1_tag: str, output: Path, artifacts_dir: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ace-e1-package-matrix-") as raw_temp:
        temp = Path(raw_temp)
        n1_source = temp / "n1-source"
        n1_source.mkdir()
        _extract_tag(n1_tag, n1_source)
        current_version = _project_version(ROOT)
        n1_version = _project_version(n1_source)
        current_epoch = _source_date_epoch("HEAD")
        n1_epoch = _source_date_epoch(n1_tag)

        current_wheel, current_sdist = _build(
            ROOT,
            temp / "current-dist",
            source_date_epoch=current_epoch,
        )
        n1_wheel, n1_sdist = _build(
            n1_source,
            temp / "n1-dist",
            source_date_epoch=n1_epoch,
        )
        independent_source = scaffold("independent_consumer", temp)
        independent_wheel, independent_sdist = _build(
            independent_source,
            temp / "independent-dist",
            source_date_epoch=current_epoch,
        )

        current_python, current_env = _create_env(temp, "current-wheel-env")
        _pip(current_python, current_wheel, cwd=temp, env=current_env)
        current_env["ACE_DISABLE_EXTENSIONS"] = "1"
        current_n1 = _probe(
            current_python,
            (
                "import json,sys; "
                "from core.engine.extensions import registry; "
                f"sys.path.insert(0, {str(n1_source)!r}); "
                "from extensions.reference.extension import ProductExtension; "
                "ext=ProductExtension(); "
                "ext.register(registry.Registry(extension_id=ext.name, extension_version=ext.version)); "
                "source=registry._recipe_metadata['product_decision_intelligence']; "
                f"print(json.dumps({{'status':'passed','core':{current_version!r},'reference':ext.version,"
                "'compatibility':source.compatibility,'contract':source.cognition_contract_version},sort_keys=True))"
            ),
            cwd=temp,
            env=current_env,
        )

        n1_python, n1_env = _create_env(temp, "n1-wheel-env")
        _pip(n1_python, n1_wheel, cwd=temp, env=n1_env)
        n1_env["ACE_DISABLE_EXTENSIONS"] = "1"
        n1_current = _probe(
            n1_python,
            (
                "import json,sys; from core.engine.extensions import registry; "
                f"sys.path.insert(0, {str(ROOT)!r}); "
                "from extensions.reference.extension import ProductExtension; ext=ProductExtension(); state={}; "
                'exec("try:\\n ext.register(registry.Registry(extension_id=ext.name, '
                "extension_version=ext.version))\\nexcept Exception as exc:\\n "
                "state['error']=f'{type(exc).__name__}:{exc}'\"); "
                "assert state['error'].endswith('current_reference_extension_requires_pre_registration_negotiation'); "
                "assert not registry._recipes and not registry._task_actions and not registry._tools; "
                f"print(json.dumps({{'status':'passed','core':{n1_version!r},'reference':ext.version,"
                "'disposition':'pre_registration_refusal','error':state['error']},sort_keys=True))"
            ),
            cwd=temp,
            env=n1_env,
        )

        mixed_rows: list[dict[str, Any]] = []
        for name, core_artifact, core_is_sdist, extension_artifact, extension_is_sdist in (
            ("core-wheel_extension-sdist", current_wheel, False, independent_sdist, True),
            ("core-sdist_extension-wheel", current_sdist, True, independent_wheel, False),
        ):
            python, env = _create_env(temp, name)
            _pip(python, core_artifact, cwd=temp, env=env, sdist=core_is_sdist)
            _pip(python, extension_artifact, cwd=temp, env=env, sdist=extension_is_sdist)
            mixed_rows.append(
                _probe(
                    python,
                    (
                        "import json; from core.engine.extensions.loader import load_extensions; "
                        "from core.engine.extensions.registry import registered_recipe_manifests; "
                        "loaded=load_extensions(); manifests=registered_recipe_manifests(); "
                        "assert 'product' in loaded and 'independent_consumer' in loaded; "
                        "assert manifests['independent_consumer_decision_intelligence']['compatibility']=='current'; "
                        f"print(json.dumps({{'status':'passed','mix':{name!r},'loaded':loaded,"
                        "'recipes':sorted(manifests)},sort_keys=True))"
                    ),
                    cwd=temp,
                    env=env,
                )
            )

        zero_python, zero_env = _create_env(temp, "zero-extension-env")
        _pip(zero_python, current_wheel, cwd=temp, env=zero_env)
        zero_env["ACE_DISABLE_EXTENSIONS"] = "1"
        zero = _probe(
            zero_python,
            (
                "import json; from core.engine.extensions.loader import load_extensions; "
                "loaded=load_extensions(); assert loaded==[]; "
                "print(json.dumps({'status':'passed','loaded':loaded},sort_keys=True))"
            ),
            cwd=temp,
            env=zero_env,
        )

        receipt = {
            "contract_version": CONTRACT,
            "created_at": datetime.now(UTC).isoformat(),
            "n1_tag": n1_tag,
            "build_provenance": {
                "builder": "uv build",
                "current_source_date_epoch": current_epoch,
                "n1_source_date_epoch": n1_epoch,
            },
            "artifacts": {
                "current_wheel": {"name": current_wheel.name, "sha256": _sha256(current_wheel)},
                "current_sdist": {"name": current_sdist.name, "sha256": _sha256(current_sdist)},
                "n1_wheel": {"name": n1_wheel.name, "sha256": _sha256(n1_wheel)},
                "n1_sdist": {"name": n1_sdist.name, "sha256": _sha256(n1_sdist)},
                "independent_wheel": {"name": independent_wheel.name, "sha256": _sha256(independent_wheel)},
                "independent_sdist": {"name": independent_sdist.name, "sha256": _sha256(independent_sdist)},
            },
            "current_core_n1_reference": current_n1,
            "n1_core_current_reference": n1_current,
            "mixed_artifacts": mixed_rows,
            "zero_extension": zero,
            "wheel_exclusions": _artifact_exclusions(current_wheel),
            "publication_provenance": "not_proven_by_local_verifier",
            "overall": "passed_local_artifact_matrix",
        }
        if artifacts_dir is not None:
            artifacts_dir = artifacts_dir.resolve()
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            if any(artifacts_dir.iterdir()):
                raise FileExistsError(f"refusing to overwrite non-empty artifacts directory: {artifacts_dir}")
            for artifact in (
                current_wheel,
                current_sdist,
                n1_wheel,
                n1_sdist,
                independent_wheel,
                independent_sdist,
            ):
                shutil.copy2(artifact, artifacts_dir / artifact.name)
            receipt["artifacts_directory"] = str(artifacts_dir)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n1-tag", default="v0.2.0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path)
    args = parser.parse_args(argv)
    receipt = verify(
        n1_tag=args.n1_tag,
        output=args.output.resolve(),
        artifacts_dir=args.artifacts_dir,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

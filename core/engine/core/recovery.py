"""Operational database-state backup and clean-target restore for one ACE store.

This is runnable recovery, not product-scoped data portability. SurrealDB owns
record serialization; ACE recreates its exact packaged schema before importing
those records because historical migration artifacts can contain stale database
definitions that SurrealDB exports but cannot import into a fresh database.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from surrealdb import AsyncSurreal

DATABASE_BACKUP_MANIFEST_CONTRACT = "ace.database-backup-manifest/v1"
DATABASE_RESTORE_RECEIPT_CONTRACT = "ace.database-restore-receipt/v1"


class DatabaseRecoveryError(RuntimeError):
    """A backup or restore could not preserve the declared recovery boundary."""


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    endpoint: str
    namespace: str
    database: str
    username: str
    password: str


@dataclass(frozen=True, slots=True)
class DatabaseBackupManifest:
    contract: str
    created_at: str
    ace_version: str
    surreal_cli_version: str
    schema_version: int
    namespace: str
    database: str
    export_filename: str
    export_sha256: str
    export_size_bytes: int
    includes: tuple[str, ...]
    excludes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatabaseRestoreReceipt:
    contract: str
    restored_at: str
    ace_version: str
    source_ace_version: str
    source_schema_version: int
    restored_schema_version: int
    target_namespace: str
    target_database: str
    export_sha256: str
    export_size_bytes: int
    target_was_clean: bool
    manifest_verified: bool


def _ace_distribution_version() -> str:
    try:
        return version("ace-core")
    except PackageNotFoundError:
        return "unknown"


def target_from_settings(*, namespace: str | None = None, database: str | None = None) -> DatabaseTarget:
    from core.engine.core.config import settings

    return DatabaseTarget(
        endpoint=settings.surreal_url,
        namespace=namespace or settings.surreal_ns,
        database=database or settings.surreal_db,
        username=settings.surreal_user,
        password=settings.surreal_pass,
    )


def _http_endpoint(endpoint: str) -> str:
    """Use the CLI's HTTP endpoint while retaining host, port, path, and redaction."""

    parts = urlsplit(endpoint)
    scheme = {"ws": "http", "wss": "https"}.get(parts.scheme, parts.scheme)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((scheme, host, parts.path, parts.query, parts.fragment))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _surreal_binary() -> str:
    configured = os.environ.get("ACE_SURREAL_BIN", "").strip()
    binary = configured or shutil.which("surreal")
    if not binary:
        raise DatabaseRecoveryError(
            "SurrealDB CLI is required for native backup/restore; install `surreal` or set ACE_SURREAL_BIN"
        )
    return binary


def _surreal_env(target: DatabaseTarget) -> dict[str, str]:
    """Authenticate through the child environment so passwords never enter argv."""

    return os.environ | {
        "SURREAL_USER": target.username,
        "SURREAL_PASS": target.password,
        "SURREAL_NAMESPACE": target.namespace,
        "SURREAL_DATABASE": target.database,
    }


def _run_native(arguments: list[str], *, target: DatabaseTarget) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [_surreal_binary(), *arguments],
            env=_surreal_env(target),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "native SurrealDB operation failed").strip()
        raise DatabaseRecoveryError(detail[:2_000]) from exc


async def _connect(target: DatabaseTarget) -> AsyncSurreal:
    db = AsyncSurreal(target.endpoint)
    await db.connect()
    await db.signin({"username": target.username, "password": target.password})
    await db.use(target.namespace, target.database)
    return db


def _one_mapping(result: Any) -> dict[str, Any]:
    value = result
    while isinstance(value, list) and len(value) == 1:
        value = value[0]
    return value if isinstance(value, dict) else {}


async def database_schema_version(target: DatabaseTarget) -> int:
    db = await _connect(target)
    try:
        result = await db.query("SELECT * FROM config_entry WHERE key = 'schema_version'")
        rows = result[0] if isinstance(result, list) and result and isinstance(result[0], list) else result
        if not rows:
            return 0
        row = rows[0] if isinstance(rows, list) else rows
        return int(row.get("value", 0)) if isinstance(row, dict) else 0
    finally:
        await db.close()


async def database_is_clean(target: DatabaseTarget) -> bool:
    """A restore target is clean only when it has no database-level definitions."""

    db = await _connect(target)
    try:
        info = _one_mapping(await db.query("INFO FOR DB"))
    finally:
        await db.close()
    if not info:
        return True
    for key, value in info.items():
        if key in {"name"}:
            continue
        if value not in ({}, [], (), None, ""):
            return False
    return True


def _manifest_path(export_path: Path, manifest_path: Path | None) -> Path:
    return manifest_path or export_path.with_name(f"{export_path.name}.manifest.json")


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _extract_native_records(native_export: Path, records_export: Path) -> None:
    """Retain only complete native INSERT statements from one Surreal export."""

    inserts: list[str] = []
    for line in native_export.read_text(encoding="utf-8").splitlines():
        if line.startswith("INSERT "):
            if not line.rstrip().endswith(";"):
                raise DatabaseRecoveryError("native export contains an unsupported multiline record statement")
            inserts.append(line)
    if not inserts:
        raise DatabaseRecoveryError("native export contains no database records")
    records_export.write_text(
        "-- ACE record-complete recovery export; schema is recreated from the exact packaged version.\n"
        "OPTION IMPORT;\n\n" + "\n".join(inserts) + "\n",
        encoding="utf-8",
    )


def _packaged_schema_files() -> tuple[tuple[int, Path], ...]:
    from core.engine.core.schema import SCHEMA_DIR

    files: list[tuple[int, Path]] = []
    for path in sorted(SCHEMA_DIR.glob("v*.surql")):
        match = re.search(r"v(\d+)", path.name)
        if match:
            files.append((int(match.group(1)), path))
    if not files:
        raise DatabaseRecoveryError("packaged ACE schema migrations are unavailable")
    return tuple(files)


async def _install_packaged_schema(target: DatabaseTarget, *, expected_version: int) -> None:
    from scripts.schema_apply import apply_file, validate_schema

    files = _packaged_schema_files()
    code_version = max(version for version, _ in files)
    if code_version != expected_version:
        raise DatabaseRecoveryError(
            "backup schema does not match this ACE installation; restore with the recorded ACE version first"
        )
    db = await _connect(target)
    try:
        for version, path in files:
            await apply_file(db, version, path.name, path.read_text(encoding="utf-8"))
            await db.query(
                "UPSERT config_entry SET key = 'schema_version', `value` = $version WHERE key = 'schema_version'",
                {"version": str(version)},
            )
        await validate_schema(db, expected_version)
        info = _one_mapping(await db.query("INFO FOR DB"))
        tables = sorted((info.get("tables") or {}).keys())
        if not tables or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in tables):
            raise DatabaseRecoveryError("packaged schema exposed an unsafe table identity")
        # Migrations can create deterministic seed/config rows. Recovery replaces
        # every table's contents with the exact source snapshot after definitions
        # are installed, so those temporary rows must not collide with native INSERT.
        for name in tables:
            await db.query(f"DELETE `{name}`")
    except DatabaseRecoveryError:
        raise
    except Exception as exc:
        raise DatabaseRecoveryError(
            "packaged schema preparation failed; discard the partial target database before retrying"
        ) from exc
    finally:
        await db.close()


def load_backup_manifest(path: Path) -> DatabaseBackupManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = DatabaseBackupManifest(**payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DatabaseRecoveryError("backup manifest is missing or invalid") from exc
    if manifest.contract != DATABASE_BACKUP_MANIFEST_CONTRACT:
        raise DatabaseRecoveryError("backup manifest contract is unsupported")
    if manifest.schema_version < 1 or manifest.export_size_bytes < 1:
        raise DatabaseRecoveryError("backup manifest does not describe a usable database export")
    return manifest


async def create_database_backup(
    export_path: Path,
    *,
    target: DatabaseTarget,
    manifest_path: Path | None = None,
    created_at: datetime | None = None,
) -> DatabaseBackupManifest:
    """Create one native full-database export plus an adjacent immutable manifest."""

    export_path = export_path.expanduser().resolve()
    manifest_path = _manifest_path(export_path, manifest_path).expanduser().resolve()
    if export_path.exists() or manifest_path.exists():
        raise DatabaseRecoveryError("backup output already exists; choose a new path")
    export_path.parent.mkdir(parents=True, exist_ok=True)
    schema_version = await database_schema_version(target)
    if schema_version < 1:
        raise DatabaseRecoveryError("source database has no supported ACE schema version")
    version = _run_native(["version"], target=target).stdout.strip()
    with tempfile.NamedTemporaryFile(dir=export_path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    with tempfile.NamedTemporaryFile(dir=export_path.parent, delete=False) as handle:
        native_temporary = Path(handle.name)
    try:
        _run_native(
            [
                "export",
                "--endpoint",
                _http_endpoint(target.endpoint),
                "--namespace",
                target.namespace,
                "--database",
                target.database,
                str(native_temporary),
            ],
            target=target,
        )
        _extract_native_records(native_temporary, temporary)
        size = temporary.stat().st_size
        if size < 1:
            raise DatabaseRecoveryError("native database export is empty")
        digest = _sha256(temporary)
        temporary.replace(export_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        native_temporary.unlink(missing_ok=True)
    timestamp = (created_at or datetime.now(UTC)).astimezone(UTC)
    manifest = DatabaseBackupManifest(
        contract=DATABASE_BACKUP_MANIFEST_CONTRACT,
        created_at=timestamp.isoformat(),
        ace_version=_ace_distribution_version(),
        surreal_cli_version=version,
        schema_version=schema_version,
        namespace=target.namespace,
        database=target.database,
        export_filename=export_path.name,
        export_sha256=digest,
        export_size_bytes=size,
        includes=(
            "all_surrealdb_table_records",
            "ace_packaged_schema_at_recorded_version",
        ),
        excludes=(
            "surrealdb_database_users_and_access_definitions",
            "environment_configuration",
            "external_connector_credentials",
            "external_secret_stores",
            "external_source_bodies_not_persisted_in_surrealdb",
        ),
    )
    try:
        _write_json_atomically(manifest_path, asdict(manifest))
    except BaseException:
        export_path.unlink(missing_ok=True)
        raise
    return manifest


async def restore_database_backup(
    export_path: Path,
    *,
    manifest_path: Path | None,
    target: DatabaseTarget,
    restored_at: datetime | None = None,
) -> DatabaseRestoreReceipt:
    """Verify and import a native export only into a demonstrably clean database."""

    export_path = export_path.expanduser().resolve()
    manifest_path = _manifest_path(export_path, manifest_path).expanduser().resolve()
    if not export_path.is_file():
        raise DatabaseRecoveryError("database export does not exist")
    manifest = load_backup_manifest(manifest_path)
    if manifest.export_filename != export_path.name:
        raise DatabaseRecoveryError("backup manifest names a different export file")
    if export_path.stat().st_size != manifest.export_size_bytes or _sha256(export_path) != manifest.export_sha256:
        raise DatabaseRecoveryError("database export checksum or size does not match its manifest")
    if not await database_is_clean(target):
        raise DatabaseRecoveryError("restore target is not clean; use a new empty namespace/database")
    await _install_packaged_schema(target, expected_version=manifest.schema_version)
    try:
        _run_native(
            [
                "import",
                "--endpoint",
                _http_endpoint(target.endpoint),
                "--namespace",
                target.namespace,
                "--database",
                target.database,
                str(export_path),
            ],
            target=target,
        )
    except DatabaseRecoveryError as exc:
        raise DatabaseRecoveryError(
            "native restore failed; treat the target database as partial and discard it before retrying"
        ) from exc
    restored_schema = await database_schema_version(target)
    if restored_schema != manifest.schema_version:
        raise DatabaseRecoveryError(
            "restored schema version does not match the verified backup; quarantine the restored database"
        )
    timestamp = (restored_at or datetime.now(UTC)).astimezone(UTC)
    return DatabaseRestoreReceipt(
        contract=DATABASE_RESTORE_RECEIPT_CONTRACT,
        restored_at=timestamp.isoformat(),
        ace_version=_ace_distribution_version(),
        source_ace_version=manifest.ace_version,
        source_schema_version=manifest.schema_version,
        restored_schema_version=restored_schema,
        target_namespace=target.namespace,
        target_database=target.database,
        export_sha256=manifest.export_sha256,
        export_size_bytes=manifest.export_size_bytes,
        target_was_clean=True,
        manifest_verified=True,
    )


__all__ = [
    "DATABASE_BACKUP_MANIFEST_CONTRACT",
    "DATABASE_RESTORE_RECEIPT_CONTRACT",
    "DatabaseBackupManifest",
    "DatabaseRecoveryError",
    "DatabaseRestoreReceipt",
    "DatabaseTarget",
    "create_database_backup",
    "database_is_clean",
    "database_schema_version",
    "load_backup_manifest",
    "restore_database_backup",
    "target_from_settings",
]

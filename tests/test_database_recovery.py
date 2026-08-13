from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from core.engine.cli.commands.recovery import recovery
from core.engine.core import recovery as recovery_module
from core.engine.core.recovery import (
    DATABASE_BACKUP_MANIFEST_CONTRACT,
    DATABASE_RESTORE_RECEIPT_CONTRACT,
    DatabaseRecoveryError,
    DatabaseTarget,
    create_database_backup,
    restore_database_backup,
)

pytestmark = pytest.mark.unit

TARGET = DatabaseTarget(
    endpoint="ws://127.0.0.1:18001",
    namespace="ace_source",
    database="ace_source",
    username="root",
    password="not-in-argv",
)
DESTINATION = DatabaseTarget(
    endpoint=TARGET.endpoint,
    namespace="ace_restore",
    database="ace_restore",
    username=TARGET.username,
    password=TARGET.password,
)


def _native_fixture(calls: list[list[str]]):
    def run(arguments: list[str], *, target: DatabaseTarget):
        calls.append(arguments)
        assert target.password not in arguments
        if arguments == ["version"]:
            return subprocess.CompletedProcess(arguments, 0, "3.2.3 for fixture\n", "")
        if arguments[0] == "export":
            Path(arguments[-1]).write_text(
                "OPTION IMPORT;\nDEFINE TABLE config_entry;\nINSERT [{ id: config_entry:fixture }];\n",
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(arguments, 0, "", "")

    return run


@pytest.mark.asyncio
async def test_backup_writes_native_export_and_checksum_manifest_without_secrets(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(recovery_module, "_run_native", _native_fixture(calls))

    async def schema(_target):
        return 177

    monkeypatch.setattr(recovery_module, "database_schema_version", schema)
    export = tmp_path / "ace-backup.surql"
    manifest = await create_database_backup(
        export,
        target=TARGET,
        created_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
    )

    assert "INSERT [{ id: config_entry:fixture }];" in export.read_text(encoding="utf-8")
    assert "DEFINE TABLE" not in export.read_text(encoding="utf-8")
    payload = json.loads((tmp_path / "ace-backup.surql.manifest.json").read_text())
    assert payload["contract"] == DATABASE_BACKUP_MANIFEST_CONTRACT
    assert payload["schema_version"] == 177
    assert payload["export_sha256"] == manifest.export_sha256
    assert "external_connector_credentials" in payload["excludes"]
    assert TARGET.password not in json.dumps(payload)
    assert calls[1][:2] == ["export", "--endpoint"]
    assert "http://127.0.0.1:18001" in calls[1]


@pytest.mark.asyncio
async def test_backup_refuses_to_overwrite_either_recovery_artifact(tmp_path):
    export = tmp_path / "existing.surql"
    export.write_text("keep", encoding="utf-8")
    with pytest.raises(DatabaseRecoveryError, match="already exists"):
        await create_database_backup(export, target=TARGET)


@pytest.mark.asyncio
async def test_restore_verifies_checksum_requires_clean_target_and_reports_schema(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(recovery_module, "_run_native", _native_fixture(calls))
    schema_reads = iter((177,))

    async def schema(_target):
        return next(schema_reads)

    async def clean(_target):
        return True

    async def install(_target, *, expected_version):
        assert expected_version == 177

    monkeypatch.setattr(recovery_module, "database_schema_version", schema)
    monkeypatch.setattr(recovery_module, "database_is_clean", clean)
    monkeypatch.setattr(recovery_module, "_install_packaged_schema", install)
    export = tmp_path / "ace-backup.surql"
    export.write_text("DEFINE TABLE config_entry;\n", encoding="utf-8")
    digest = recovery_module._sha256(export)
    (tmp_path / "ace-backup.surql.manifest.json").write_text(
        json.dumps(
            {
                "contract": DATABASE_BACKUP_MANIFEST_CONTRACT,
                "created_at": "2026-08-13T12:00:00+00:00",
                "ace_version": "1.0.0",
                "surreal_cli_version": "3.2.3",
                "schema_version": 177,
                "namespace": "ace_source",
                "database": "ace_source",
                "export_filename": export.name,
                "export_sha256": digest,
                "export_size_bytes": export.stat().st_size,
                "includes": ["surrealdb_database_definitions", "surrealdb_database_records"],
                "excludes": ["external_connector_credentials"],
            }
        ),
        encoding="utf-8",
    )

    receipt = await restore_database_backup(
        export,
        manifest_path=None,
        target=DESTINATION,
        restored_at=datetime(2026, 8, 13, 12, 30, tzinfo=UTC),
    )

    assert receipt.contract == DATABASE_RESTORE_RECEIPT_CONTRACT
    assert receipt.target_was_clean is True
    assert receipt.manifest_verified is True
    assert receipt.restored_schema_version == 177
    assert calls[-1][0] == "import"


@pytest.mark.asyncio
async def test_restore_rejects_dirty_target_before_native_import(tmp_path, monkeypatch):
    export = tmp_path / "ace-backup.surql"
    export.write_text("backup", encoding="utf-8")
    (tmp_path / "ace-backup.surql.manifest.json").write_text(
        json.dumps(
            {
                "contract": DATABASE_BACKUP_MANIFEST_CONTRACT,
                "created_at": "2026-08-13T12:00:00+00:00",
                "ace_version": "1.0.0",
                "surreal_cli_version": "3.2.3",
                "schema_version": 177,
                "namespace": "ace_source",
                "database": "ace_source",
                "export_filename": export.name,
                "export_sha256": recovery_module._sha256(export),
                "export_size_bytes": export.stat().st_size,
                "includes": [],
                "excludes": [],
            }
        ),
        encoding="utf-8",
    )

    async def dirty(_target):
        return False

    monkeypatch.setattr(recovery_module, "database_is_clean", dirty)
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(recovery_module, "_run_native", forbidden)
    with pytest.raises(DatabaseRecoveryError, match="not clean"):
        await restore_database_backup(export, manifest_path=None, target=DESTINATION)
    assert called is False


def test_recovery_cli_exposes_bounded_backup_and_restore_commands():
    runner = CliRunner()
    result = runner.invoke(recovery, ["--help"])
    assert result.exit_code == 0
    assert "backup" in result.output
    assert "restore" in result.output
    assert "connector credentials" in result.output

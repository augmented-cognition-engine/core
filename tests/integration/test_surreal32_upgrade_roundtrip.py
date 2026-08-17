from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal

from core.engine.core.surreal32_upgrade import prepare_surreal32_upgrade

pytestmark = pytest.mark.integration


def _port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _native(binary: str, command: str, endpoint: str, database: str, path: Path):
    return subprocess.run(
        [
            binary,
            command,
            "--endpoint",
            endpoint,
            "--username",
            "root",
            "--password",
            "root",
            "--namespace",
            "ace_upgrade_acceptance",
            "--database",
            database,
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(
    os.environ.get("ACE_RUN_SURREAL32_UPGRADE_ACCEPTANCE") != "1" or shutil.which("surreal") is None,
    reason="requires an explicit disposable SurrealDB 3.2 CLI acceptance run",
)
def test_dangling_org_cleanup_allows_native_surreal32_export_import(tmp_path):
    binary = shutil.which("surreal")
    assert binary is not None
    assert "3.2." in subprocess.run([binary, "version"], check=True, capture_output=True, text=True).stdout
    port = _port()
    endpoint = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [binary, "start", "memory", "--bind", f"127.0.0.1:{port}", "--user", "root", "--pass", "root", "--log", "none"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            ready = subprocess.run(
                [binary, "is-ready", "--endpoint", endpoint, "--log", "none"],
                check=False,
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("disposable SurrealDB did not become ready")

        schema = subprocess.run(
            [
                binary,
                "sql",
                "--endpoint",
                endpoint,
                "--username",
                "root",
                "--password",
                "root",
                "--namespace",
                "ace_upgrade_acceptance",
                "--database",
                "source",
                "--hide-welcome",
            ],
            input=(
                "DEFINE TABLE task SCHEMAFULL;"
                "DEFINE FIELD org ON task TYPE string;"
                "DEFINE INDEX idx_task_org ON task FIELDS org;"
                "REMOVE FIELD org ON task;"
                "DEFINE TABLE config_entry SCHEMAFULL;"
                "DEFINE FIELD value ON config_entry TYPE string;"
            ),
            check=True,
            capture_output=True,
            text=True,
        )
        assert "error" not in schema.stderr.lower()
        broken_export = tmp_path / "broken.surql"
        assert _native(binary, "export", endpoint, "source", broken_export).returncode == 0
        broken_import = _native(binary, "import", endpoint, "broken_target", broken_export)
        assert broken_import.returncode != 0
        assert "field 'org' does not exist" in broken_import.stderr.lower()

        async def clean():
            db = AsyncSurreal(f"ws://127.0.0.1:{port}")
            await db.connect()
            await db.signin({"username": "root", "password": "root"})
            await db.use("ace_upgrade_acceptance", "source")
            try:
                dry_run = await prepare_surreal32_upgrade(db)
                applied = await prepare_surreal32_upgrade(db, apply=True)
                replay = await prepare_surreal32_upgrade(db, apply=True)
                return dry_run, applied, replay
            finally:
                await db.close()

        dry_run, applied, replay = asyncio.run(clean())
        assert [(item.table, item.index) for item in dry_run.stale_indexes] == [("task", "idx_task_org")]
        assert applied.clean is True
        assert replay.removed_indexes == ()
        assert replay.config_value_idiom == "escaped"

        clean_export = tmp_path / "clean.surql"
        assert _native(binary, "export", endpoint, "source", clean_export).returncode == 0
        clean_import = _native(binary, "import", endpoint, "clean_target", clean_export)
        assert clean_import.returncode == 0, clean_import.stderr
    finally:
        process.terminate()
        process.wait(timeout=10)

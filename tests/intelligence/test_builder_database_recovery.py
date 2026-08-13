"""Real SurrealKV restart and native backup/restore proof for the Builder chain."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal

from ace.application import (
    IntelligenceBuilderSessionService,
    IntelligenceResourcePlaneService,
)
from ace.application.intelligence_builder_contracts import (
    OnboardingStage,
    OnboardingTransitionAuthority,
)
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence import IntelligenceResourceKind, IntelligenceResourceQueryV1Alpha1
from ace.testing.watch_brief import exercise_watch_brief_restart
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader
from core.engine.core.recovery import (
    DatabaseTarget,
    create_database_backup,
    restore_database_backup,
)

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parents[2]
PRODUCT = "product:intelligence-builder-fixture"
EVALUATED_AT = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_port(port: int, process: subprocess.Popen, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("disposable SurrealDB exited before accepting connections")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise RuntimeError("disposable SurrealDB did not accept connections")


async def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        await asyncio.to_thread(process.wait, 10)
    except subprocess.TimeoutExpired:
        process.kill()
        await asyncio.to_thread(process.wait)


class _SingleConnectionPool:
    def __init__(self, target: DatabaseTarget) -> None:
        self.target = target
        self.db: AsyncSurreal | None = None

    async def open(self) -> None:
        db = AsyncSurreal(self.target.endpoint)
        await db.connect()
        await db.signin({"username": self.target.username, "password": self.target.password})
        await db.use(self.target.namespace, self.target.database)
        self.db = db

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
            self.db = None

    @asynccontextmanager
    async def connection(self):
        if self.db is None:
            raise RuntimeError("fixture pool is closed")
        yield self.db


class _Authority:
    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        return AuthorityUseReceiptV1Alpha1(
            product_id=kwargs["context"].product_id,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=kwargs["grant_ref"],
            grant_hash="d" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=EVALUATED_AT + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=kwargs["context"].product_id,
                state_id=kwargs["grant_ref"],
                sequence=1,
                revision_id="authority_revision:recovery-read",
                commit_receipt_id="authority_receipt:recovery-read",
            ),
        )


def _query() -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=PRODUCT,
            actor_ref="principal:fixture-builder",
            authentication_receipt_ref="authentication_receipt:recovery-fixture",
            authentication_receipt_digest="sha256:" + "a" * 64,
            authenticated_at=EVALUATED_AT - timedelta(hours=1),
            expires_at=EVALUATED_AT + timedelta(hours=2),
        ),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:recovery-read",
        resource_kinds=(IntelligenceResourceKind.BUILDER_SESSION,),
        as_of=EVALUATED_AT,
        available_at=EVALUATED_AT,
        page_size=200,
    )


async def _page(store: SurrealImmutableRecordStore):
    return await IntelligenceResourcePlaneService(
        reader=intelligence_resource_projection_reader(store),
        authority=_Authority(),
    ).query(_query(), evaluated_at=EVALUATED_AT)


def _surreal_process(binary: str, port: int, store: Path, log) -> subprocess.Popen:
    return subprocess.Popen(
        [
            binary,
            "start",
            "--no-banner",
            "--username",
            "root",
            "--password",
            "root",
            "--bind",
            f"127.0.0.1:{port}",
            f"surrealkv://{store}",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


@pytest.mark.asyncio
async def test_builder_chain_reopens_appends_and_restores_from_native_backup(tmp_path):
    surreal = os.environ.get("ACE_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    port = _port()
    endpoint = f"ws://127.0.0.1:{port}"
    source = DatabaseTarget(endpoint, "ace_builder_recovery", "ace_builder_recovery", "root", "root")
    restored = DatabaseTarget(endpoint, "ace_builder_restored", "ace_builder_restored", "root", "root")
    database_store = tmp_path / "surrealkv"
    log = (tmp_path / "surreal.log").open("wb")
    process = _surreal_process(surreal, port, database_store, log)
    pool: _SingleConnectionPool | None = None
    try:
        await _wait_port(port, process)
        env = os.environ | {
            "SURREAL_URL": endpoint,
            "SURREAL_NS": source.namespace,
            "SURREAL_DB": source.database,
            "SURREAL_USER": source.username,
            "SURREAL_PASS": source.password,
            "JWT_SECRET": "builder-recovery-fixture-secret-at-least-32-bytes",
            "LLM_API_KEY": "sk-test-placeholder",
        }
        await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "scripts/schema_apply.py"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        pool = _SingleConnectionPool(source)
        await pool.open()
        store = SurrealImmutableRecordStore(pool)
        journey = await exercise_watch_brief_restart(store=store)
        before_restart = await _page(store)
        assert before_restart.state.value == "complete"
        assert before_restart.items[-1].payload is not None
        assert before_restart.items[-1].payload.parsed_value()["stage"] == "first_briefing_ready"
        first_brief_revision = journey.briefing.session.revision
        first_page_json = before_restart.model_dump_json()
        await pool.close()
        pool = None

        await _stop(process)
        process = _surreal_process(surreal, port, database_store, log)
        await _wait_port(port, process)

        pool = _SingleConnectionPool(source)
        await pool.open()
        restarted_store = SurrealImmutableRecordStore(pool)
        restarted_sessions = IntelligenceBuilderSessionService(store=restarted_store)
        reopened = await restarted_sessions.load_latest(
            product_id=PRODUCT,
            session_id=first_brief_revision.session_id,
            available_at=EVALUATED_AT,
        )
        assert reopened == first_brief_revision
        assert (await _page(restarted_store)).model_dump_json() == first_page_json

        later = await restarted_sessions.advance(
            reopened,
            stage=OnboardingStage.ACTIVATION_PENDING,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref="agent:activation-planner",
            occurred_at=datetime(2026, 8, 11, 12, 4, tzinfo=UTC),
        )
        after_append = await _page(restarted_store)
        assert len(after_append.items) == len(before_restart.items) + 1
        assert after_append.items[:-1] == before_restart.items
        assert after_append.items[-1].payload is not None
        assert after_append.items[-1].payload.parsed_value()["stage"] == "activation_pending"
        assert later.revision.prior_revision_id == reopened.revision_id
        await pool.close()
        pool = None

        export = tmp_path / "ace-builder.surql"
        manifest = await create_database_backup(export, target=source)
        receipt = await restore_database_backup(export, manifest_path=None, target=restored)
        assert receipt.source_schema_version == receipt.restored_schema_version == manifest.schema_version

        pool = _SingleConnectionPool(restored)
        await pool.open()
        restored_page = await _page(SurrealImmutableRecordStore(pool))
        assert restored_page.model_dump_json() == after_append.model_dump_json()
    finally:
        if pool is not None:
            await pool.close()
        await _stop(process)
        log.close()

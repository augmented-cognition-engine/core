"""Real SurrealKV restart proof for durable Intelligence build host composition."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys

import pytest

from ace.application.installed_pack_artifacts import InstalledCompiledPackArtifactResolver
from ace.application.intelligence_build_execution import (
    ImmutableRecordScopeError,
    ProductScopedImmutableRecordStore,
)
from ace.application.intelligence_build_host import DurableIntelligenceBuildHostComposer
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from tests.intelligence.test_builder_database_recovery import (
    ROOT,
    _port,
    _SingleConnectionPool,
    _stop,
    _surreal_process,
    _wait_port,
)
from tests.intelligence.test_domain_activation_plan_admission import _pack_material
from tests.test_installed_pack_artifacts import _Distribution
from tests.test_intelligence_build_host_composition import (
    _activated_stack,
    _build,
    _Resources,
    _RuntimeUse,
)

pytestmark = pytest.mark.e2e


def _installed_packs(tmp_path):
    manifest_document, modules, fixture = _pack_material()
    manifest = json.loads(manifest_document)
    pack_id = manifest["metadata"]["pack_id"]
    root = f"domain_packs/{pack_id}"
    resources = {
        f"{root}/manifest.json": manifest_document,
        **{f"{root}/{path}": payload for path, payload in modules.items()},
        f"{root}/conformance/activation_golden_fixture.json": fixture,
    }
    return InstalledCompiledPackArtifactResolver.discover(
        [_Distribution(tmp_path / "installed-pack", "ace-test-domain", resources)]
    )


@pytest.mark.asyncio
async def test_durable_host_recomposes_exact_invocation_ports_after_service_restart(tmp_path):
    surreal = os.environ.get("ACE_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    port = _port()
    endpoint = f"ws://127.0.0.1:{port}"
    database_store = tmp_path / "surrealkv"
    log = (tmp_path / "surreal.log").open("wb")
    process = _surreal_process(surreal, port, database_store, log)
    pool: _SingleConnectionPool | None = None
    try:
        await _wait_port(port, process)
        target = type("Target", (), {})()
        target.endpoint = endpoint
        target.namespace = "ace_build_host_restart"
        target.database = "ace_build_host_restart"
        target.username = "root"
        target.password = "root"
        env = os.environ | {
            "SURREAL_URL": endpoint,
            "SURREAL_NS": target.namespace,
            "SURREAL_DB": target.database,
            "SURREAL_USER": target.username,
            "SURREAL_PASS": target.password,
            "JWT_SECRET": "build-host-restart-fixture-secret-at-least-32-bytes",
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

        pool = _SingleConnectionPool(target)
        await pool.open()
        records = SurrealImmutableRecordStore(pool)
        governed = SurrealGovernedStateStore(pool)
        _, _, _, authority, active = await _activated_stack(records=records, governed=governed)
        build = _build(active)
        runtime_use = _RuntimeUse()
        installed = _installed_packs(tmp_path)
        first = await DurableIntelligenceBuildHostComposer(
            governed_state=governed,
            runtime_use=runtime_use,
            packs=installed,
        ).compose(
            build=build,
            records=ProductScopedImmutableRecordStore(product_id=build.product_id, store=records),
            resources=_Resources(),
            activation_authority=authority,
        )
        assert first.recorded_sources is not None
        assert first.prepared_derivations is not None
        first_binding = first.recorded_sources.binding
        authority_calls = (len(authority.approvals), len(authority.grants))
        await pool.close()
        pool = None

        await _stop(process)
        process = _surreal_process(surreal, port, database_store, log)
        await _wait_port(port, process)

        pool = _SingleConnectionPool(target)
        await pool.open()
        reopened_records = SurrealImmutableRecordStore(pool)
        reopened_governed = SurrealGovernedStateStore(pool)
        reopened_runtime_use = _RuntimeUse()
        reopened = await DurableIntelligenceBuildHostComposer(
            governed_state=reopened_governed,
            runtime_use=reopened_runtime_use,
            packs=_installed_packs(tmp_path),
        ).compose(
            build=build,
            records=ProductScopedImmutableRecordStore(
                product_id=build.product_id,
                store=reopened_records,
            ),
            resources=_Resources(),
            activation_authority=authority,
        )

        assert reopened.recorded_sources is not None
        assert reopened.prepared_derivations is not None
        assert reopened.recorded_sources is not first.recorded_sources
        assert reopened.prepared_derivations is not first.prepared_derivations
        assert reopened.recorded_sources.binding == first_binding
        assert reopened.recorded_sources.store is reopened.records
        assert reopened.prepared_derivations.ledger.store is reopened.records
        assert reopened.prepared_derivations.runtime_use is reopened_runtime_use
        assert reopened.activation_authority is authority
        assert (len(authority.approvals), len(authority.grants)) == authority_calls
        assert reopened_runtime_use.calls == []
        assert not hasattr(reopened, "binding")
        with pytest.raises(ImmutableRecordScopeError):
            await reopened.records.scan_product_records(product_id="product:other")
    finally:
        if pool is not None:
            await pool.close()
        await _stop(process)
        log.close()

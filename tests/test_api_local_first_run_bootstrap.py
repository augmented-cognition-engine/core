"""PI13 WS3a: /v1/intelligence/builds/bootstrap/local-first-run route tests.

These tests prove the production route family reaches the governed local
first-run bootstrap through its durable runtime dependency, that identical
durable material replays the exact recorded approval and start request, and
that denied/missing/conflict/unavailable outcomes map to exact HTTP statuses.
The full service behavior stays covered by ``tests/test_local_first_run_bootstrap.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.core.contracts import canonical_hash
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.intelligence_builds import router
from core.engine.core.agent_composition_runtime import CompositionAuthorityGrantMaterial
from core.engine.core.auth import get_current_user
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.local_first_run_bootstrap import (
    LocalFirstRunBootstrapRuntime,
    local_first_run_bootstrap_runtime,
)
from core.engine.core.local_owner_authority import (
    LOCAL_OWNER_PRODUCT_ID,
    bootstrap_local_owner_authority,
)
from tests.test_local_first_run_bootstrap import READ_GRANT_REF, _bound_plan, _owner
from tests.test_local_owner_authority import InMemoryGovernedStateStore

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)
ROUTE = "/v1/intelligence/builds/bootstrap/local-first-run"


class _UnavailableRecordStore(InMemoryImmutableRecordStore):
    async def read_as_of(self, **kwargs):
        raise RuntimeError("durable record storage is down")


def _body(bound) -> dict:
    return {
        "decision": "approve",
        "bound_plan": json.loads(bound.model_dump_json()),
        "approved_at": NOW.isoformat(),
    }


async def _request(*, user: dict, runtime: LocalFirstRunBootstrapRuntime, body: dict):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[local_first_run_bootstrap_runtime] = lambda: runtime
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(ROUTE, json=body)


def test_default_bootstrap_runtime_composes_the_durable_surreal_stores() -> None:
    runtime = local_first_run_bootstrap_runtime()
    assert isinstance(runtime.records, SurrealImmutableRecordStore)
    assert isinstance(runtime.governed_state, SurrealGovernedStateStore)


@pytest.mark.asyncio
async def test_route_returns_then_exactly_replays_the_durable_bootstrap_material(tmp_path) -> None:
    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=NOW - timedelta(hours=1))
    bound = await _bound_plan(tmp_path, bound_at=NOW)
    runtime = LocalFirstRunBootstrapRuntime(records=records, governed_state=governed)

    first = await _request(user=_owner(), runtime=runtime, body=_body(bound))

    assert first.status_code == 200
    payload = first.json()
    assert payload["contract"] == "ace.host.local-first-run-build-authority/v1alpha1"
    assert payload["resumed"] is False
    assert payload["bound_plan_id"] == bound.bound_plan_id
    assert payload["start_request"]["activation_approval_receipt_ref"] == payload["approval"]["receipt_ref"]

    replay = await _request(user=_owner(), runtime=runtime, body=_body(bound))

    assert replay.status_code == 200
    replayed = replay.json()
    assert replayed["resumed"] is True
    assert replayed["approval"] == payload["approval"]
    assert replayed["start_request"] == payload["start_request"]


@pytest.mark.asyncio
async def test_identical_replay_after_grant_revocation_fails_closed_at_server_now(tmp_path) -> None:
    """The client's ``approved_at`` must not pin authority evaluation.

    An approval minted before a grant revocation, replayed with the identical
    request body (same old ``approved_at``), must fail closed at server-now
    naming the revoked grant — never resume authority as of the old timestamp.
    """

    records = InMemoryImmutableRecordStore()
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=NOW - timedelta(hours=1))
    bound = await _bound_plan(tmp_path, bound_at=NOW)
    runtime = LocalFirstRunBootstrapRuntime(records=records, governed_state=governed)
    body = _body(bound)

    minted = await _request(user=_owner(), runtime=runtime, body=body)
    assert minted.status_code == 200
    assert minted.json()["resumed"] is False

    # Revoke the observe_read grant just after the client-reviewed approval
    # timestamp; evaluation pinned to the old ``approved_at`` would miss it.
    head = governed.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, READ_GRANT_REF)]
    revision = governed.revisions[(LOCAL_OWNER_PRODUCT_ID, head.revision_id)]
    grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload)
    revoked = grant.model_copy(update={"lifecycle": "revoked", "revoked_at": NOW + timedelta(seconds=1)})
    governed.revisions[(LOCAL_OWNER_PRODUCT_ID, head.revision_id)] = revision.model_copy(
        update={
            "payload": revoked.model_dump(mode="python"),
            "material_hash": canonical_hash(revoked.model_dump(mode="json")),
        }
    )

    replay = await _request(user=_owner(), runtime=runtime, body=body)

    assert replay.status_code == 404
    assert READ_GRANT_REF in replay.json()["detail"]


@pytest.mark.asyncio
async def test_route_maps_denied_missing_conflict_and_unavailable_exactly(tmp_path) -> None:
    governed = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=governed, approved_at=NOW - timedelta(hours=1))
    bound = await _bound_plan(tmp_path, bound_at=NOW)

    denied = await _request(
        user={**_owner(), "local_owner": False},
        runtime=LocalFirstRunBootstrapRuntime(records=InMemoryImmutableRecordStore(), governed_state=governed),
        body=_body(bound),
    )
    assert denied.status_code == 403

    missing = await _request(
        user=_owner(),
        runtime=LocalFirstRunBootstrapRuntime(
            records=InMemoryImmutableRecordStore(),
            governed_state=InMemoryGovernedStateStore(),
        ),
        body=_body(bound),
    )
    assert missing.status_code == 404
    assert "authority_grant:atrium-observe-read" in missing.json()["detail"]

    records = InMemoryImmutableRecordStore()
    runtime = LocalFirstRunBootstrapRuntime(records=records, governed_state=governed)
    minted = await _request(user=_owner(), runtime=runtime, body=_body(bound))
    assert minted.status_code == 200
    crossed = await _bound_plan(
        tmp_path,
        bound_at=NOW,
        client_request_id="atrium_request:personal-first-run-crossed",
    )
    conflict = await _request(user=_owner(), runtime=runtime, body=_body(crossed))
    assert conflict.status_code == 409
    assert "different exact bound plan" in conflict.json()["detail"]

    unavailable = await _request(
        user=_owner(),
        runtime=LocalFirstRunBootstrapRuntime(records=_UnavailableRecordStore(), governed_state=governed),
        body=_body(bound),
    )
    assert unavailable.status_code == 503

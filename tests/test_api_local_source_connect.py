"""Tests for the Connect preview/authorize HTTP transport (ACE PI13)."""

from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.api.main import app
from core.engine.core.auth import get_current_user
from core.engine.core.local_source_connect import (
    LocalSourceConnectHostRuntime,
    LocalSourceConnectRecordRepository,
    local_source_connect_host_runtime,
    local_source_connect_preview_runtime,
)
from tests.test_local_source_connect_host import (
    NONEXISTENT_ROOT,
    PREVIEW_GROUP_ID,
    PREVIEW_MAPPING_ID,
    PREVIEW_PROFILE,
    PREVIEW_PROFILE_ID,
    CountingProvider,
    CountingResolver,
    _acquired_markdown_file,
    _authorized_at,
    _clock,
    _installed_mapping,
    _preview_runtime,
)

_AUTHORIZE_USER = {"sub": "actor:reviewer-1", "product": "product:pi13-ws2-host"}


def _preview_payload() -> dict:
    return {
        "profile_id": PREVIEW_PROFILE_ID,
        "profile_digest": PREVIEW_PROFILE.profile_digest,
        "source_group_id": PREVIEW_GROUP_ID,
        "authorized_root": NONEXISTENT_ROOT,
        "mapping_scopes": [{"mapping_id": PREVIEW_MAPPING_ID, "include": ["notes/*.md"]}],
        "exclude": [],
    }


def _fetch_preview_body(client: TestClient, *, user: dict | None = None) -> dict:
    app.dependency_overrides[get_current_user] = lambda: user if user is not None else _AUTHORIZE_USER
    app.dependency_overrides[local_source_connect_preview_runtime] = lambda: _preview_runtime()
    response = client.post("/v1/intelligence/builds/connect/preview", json=_preview_payload())
    assert response.status_code == 200
    return response.json()


def _authorize_host_runtime(
    *, resolver: CountingResolver, store: InMemoryImmutableRecordStore
) -> LocalSourceConnectHostRuntime:
    return LocalSourceConnectHostRuntime(
        repository=LocalSourceConnectRecordRepository(store),
        provider_resolver=resolver,
        clock=_clock(_authorized_at(), _authorized_at()),
    )


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def client():
    # These route-contract tests inject their complete runtimes and deliberately
    # skip the production lifespan, which requires a live SurrealDB.
    yield TestClient(app)


def test_openapi_has_connect_preview_and_authorize_post_paths() -> None:
    paths = app.openapi()["paths"]

    assert "post" in paths["/v1/intelligence/builds/connect/preview"]
    assert "post" in paths["/v1/intelligence/builds/connect/authorize"]


def test_preview_endpoint_returns_local_read_only_installed_preview(client: TestClient) -> None:
    user = {"sub": "actor:reviewer-1", "product": "product:pi13-ws2-host"}
    runtime = _preview_runtime()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[local_source_connect_preview_runtime] = lambda: runtime

    payload = {
        "profile_id": PREVIEW_PROFILE_ID,
        "profile_digest": PREVIEW_PROFILE.profile_digest,
        "source_group_id": PREVIEW_GROUP_ID,
        "authorized_root": NONEXISTENT_ROOT,
        "mapping_scopes": [{"mapping_id": PREVIEW_MAPPING_ID, "include": ["notes/*.md"]}],
        "exclude": [],
    }

    response = client.post("/v1/intelligence/builds/connect/preview", json=payload)

    assert response.status_code == 200
    body = response.json()

    assert body["acquisition_mode"] == "local"
    assert body["read_only"] is True
    assert body["network_capture_performed"] is False
    assert body["write_access_requested"] is False

    installed = _installed_mapping()
    assert len(body["mapping_scopes"]) == 1
    scope = body["mapping_scopes"][0]
    assert scope["mapping_id"] == installed.mapping_id
    assert scope["source_definition_ref"] == installed.source_definition_ref
    assert scope["source_type_ref"] == installed.source_type_ref
    assert scope["subject_binding_id"] == installed.subject_binding_id
    assert scope["entity_type_id"] == installed.entity_type_id
    assert scope["include"] == ["notes/*.md"]

    assert not hasattr(runtime, "provider_resolver")


def test_authorize_missing_authorized_field_is_422_and_calls_nothing(client: TestClient) -> None:
    provider = CountingProvider(files=(_acquired_markdown_file(),))
    resolver = CountingResolver(provider)
    store = InMemoryImmutableRecordStore()

    preview_body = _fetch_preview_body(client)
    app.dependency_overrides[local_source_connect_host_runtime] = lambda: _authorize_host_runtime(
        resolver=resolver, store=store
    )
    response = client.post(
        "/v1/intelligence/builds/connect/authorize",
        json={"preview": preview_body, "authorized_at": _authorized_at().isoformat()},
    )

    assert response.status_code == 422
    assert resolver.calls == 0
    assert provider.calls == 0
    assert store.records == {}


def test_authorize_false_is_422_and_calls_nothing(client: TestClient) -> None:
    provider = CountingProvider(files=(_acquired_markdown_file(),))
    resolver = CountingResolver(provider)
    store = InMemoryImmutableRecordStore()

    preview_body = _fetch_preview_body(client)
    app.dependency_overrides[local_source_connect_host_runtime] = lambda: _authorize_host_runtime(
        resolver=resolver, store=store
    )
    response = client.post(
        "/v1/intelligence/builds/connect/authorize",
        json={"preview": preview_body, "authorized": False, "authorized_at": _authorized_at().isoformat()},
    )

    assert response.status_code == 422
    assert resolver.calls == 0
    assert provider.calls == 0
    assert store.records == {}


def test_authorize_true_success_persists_local_read_only_capture(client: TestClient) -> None:
    provider = CountingProvider(files=(_acquired_markdown_file(),))
    resolver = CountingResolver(provider)
    store = InMemoryImmutableRecordStore()

    preview_body = _fetch_preview_body(client)
    app.dependency_overrides[local_source_connect_host_runtime] = lambda: _authorize_host_runtime(
        resolver=resolver, store=store
    )
    response = client.post(
        "/v1/intelligence/builds/connect/authorize",
        json={"preview": preview_body, "authorized": True, "authorized_at": _authorized_at().isoformat()},
    )

    assert response.status_code == 200
    assert resolver.calls == 1
    assert provider.calls == 1

    body = response.json()
    assert body["acquisition_mode"] == "local"
    assert body["read_only"] is True
    assert body["network_capture_performed"] is False
    assert body["write_access_requested"] is False
    assert len(body["captures"]) == 1

    capture = body["captures"][0]
    assert capture["relative_path"] == "notes/a.md"
    expected_uri = "file://" + quote(f"{NONEXISTENT_ROOT}/notes/a.md", safe="/")
    assert capture["source_uri"] == expected_uri
    assert capture["selection"]["source_uri"] == expected_uri

    assert store.records != {}


def test_authorize_replay_with_failing_resolver_returns_same_result_without_new_reads(client: TestClient) -> None:
    provider = CountingProvider(files=(_acquired_markdown_file(),))
    resolver = CountingResolver(provider)
    store = InMemoryImmutableRecordStore()

    preview_body = _fetch_preview_body(client)
    payload = {
        "preview": preview_body,
        "authorized": True,
        "authorized_at": _authorized_at().isoformat(),
    }

    app.dependency_overrides[local_source_connect_host_runtime] = lambda: _authorize_host_runtime(
        resolver=resolver, store=store
    )
    first_response = client.post("/v1/intelligence/builds/connect/authorize", json=payload)

    failing_resolver = CountingResolver(raise_error=AssertionError("must not resolve on exact replay"))
    app.dependency_overrides[local_source_connect_host_runtime] = lambda: _authorize_host_runtime(
        resolver=failing_resolver, store=store
    )
    replay_response = client.post("/v1/intelligence/builds/connect/authorize", json=payload)

    assert first_response.status_code == 200
    assert replay_response.status_code == 200
    assert replay_response.json() == first_response.json()
    assert failing_resolver.calls == 0
    assert provider.calls == 1


def test_authorize_different_authenticated_actor_is_403_and_calls_nothing(client: TestClient) -> None:
    provider = CountingProvider(files=(_acquired_markdown_file(),))
    resolver = CountingResolver(provider)
    store = InMemoryImmutableRecordStore()

    preview_body = _fetch_preview_body(client)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "actor:someone-else",
        "product": "product:pi13-ws2-host",
    }
    app.dependency_overrides[local_source_connect_host_runtime] = lambda: _authorize_host_runtime(
        resolver=resolver, store=store
    )
    response = client.post(
        "/v1/intelligence/builds/connect/authorize",
        json={"preview": preview_body, "authorized": True, "authorized_at": _authorized_at().isoformat()},
    )

    assert response.status_code == 403
    assert resolver.calls == 0
    assert provider.calls == 0
    assert store.records == {}

"""Tests for the local Connect-to-Builder source-scope bridge (PI13 WS3 addendum 9)."""

from __future__ import annotations

import unittest.mock
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import OnboardingStage
from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectPreviewRequest,
    LocalSourceMappingScope,
    authorize_local_source_connect,
    preview_local_source_connect,
)
from ace.core.contracts import canonical_hash
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.core.intelligence_builder_disposition_authority import (
    BuilderSourceScopeApproveRequestV1Alpha1,
    approve_builder_source_scope,
)
from core.engine.core.local_owner_authority import LOCAL_OWNER_ACTOR_REF, LOCAL_OWNER_PRODUCT_ID
from core.engine.core.local_source_connect import LocalSourceConnectRecordRepository
from core.engine.core.local_source_connect_progression import (
    LocalSourceConnectScopeProgressionRuntime,
    LocalSourceConnectSourceProgressionConflict,
    LocalSourceConnectSourceProgressionDenied,
    connect_local_source_connect_scope,
    propose_local_source_connect_scope,
)

pytestmark = pytest.mark.unit

_AUTHORIZED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


class _NoGrantAuthority:
    async def resolve_approval(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("unexpected direct approval resolution on the grant delegate")

    async def resolve_grant(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("connect() never resolves a grant through this delegate")


def _owner(**overrides) -> dict:
    values = {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": ["intelligence_build", "observe_read"],
        "local_owner": True,
    }
    values.update(overrides)
    return values


def _pack() -> CompiledPackRefV1:
    digest = canonical_hash({"pack": "pi13-ws3-source-progression"})
    return CompiledPackRefV1(
        pack_id="pack-a",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{digest[:32]}",
        pack_digest=f"sha256:{digest}",
    )


def _scope(mapping_id: str = "mapping-a", include: tuple[str, ...] = ("notes/*.md",)) -> LocalSourceMappingScope:
    return LocalSourceMappingScope(
        mapping_id=mapping_id,
        source_definition_ref="source-def-a",
        source_type_ref="source_type:local_files",
        subject_binding_id="subject-a",
        entity_type_id="entity-a",
        include=include,
    )


def _preview_request(**overrides) -> LocalSourceConnectPreviewRequest:
    values = dict(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        pack=_pack(),
        profile_id="profile-a",
        profile_digest=f"sha256:{canonical_hash({'profile': 'a'})}",
        source_group_id="source-group-a",
        expected_contribution="A cited orientation over the exact authorized local scope.",
        authorized_root="/nonexistent/pi13-ws3/host-local-root",
        mapping_scopes=(_scope(),),
        exclude=(),
    )
    values.update(overrides)
    return LocalSourceConnectPreviewRequest(**values)


def _authorization_request(**preview_overrides) -> LocalSourceConnectAuthorizationRequest:
    preview = preview_local_source_connect(_preview_request(**preview_overrides))
    return LocalSourceConnectAuthorizationRequest(preview=preview, authorized=True, authorized_at=_AUTHORIZED_AT)


def _provider_identity(**overrides) -> CapabilityArtifactIdentityV1Alpha1:
    values = dict(
        capability="source_snapshot",
        contract="ace.source.snapshot/v1alpha1",
        implementation_id="spy-provider",
        implementation_version="1.0.0",
        artifact_digest=f"sha256:{canonical_hash({'provider': 'spy'})}",
    )
    values.update(overrides)
    return CapabilityArtifactIdentityV1Alpha1(**values)


class SpyProvider:
    def __init__(self, files: tuple[AcquiredLocalFile, ...] = ()) -> None:
        self.artifact_identity = _provider_identity()
        self.files = files

    async def snapshot(self, request):
        return self.files


def _acquired_markdown_file(relative_path: str, payload: str = '{"text":"hello"}', **overrides) -> AcquiredLocalFile:
    values = dict(
        relative_path=relative_path,
        extension="md",
        byte_digest=f"sha256:{canonical_hash({'bytes': relative_path})}",
        size_bytes=len(payload),
        status="acquired",
        structured_payload_json=payload,
    )
    values.update(overrides)
    return AcquiredLocalFile(**values)


async def _build_result(request, files):
    return await authorize_local_source_connect(request, SpyProvider(files=files))


def _raise_if_touched(*args, **kwargs):
    raise AssertionError("the source-scope bridge must never touch the filesystem")


@contextmanager
def _forbidden_filesystem():
    with (
        unittest.mock.patch("os.path.exists", _raise_if_touched),
        unittest.mock.patch("os.stat", _raise_if_touched),
        unittest.mock.patch("os.scandir", _raise_if_touched),
        unittest.mock.patch("builtins.open", _raise_if_touched),
    ):
        yield


async def _seeded_session(store):
    sessions = IntelligenceBuilderSessionService(store=store)
    started = await sessions.start(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        correlation_id="correlation:ws3-source-progression",
        goal_ref="goal:bounded-orientation",
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=_AUTHORIZED_AT,
    )
    return sessions, started.revision


def _runtime(store) -> LocalSourceConnectScopeProgressionRuntime:
    return LocalSourceConnectScopeProgressionRuntime(
        records=store,
        repository=LocalSourceConnectRecordRepository(store),
        grants=_NoGrantAuthority(),
    )


# --- propose_local_source_connect_scope ---


async def test_propose_derives_selections_from_recorded_captures_and_advances_session():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    sessions, session = await _seeded_session(store)
    runtime = _runtime(store)

    with _forbidden_filesystem():
        scope = await propose_local_source_connect_scope(
            request=request,
            result=result,
            session=session,
            user=_owner(),
            runtime=runtime,
            occurred_at=_AUTHORIZED_AT,
        )

    assert len(scope.proposal.selections) == 2
    assert scope.session.revision.stage is OnboardingStage.SOURCES_CONNECTING
    assert scope.session.revision.product_id == LOCAL_OWNER_PRODUCT_ID

    reloaded = await sessions.load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID, session_id=session.session_id, available_at=_AUTHORIZED_AT
    )
    assert reloaded is not None
    assert reloaded.revision_id == scope.session.revision.revision_id


async def test_propose_is_idempotent_on_retry():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    sessions, session = await _seeded_session(store)
    runtime = _runtime(store)

    first = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )
    second = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )

    assert first.proposal.proposal_id == second.proposal.proposal_id
    assert first.session.revision.revision_id == second.session.revision.revision_id


async def test_propose_retry_fails_closed_on_different_retried_timestamp():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )

    with pytest.raises(LocalSourceConnectSourceProgressionConflict):
        await propose_local_source_connect_scope(
            request=request,
            result=result,
            session=session,
            user=_owner(),
            runtime=runtime,
            occurred_at=_AUTHORIZED_AT + timedelta(seconds=1),
        )


async def test_propose_fails_closed_on_crossed_owner():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    with pytest.raises(LocalSourceConnectSourceProgressionDenied):
        await propose_local_source_connect_scope(
            request=request,
            result=result,
            session=session,
            user=_owner(sub="user:someone-else"),
            runtime=runtime,
            occurred_at=_AUTHORIZED_AT,
        )


async def test_propose_fails_closed_on_result_mismatching_recorded_material():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    other_result = await _build_result(request, (_acquired_markdown_file("notes/a.md"),))
    with pytest.raises(LocalSourceConnectSourceProgressionConflict):
        await propose_local_source_connect_scope(
            request=request,
            result=other_result,
            session=session,
            user=_owner(),
            runtime=runtime,
            occurred_at=_AUTHORIZED_AT,
        )


async def test_propose_fails_closed_on_single_capture_below_the_two_source_bound():
    request = _authorization_request()
    result = await _build_result(request, (_acquired_markdown_file("notes/a.md"),))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    with pytest.raises(LocalSourceConnectSourceProgressionDenied, match="two distinct"):
        await propose_local_source_connect_scope(
            request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
        )


async def test_propose_fails_closed_on_empty_captures():
    request = _authorization_request()
    result = await _build_result(request, ())
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    with pytest.raises(LocalSourceConnectSourceProgressionDenied, match="no captured local sources"):
        await propose_local_source_connect_scope(
            request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
        )


async def test_propose_fails_closed_on_unsupported_only_result():
    request = _authorization_request(mapping_scopes=(_scope(include=("notes/*.bin",)),))
    unsupported = _acquired_markdown_file(
        "notes/a.bin", extension="bin", status="unsupported", structured_payload_json=None
    )
    result = await _build_result(request, (unsupported,))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    assert result.captures == ()
    with pytest.raises(LocalSourceConnectSourceProgressionDenied, match="no captured local sources"):
        await propose_local_source_connect_scope(
            request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
        )


async def test_propose_fails_closed_on_more_than_the_bounded_selection_limit(monkeypatch):
    import core.engine.core.local_source_connect_progression as module

    monkeypatch.setattr(module, "MAX_SOURCE_SCOPE_SELECTIONS", 1)
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    with pytest.raises(LocalSourceConnectSourceProgressionDenied, match="exceed"):
        await propose_local_source_connect_scope(
            request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
        )


async def test_connect_blocks_closed_on_unrepresentable_payload_shape():
    request = _authorization_request()
    scalar_payload_file = _acquired_markdown_file("notes/a.md", payload="1")
    result = await _build_result(request, (scalar_payload_file, _acquired_markdown_file("notes/b.md")))
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )

    # An unrepresentable capture payload fails closed inside test_and_sample,
    # which ConnectionAgent.connect maps to a safe block rather than raising.
    outcome = await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=approval.approval.receipt_ref,
        user=_owner(),
        runtime=runtime,
        occurred_at=approved_at + timedelta(seconds=1),
    )
    assert outcome.connected is False
    assert outcome.session.revision.stage is OnboardingStage.BLOCKED


# --- connect_local_source_connect_scope ---


async def test_connect_uses_the_same_recorded_provider_and_performs_no_read():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )

    with _forbidden_filesystem():
        outcome = await connect_local_source_connect_scope(
            request=request,
            result=result,
            session=scope.session.revision,
            proposal=scope.proposal,
            approval_receipt_ref=approval.approval.receipt_ref,
            user=_owner(),
            runtime=runtime,
            occurred_at=approved_at + timedelta(seconds=1),
        )

    assert outcome.connected is True
    assert outcome.profile is not None
    assert len(outcome.profile.samples) == len(scope.proposal.selections)
    catalog_option_ids = {sample.option_id for sample in outcome.profile.samples}
    proposed_option_ids = {selection.option_id for selection in scope.proposal.selections}
    assert catalog_option_ids == proposed_option_ids


async def test_connect_is_idempotent_on_retry():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )
    occurred_at = approved_at + timedelta(seconds=1)

    first = await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=approval.approval.receipt_ref,
        user=_owner(),
        runtime=runtime,
        occurred_at=occurred_at,
    )
    second = await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=approval.approval.receipt_ref,
        user=_owner(),
        runtime=runtime,
        occurred_at=occurred_at,
    )

    assert first.session.revision.revision_id == second.session.revision.revision_id
    assert first.connected is True
    assert second.connected is True


async def test_connect_fails_closed_on_stale_session():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )

    with pytest.raises(LocalSourceConnectSourceProgressionConflict):
        await connect_local_source_connect_scope(
            request=request,
            result=result,
            session=session,  # stale: the GOAL_SELECTED revision, not the proposed one
            proposal=scope.proposal,
            approval_receipt_ref=approval.approval.receipt_ref,
            user=_owner(),
            runtime=runtime,
            occurred_at=approved_at + timedelta(seconds=1),
        )


async def test_connect_does_not_mint_approval_and_fails_closed_when_unapproved():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )

    outcome = await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref="approval:builder-source-scope:never-recorded",
        user=_owner(),
        runtime=runtime,
        occurred_at=_AUTHORIZED_AT + timedelta(seconds=2),
    )

    assert outcome.connected is False
    assert outcome.session.revision.stage is OnboardingStage.BLOCKED


async def test_connect_fails_closed_on_crossed_owner():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )

    with pytest.raises(LocalSourceConnectSourceProgressionDenied):
        await connect_local_source_connect_scope(
            request=request,
            result=result,
            session=scope.session.revision,
            proposal=scope.proposal,
            approval_receipt_ref=approval.approval.receipt_ref,
            user=_owner(sub="user:someone-else"),
            runtime=runtime,
            occurred_at=approved_at + timedelta(seconds=1),
        )


async def test_connect_retry_fails_closed_on_different_retried_timestamp():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )
    occurred_at = approved_at + timedelta(seconds=1)

    await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=approval.approval.receipt_ref,
        user=_owner(),
        runtime=runtime,
        occurred_at=occurred_at,
    )

    with pytest.raises(LocalSourceConnectSourceProgressionConflict):
        await connect_local_source_connect_scope(
            request=request,
            result=result,
            session=scope.session.revision,
            proposal=scope.proposal,
            approval_receipt_ref=approval.approval.receipt_ref,
            user=_owner(),
            runtime=runtime,
            occurred_at=occurred_at + timedelta(seconds=1),
        )


async def test_connect_retry_fails_closed_on_unrelated_exact_recorded_result():
    request = _authorization_request()
    result = await _build_result(
        request, (_acquired_markdown_file("notes/a.md"), _acquired_markdown_file("notes/b.md"))
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)
    _, session = await _seeded_session(store)
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request, result=result, session=session, user=_owner(), runtime=runtime, occurred_at=_AUTHORIZED_AT
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )
    occurred_at = approved_at + timedelta(seconds=1)

    await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=approval.approval.receipt_ref,
        user=_owner(),
        runtime=runtime,
        occurred_at=occurred_at,
    )

    other_request = _authorization_request(mapping_scopes=(_scope(mapping_id="mapping-b", include=("notes/*.md",)),))
    other_result = await _build_result(
        other_request, (_acquired_markdown_file("notes/c.md"), _acquired_markdown_file("notes/d.md"))
    )
    await repository.persist(other_request, other_result, _AUTHORIZED_AT)

    with pytest.raises(LocalSourceConnectSourceProgressionConflict):
        await connect_local_source_connect_scope(
            request=other_request,
            result=other_result,
            session=scope.session.revision,
            proposal=scope.proposal,
            approval_receipt_ref=approval.approval.receipt_ref,
            user=_owner(),
            runtime=runtime,
            occurred_at=occurred_at,
        )

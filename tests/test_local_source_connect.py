"""Tests for the pure Connect PREVIEW contracts (ACE PI13 WS2)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectAuthorizationResult,
    LocalSourceConnectError,
    LocalSourceConnectPreview,
    LocalSourceConnectPreviewRequest,
    LocalSourceMappingModuleAmbiguousError,
    LocalSourceMappingModuleInvalidError,
    LocalSourceMappingModuleNotFoundError,
    LocalSourceMappingNotFoundError,
    LocalSourceMappingScope,
    LocalSourceMappingScopeInvalidError,
    authorize_local_source_connect,
    preview_local_source_connect,
    resolve_installed_local_source_mapping_scopes,
)
from ace.application.source_snapshot_provider import SourceSnapshotRequestV1Alpha1
from ace.core.contracts import canonical_hash
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.core.source import SourceAcquisitionMode
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.source_mapping import (
    SOURCE_MAPPING_MODULE_VERSION,
    AttributeMappingV1,
    SourceMappingModuleV1,
    SourceMappingRuleV1,
)

NONEXISTENT_ROOT = "/nonexistent/pi13-ws2/local-root"


def _pack() -> CompiledPackRefV1:
    digest = canonical_hash({"pack": "pi13-ws2"})
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


def _request(**overrides) -> LocalSourceConnectPreviewRequest:
    values = dict(
        product_id="product:pi13-ws2",
        actor_ref="actor:reviewer-1",
        pack=_pack(),
        profile_id="profile-a",
        profile_digest=f"sha256:{canonical_hash({'profile': 'a'})}",
        source_group_id="source-group-a",
        expected_contribution="A cited orientation over the exact authorized local scope.",
        authorized_root=NONEXISTENT_ROOT,
        mapping_scopes=(_scope(),),
        exclude=(),
    )
    values.update(overrides)
    return LocalSourceConnectPreviewRequest(**values)


@pytest.fixture(autouse=True)
def _forbid_filesystem_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove Connect preview never touches the filesystem or the clock."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("Connect PREVIEW must not touch the filesystem")

    monkeypatch.setattr(Path, "exists", _boom)
    monkeypatch.setattr(Path, "stat", _boom)
    monkeypatch.setattr(Path, "resolve", _boom)
    monkeypatch.setattr(Path, "glob", _boom)
    monkeypatch.setattr(Path, "open", _boom)
    monkeypatch.setattr(Path, "read_bytes", _boom)
    monkeypatch.setattr(os.path, "exists", _boom)
    monkeypatch.setattr(os, "stat", _boom)


def test_preview_succeeds_against_a_nonexistent_absolute_root() -> None:
    request = _request()
    preview = preview_local_source_connect(request)
    assert isinstance(preview, LocalSourceConnectPreview)
    assert preview.authorized_root == NONEXISTENT_ROOT


def test_preview_flags_are_exact_truths() -> None:
    preview = preview_local_source_connect(_request())
    assert preview.read_only is True
    assert preview.acquisition_mode is SourceAcquisitionMode.LOCAL
    assert preview.network_capture_performed is False
    assert preview.write_access_requested is False
    assert preview.reusable_authority is False


def test_preview_identity_is_deterministic() -> None:
    first = preview_local_source_connect(_request())
    second = preview_local_source_connect(_request())
    assert first.preview_id == second.preview_id
    assert first.preview_digest == second.preview_digest
    assert first.preview_id is not None
    assert first.preview_digest is not None


def test_preview_identity_changes_with_material() -> None:
    base = preview_local_source_connect(_request())
    changed = preview_local_source_connect(_request(source_group_id="source-group-b"))
    assert base.preview_id != changed.preview_id
    assert base.preview_digest != changed.preview_digest


def test_preview_include_is_deterministic_union_of_scopes() -> None:
    scopes = (
        _scope(mapping_id="mapping-a", include=("b/*.md", "a/*.md")),
        _scope(mapping_id="mapping-b", include=("c/*.md",)),
    )
    preview = preview_local_source_connect(_request(mapping_scopes=scopes))
    assert preview.include == ("a/*.md", "b/*.md", "c/*.md")


def test_ambiguous_include_across_mapping_scopes_is_rejected() -> None:
    scopes = (
        _scope(mapping_id="mapping-a", include=("shared/*.md",)),
        _scope(mapping_id="mapping-b", include=("shared/*.md",)),
    )
    with pytest.raises(ValidationError):
        _request(mapping_scopes=scopes)


def test_duplicate_mapping_ids_are_rejected() -> None:
    scopes = (_scope(mapping_id="mapping-a"), _scope(mapping_id="mapping-a", include=("other/*.md",)))
    with pytest.raises(ValidationError):
        _request(mapping_scopes=scopes)


def test_empty_mapping_include_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _scope(include=())


def test_duplicate_exclude_expressions_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _request(exclude=("drafts/*.md", "drafts/*.md"))


def test_relative_authorized_root_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _request(authorized_root="relative/local-root")


def test_tampered_preview_id_is_rejected() -> None:
    preview = preview_local_source_connect(_request())
    tampered = preview.model_dump(mode="python")
    tampered["preview_id"] = "local_source_connect_preview:" + "0" * 32
    with pytest.raises(ValidationError):
        LocalSourceConnectPreview.model_validate(tampered)


def test_tampered_preview_digest_is_rejected() -> None:
    preview = preview_local_source_connect(_request())
    tampered = preview.model_dump(mode="python")
    tampered["preview_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError):
        LocalSourceConnectPreview.model_validate(tampered)


def test_strict_extra_fields_are_rejected_on_request() -> None:
    with pytest.raises(ValidationError):
        LocalSourceConnectPreviewRequest(
            **_request().model_dump(mode="python"),
            unexpected_field="not-allowed",
        )


def test_strict_extra_fields_are_rejected_on_preview() -> None:
    preview = preview_local_source_connect(_request())
    payload = preview.model_dump(mode="python")
    payload["unexpected_field"] = "not-allowed"
    with pytest.raises(ValidationError):
        LocalSourceConnectPreview.model_validate(payload)


def test_strict_extra_fields_are_rejected_on_mapping_scope() -> None:
    with pytest.raises(ValidationError):
        LocalSourceMappingScope(
            **_scope().model_dump(mode="python"),
            unexpected_field="not-allowed",
        )


def test_preview_local_source_connect_rejects_a_request_that_fails_revalidation() -> None:
    request = _request()
    broken = LocalSourceConnectPreviewRequest.model_construct(
        product_id=request.product_id,
        actor_ref=request.actor_ref,
        pack=request.pack,
        profile_id=request.profile_id,
        profile_digest=request.profile_digest,
        source_group_id=request.source_group_id,
        expected_contribution=request.expected_contribution,
        authorized_root="relative/not-absolute",
        mapping_scopes=request.mapping_scopes,
        exclude=request.exclude,
    )
    with pytest.raises(LocalSourceConnectError):
        preview_local_source_connect(broken)


def test_preview_local_source_connect_revalidates_and_derives(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    preview = preview_local_source_connect(request)
    assert preview.mapping_scopes == request.mapping_scopes
    assert preview.exclude == request.exclude
    assert preview.pack == request.pack


# --- authorize_local_source_connect: authorization tests (ACE PI13 WS2) ---

SPECIAL_ROOT = "/root with space/#dir%name"


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
    """Records each snapshot call and returns a preconfigured acquired-file tuple."""

    def __init__(
        self,
        files: tuple[AcquiredLocalFile, ...] = (),
        *,
        identity: CapabilityArtifactIdentityV1Alpha1 | None = None,
    ) -> None:
        self.artifact_identity = identity if identity is not None else _provider_identity()
        self.files = files
        self.calls: list[SourceSnapshotRequestV1Alpha1] = []

    async def snapshot(self, request: SourceSnapshotRequestV1Alpha1) -> tuple[AcquiredLocalFile, ...]:
        self.calls.append(request)
        return self.files


_CANONICAL_PAYLOAD = '{"text":"hello"}'
_PAYLOAD_DIGEST = "sha256:" + hashlib.sha256(_CANONICAL_PAYLOAD.encode("utf-8")).hexdigest()


def _acquired_markdown_file(
    relative_path: str = "notes/a.md", *, status: str = "acquired", **overrides
) -> AcquiredLocalFile:
    values = dict(
        relative_path=relative_path,
        extension="md",
        byte_digest=f"sha256:{canonical_hash({'bytes': relative_path})}",
        size_bytes=len(_CANONICAL_PAYLOAD),
        status=status,
        structured_payload_json=_CANONICAL_PAYLOAD if status == "acquired" else None,
    )
    values.update(overrides)
    return AcquiredLocalFile(**values)


def _authorized_at() -> datetime:
    return datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _authorization_request(
    *, authorized_root: str = NONEXISTENT_ROOT, authorized: bool = True, **preview_overrides
) -> LocalSourceConnectAuthorizationRequest:
    preview = preview_local_source_connect(_request(authorized_root=authorized_root, **preview_overrides))
    return LocalSourceConnectAuthorizationRequest(
        preview=preview,
        authorized=authorized,
        authorized_at=_authorized_at(),
    )


async def test_authorization_request_requires_authorized_true() -> None:
    preview = preview_local_source_connect(_request())
    with pytest.raises(ValidationError):
        LocalSourceConnectAuthorizationRequest(preview=preview, authorized_at=_authorized_at())
    with pytest.raises(ValidationError):
        LocalSourceConnectAuthorizationRequest(preview=preview, authorized=False, authorized_at=_authorized_at())
    provider = SpyProvider()
    assert provider.calls == []


async def test_authorize_local_source_connect_calls_provider_once_and_builds_exact_capture() -> None:
    request = _authorization_request(authorized_root=SPECIAL_ROOT)
    acquired = _acquired_markdown_file()
    provider = SpyProvider(files=(acquired,))

    result = await authorize_local_source_connect(request, provider)

    assert len(provider.calls) == 1
    snapshot_request = provider.calls[0]
    assert snapshot_request.authorized_root == SPECIAL_ROOT
    assert snapshot_request.include == request.preview.include
    assert snapshot_request.exclude == request.preview.exclude

    assert isinstance(result, LocalSourceConnectAuthorizationResult)
    assert len(result.captures) == 1
    assert result.unsupported_files == ()
    assert result.acquisition_mode is SourceAcquisitionMode.LOCAL

    capture = result.captures[0]
    assert capture.byte_digest == acquired.byte_digest
    assert capture.size_bytes == acquired.size_bytes
    assert capture.relative_path == acquired.relative_path
    assert capture.provider == provider.artifact_identity
    assert capture.preview_id == request.preview.preview_id
    assert capture.authorization_id == request.authorization_id
    assert capture.selection.locator == acquired.relative_path
    assert capture.selection.observed_at == _authorized_at()
    assert capture.selection.captured_payload_digest == _PAYLOAD_DIGEST
    assert capture.source_uri == "file:///root%20with%20space/%23dir%25name/" + acquired.relative_path
    assert capture.selection.source_uri == capture.source_uri


async def test_authorize_local_source_connect_is_deterministic() -> None:
    request = _authorization_request()
    acquired = _acquired_markdown_file()
    first = await authorize_local_source_connect(request, SpyProvider(files=(acquired,)))
    second = await authorize_local_source_connect(request, SpyProvider(files=(acquired,)))
    assert first.result_id == second.result_id
    assert first.result_digest == second.result_digest


async def test_strict_revalidation_rejects_tampered_authorization_result() -> None:
    request = _authorization_request()
    result = await authorize_local_source_connect(request, SpyProvider(files=(_acquired_markdown_file(),)))

    tampered_authorization = result.model_dump(mode="python")
    tampered_authorization["authorization_id"] = "local_source_connect_authorization:" + "0" * 32
    with pytest.raises(ValidationError):
        LocalSourceConnectAuthorizationResult.model_validate(tampered_authorization)

    tampered_capture = result.model_dump(mode="python")
    tampered_capture["captures"][0]["capture_id"] = "local_source_connect_capture:" + "0" * 32
    with pytest.raises(ValidationError):
        LocalSourceConnectAuthorizationResult.model_validate(tampered_capture)

    tampered_result_id = result.model_dump(mode="python")
    tampered_result_id["result_id"] = "local_source_connect_authorization_result:" + "0" * 32
    with pytest.raises(ValidationError):
        LocalSourceConnectAuthorizationResult.model_validate(tampered_result_id)


async def test_strict_revalidation_rejects_a_provider_identity_mismatch_between_capture_and_result() -> None:
    request = _authorization_request()
    result = await authorize_local_source_connect(request, SpyProvider(files=(_acquired_markdown_file(),)))
    payload = result.model_dump(mode="python")
    payload["captures"][0]["provider"]["implementation_id"] = "some-other-provider"
    with pytest.raises(ValidationError):
        LocalSourceConnectAuthorizationResult.model_validate(payload)


@pytest.mark.parametrize(
    "acquired_file",
    [
        pytest.param(_acquired_markdown_file(relative_path="../escape.md"), id="traversal"),
        pytest.param(_acquired_markdown_file(relative_path="/abs/notes.md"), id="absolute"),
        pytest.param(_acquired_markdown_file(relative_path="notes\\a.md"), id="backslash"),
        pytest.param(_acquired_markdown_file(relative_path="notes/missing.txt"), id="outside_include"),
        pytest.param(_acquired_markdown_file(extension="txt"), id="extension_drift"),
    ],
)
async def test_authorize_local_source_connect_rejects_unsafe_or_mismatched_acquired_files(
    acquired_file: AcquiredLocalFile,
) -> None:
    request = _authorization_request()
    provider = SpyProvider(files=(acquired_file,))
    with pytest.raises(LocalSourceConnectError):
        await authorize_local_source_connect(request, provider)


async def test_authorize_local_source_connect_rejects_a_duplicate_relative_path() -> None:
    request = _authorization_request()
    acquired = _acquired_markdown_file()
    provider = SpyProvider(files=(acquired, replace(acquired)))
    with pytest.raises(LocalSourceConnectError):
        await authorize_local_source_connect(request, provider)


async def test_authorize_local_source_connect_rejects_an_excluded_path() -> None:
    request = _authorization_request(exclude=("notes/a.md",))
    provider = SpyProvider(files=(_acquired_markdown_file(),))
    with pytest.raises(LocalSourceConnectError):
        await authorize_local_source_connect(request, provider)


async def test_authorize_local_source_connect_rejects_overlapping_mapping_scope_matches() -> None:
    scopes = (
        _scope(mapping_id="mapping-a", include=("notes/*.md",)),
        _scope(mapping_id="mapping-b", include=("notes/a.md",)),
    )
    preview = preview_local_source_connect(_request(mapping_scopes=scopes))
    request = LocalSourceConnectAuthorizationRequest(preview=preview, authorized=True, authorized_at=_authorized_at())
    provider = SpyProvider(files=(_acquired_markdown_file(),))
    with pytest.raises(LocalSourceConnectError):
        await authorize_local_source_connect(request, provider)


async def test_authorize_local_source_connect_rejects_provider_identity_drift_during_snapshot() -> None:
    request = _authorization_request()

    class DriftingProvider(SpyProvider):
        async def snapshot(self, request: SourceSnapshotRequestV1Alpha1) -> tuple[AcquiredLocalFile, ...]:
            files = await super().snapshot(request)
            object.__setattr__(self, "artifact_identity", _provider_identity(implementation_id="different-provider"))
            return files

    provider = DriftingProvider(files=(_acquired_markdown_file(),))
    with pytest.raises(LocalSourceConnectError):
        await authorize_local_source_connect(request, provider)


async def test_authorize_local_source_connect_rejects_a_noncanonical_payload() -> None:
    request = _authorization_request()
    acquired = _acquired_markdown_file(structured_payload_json='{"text": "hello"}')
    provider = SpyProvider(files=(acquired,))
    with pytest.raises(LocalSourceConnectError):
        await authorize_local_source_connect(request, provider)


async def test_authorize_local_source_connect_handles_unsupported_status_with_no_payload() -> None:
    request = _authorization_request()
    acquired = _acquired_markdown_file(status="unsupported")
    provider = SpyProvider(files=(acquired,))

    result = await authorize_local_source_connect(request, provider)

    assert result.captures == ()
    assert len(result.unsupported_files) == 1
    assert result.unsupported_files[0].relative_path == acquired.relative_path
    assert result.unsupported_files[0].reason == "unsupported"


async def test_authorize_local_source_connect_rejects_unsupported_status_with_a_payload() -> None:
    request = _authorization_request()
    acquired = _acquired_markdown_file(status="unsupported", structured_payload_json=_CANONICAL_PAYLOAD)
    provider = SpyProvider(files=(acquired,))
    with pytest.raises(LocalSourceConnectError):
        await authorize_local_source_connect(request, provider)


async def test_authorize_local_source_connect_never_touches_the_filesystem() -> None:
    """The autouse fixture patches Path/os accessors to raise; the service must not call them."""

    request = _authorization_request()
    result = await authorize_local_source_connect(request, SpyProvider(files=(_acquired_markdown_file(),)))
    assert len(result.captures) == 1


def _installed_mapping_rule(mapping_id: str = "mapping-a") -> SourceMappingRuleV1:
    return SourceMappingRuleV1(
        mapping_id=mapping_id,
        source_definition_ref="source-def-a",
        source_type_ref="source_type:local_files",
        capability_requirement_id="local_files_snapshot",
        authority_request_id="read_local_files",
        allowed_uri_schemes=("file",),
        subject_binding_id="subject-a",
        entity_type_id="entity-a",
        attribute_mappings=(AttributeMappingV1(attribute_id="body", source_pointer="/body"),),
        static_confidence=1.0,
    )


def _installed_module(
    *,
    module_id: str = "source-group-a",
    contract: str = SOURCE_MAPPING_MODULE_VERSION,
    mappings: tuple[SourceMappingRuleV1, ...] | None = None,
    canonical_payload: str | None = None,
) -> SimpleNamespace:
    module = SourceMappingModuleV1(
        module_id=module_id,
        mappings=mappings if mappings is not None else (_installed_mapping_rule(),),
    )
    return SimpleNamespace(
        contract=contract,
        module_id=module_id,
        canonical_payload=canonical_payload if canonical_payload is not None else module.model_dump_json(),
    )


def test_resolve_installed_local_source_mapping_scopes_derives_exact_scopes() -> None:
    scopes = resolve_installed_local_source_mapping_scopes(
        pack_modules=(_installed_module(),),
        source_group_id="source-group-a",
        selected_mapping_scopes=(("mapping-a", ("notes/*.md",)),),
    )

    assert len(scopes) == 1
    scope = scopes[0]
    installed = _installed_mapping_rule()
    assert scope.mapping_id == installed.mapping_id
    assert scope.source_definition_ref == installed.source_definition_ref
    assert scope.source_type_ref == installed.source_type_ref
    assert scope.subject_binding_id == installed.subject_binding_id
    assert scope.entity_type_id == installed.entity_type_id
    assert scope.include == ("notes/*.md",)


def test_resolve_installed_local_source_mapping_scopes_missing_module_fails_closed() -> None:
    with pytest.raises(LocalSourceMappingModuleNotFoundError):
        resolve_installed_local_source_mapping_scopes(
            pack_modules=(_installed_module(module_id="other-group"),),
            source_group_id="source-group-a",
            selected_mapping_scopes=(("mapping-a", ("notes/*.md",)),),
        )


def test_resolve_installed_local_source_mapping_scopes_ignores_non_mapping_contract_modules() -> None:
    with pytest.raises(LocalSourceMappingModuleNotFoundError):
        resolve_installed_local_source_mapping_scopes(
            pack_modules=(_installed_module(contract="ace.intelligence.other-module/v1alpha1"),),
            source_group_id="source-group-a",
            selected_mapping_scopes=(("mapping-a", ("notes/*.md",)),),
        )


def test_resolve_installed_local_source_mapping_scopes_ambiguous_module_fails_closed() -> None:
    with pytest.raises(LocalSourceMappingModuleAmbiguousError):
        resolve_installed_local_source_mapping_scopes(
            pack_modules=(_installed_module(), _installed_module()),
            source_group_id="source-group-a",
            selected_mapping_scopes=(("mapping-a", ("notes/*.md",)),),
        )


def test_resolve_installed_local_source_mapping_scopes_invalid_module_payload_fails_closed() -> None:
    with pytest.raises(LocalSourceMappingModuleInvalidError):
        resolve_installed_local_source_mapping_scopes(
            pack_modules=(_installed_module(canonical_payload="{}"),),
            source_group_id="source-group-a",
            selected_mapping_scopes=(("mapping-a", ("notes/*.md",)),),
        )


def test_resolve_installed_local_source_mapping_scopes_missing_mapping_fails_closed() -> None:
    with pytest.raises(LocalSourceMappingNotFoundError):
        resolve_installed_local_source_mapping_scopes(
            pack_modules=(_installed_module(mappings=(_installed_mapping_rule("other-mapping"),)),),
            source_group_id="source-group-a",
            selected_mapping_scopes=(("mapping-a", ("notes/*.md",)),),
        )


def test_resolve_installed_local_source_mapping_scopes_invalid_include_fails_closed() -> None:
    with pytest.raises(LocalSourceMappingScopeInvalidError):
        resolve_installed_local_source_mapping_scopes(
            pack_modules=(_installed_module(),),
            source_group_id="source-group-a",
            selected_mapping_scopes=(("mapping-a", ()),),
        )

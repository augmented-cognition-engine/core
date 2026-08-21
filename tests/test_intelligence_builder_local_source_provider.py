"""Tests for the recorded local-source RegisteredSourceOptionProvider adapter (PI13 WS3)."""

from __future__ import annotations

import json
import unittest.mock
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from ace.application.intelligence_builder_contracts import (
    ConnectionEffect,
    SourceScopeProposalV1,
    SourceScopeSelectionV1,
    SourceValueKind,
)
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
from core.engine.core.intelligence_builder_local_source_provider import (
    MAX_FIELD_PROFILES,
    MAX_RECORDED_CAPTURES,
    RecordedLocalSourceOptionProvider,
    RecordedLocalSourceOptionProviderConflict,
    RecordedLocalSourceOptionProviderDenied,
    recorded_capture_json_leaves,
)

pytestmark = pytest.mark.unit

_AUTHORIZED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
_PRODUCT_ID = "product:ws3-local-source-provider"


def _pack() -> CompiledPackRefV1:
    digest = canonical_hash({"pack": "pi13-ws3-local-source-provider"})
    return CompiledPackRefV1(
        pack_id="pack-a",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{digest[:32]}",
        pack_digest=f"sha256:{digest}",
    )


def _scope(mapping_id: str = "mapping-a", include: tuple[str, ...] = ("notes/*.json",)) -> LocalSourceMappingScope:
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
        product_id=_PRODUCT_ID,
        actor_ref="actor:owner",
        pack=_pack(),
        profile_id="profile-a",
        profile_digest=f"sha256:{canonical_hash({'profile': 'a'})}",
        source_group_id="source-group-a",
        expected_contribution="A cited orientation over the exact authorized local scope.",
        authorized_root="/nonexistent/pi13-ws3/local-source-provider-root",
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


def _canonical_json(value) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _acquired_json_file(relative_path: str, payload) -> AcquiredLocalFile:
    body = _canonical_json(payload)
    return AcquiredLocalFile(
        relative_path=relative_path,
        extension="json",
        byte_digest=f"sha256:{canonical_hash({'bytes': relative_path})}",
        size_bytes=len(body),
        status="acquired",
        structured_payload_json=body,
    )


async def _authorize(files: tuple[AcquiredLocalFile, ...], **preview_overrides):
    request = _authorization_request(**preview_overrides)
    return await authorize_local_source_connect(request, SpyProvider(files=files))


_NESTED_PAYLOAD = {
    "title": "alpha",
    "a/b": {"c~d": "value"},
    "count": 3,
    "score": 1.5,
    "active": True,
    "deleted": None,
    "created_at": "2026-08-20T00:00:00+00:00",
    "tags": ["first", "second"],
    "owner": {"name": "amirian", "nested": {"deep": "leaf"}},
}


async def _two_capture_result():
    files = (
        _acquired_json_file("notes/alpha.json", _NESTED_PAYLOAD),
        _acquired_json_file("notes/beta.json", {"title": "beta", "count": 7}),
    )
    return await _authorize(files)


def _raise_if_touched(*args, **kwargs):
    raise AssertionError("the recorded local-source provider must never touch the filesystem")


@contextmanager
def _forbidden_filesystem():
    with (
        unittest.mock.patch("os.path.exists", _raise_if_touched),
        unittest.mock.patch("os.stat", _raise_if_touched),
        unittest.mock.patch("os.scandir", _raise_if_touched),
        unittest.mock.patch("builtins.open", _raise_if_touched),
    ):
        yield


def _full_proposal(catalog, *, sample_records: int = 1) -> SourceScopeProposalV1:
    selections = tuple(
        SourceScopeSelectionV1(
            option_id=option.option_id,
            permissions=option.permission_options,
            scopes=option.scope_options,
            effects=option.allowed_effects,
            sample_records=sample_records,
        )
        for option in catalog.options
    )
    return SourceScopeProposalV1(
        session_id="session:ws3-local-source-provider",
        goal_ref="goal:bounded-orientation",
        catalog_id=str(catalog.catalog_id),
        catalog_digest=str(catalog.catalog_digest),
        selections=selections,
        created_at=_AUTHORIZED_AT,
    )


async def test_catalog_is_deterministic_and_bounded_to_recorded_captures():
    result = await _two_capture_result()
    with _forbidden_filesystem():
        provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
        first = await provider.catalog()
        second = await provider.catalog()

    assert first == second
    assert first.catalog_id == second.catalog_id
    assert first.catalog_digest == second.catalog_digest
    assert len(first.options) == 2
    assert first.provider_ref == f"provider:{result.provider.implementation_id}"
    assert first.provider_digest == result.provider.artifact_digest
    for option in first.options:
        assert option.allowed_effects == (ConnectionEffect.BOUNDED_SAMPLE, ConnectionEffect.CONNECTION_TEST)
        assert option.maximum_sample_records == 1
        assert option.source_type_ref == "source_type:recorded_local_source_capture"

    other_provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    other = await other_provider.catalog()
    assert other.catalog_id == first.catalog_id
    assert other.catalog_digest == first.catalog_digest


async def test_construction_never_rereads_the_filesystem():
    result = await _two_capture_result()
    with _forbidden_filesystem():
        provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
        catalog = await provider.catalog()
        proposal = _full_proposal(catalog)
        samples = await provider.test_and_sample(proposal)

    assert len(samples) == 2


async def test_samples_bind_exact_capture_and_authorized_at():
    result = await _two_capture_result()
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    samples = await provider.test_and_sample(proposal)

    assert len(samples) == 2
    captures_by_source_ref = {capture.source_uri: capture for capture in result.captures}
    for sample in samples:
        assert sample.observed_at == _AUTHORIZED_AT
        assert sample.authoritative_config_persisted is False
        assert sample.scheduled is False
        assert sample.delivered is False
        assert sample.sample_records == 1
        capture = captures_by_source_ref[sample.source_ref]
        # evidence_digest binds to the raw captured bytes (for citation
        # resolution), not to an option/proposal/catalog digest.
        assert sample.evidence_digest == capture.byte_digest
        assert sample.evidence_digest != capture.capture_id


async def test_nested_pointer_escaping_type_and_null_handling():
    result = await _two_capture_result()
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    samples = await provider.test_and_sample(proposal)
    alpha_source_uri = next(
        capture.source_uri for capture in result.captures if capture.relative_path == "notes/alpha.json"
    )
    alpha_sample = next(sample for sample in samples if sample.source_ref == alpha_source_uri)
    assert alpha_sample.source_ref == alpha_source_uri
    fields = {field.field_path: field for field in alpha_sample.fields}

    assert fields["/title"].value_kind == SourceValueKind.STRING
    assert fields["/count"].value_kind == SourceValueKind.INTEGER
    assert fields["/score"].value_kind == SourceValueKind.NUMBER
    assert fields["/active"].value_kind == SourceValueKind.BOOLEAN
    assert fields["/deleted"].value_kind == SourceValueKind.UNKNOWN
    assert fields["/deleted"].nullable is True
    assert fields["/created_at"].value_kind == SourceValueKind.DATETIME
    assert fields["/tags/0"].value_kind == SourceValueKind.STRING
    assert fields["/tags/1"].value_kind == SourceValueKind.STRING
    assert fields["/owner/nested/deep"].value_kind == SourceValueKind.STRING
    # RFC6901 escaping: "~" -> "~0", "/" -> "~1", applied in that order per token.
    assert "/a~1b/c~0d" in fields
    assert fields["/a~1b/c~0d"].value_kind == SourceValueKind.STRING


async def test_rejects_a_single_recorded_capture():
    result = await _authorize((_acquired_json_file("notes/alpha.json", {"title": "alpha"}),))
    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)


async def test_rejects_captures_beyond_the_bounded_maximum(monkeypatch):
    files = tuple(
        _acquired_json_file(f"notes/note-{index:03d}.json", {"index": index})
        for index in range(MAX_RECORDED_CAPTURES + 1)
    )
    result = await _authorize(files, mapping_scopes=(_scope(include=("notes/*.json",)),))
    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)


async def test_rejects_a_proposal_that_widens_the_recorded_scope():
    result = await _two_capture_result()
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    option = catalog.options[0]
    widened_selection = SourceScopeSelectionV1(
        option_id=option.option_id,
        permissions=option.permission_options,
        scopes=option.scope_options,
        effects=option.allowed_effects,
        sample_records=option.maximum_sample_records + 1,
    )
    proposal = SourceScopeProposalV1(
        session_id="session:ws3-local-source-provider",
        goal_ref="goal:bounded-orientation",
        catalog_id=str(catalog.catalog_id),
        catalog_digest=str(catalog.catalog_digest),
        selections=(widened_selection,),
        created_at=_AUTHORIZED_AT,
    )

    with pytest.raises(RecordedLocalSourceOptionProviderConflict):
        await provider.test_and_sample(proposal)


async def test_rejects_a_scalar_root_capture_shape():
    result = await _authorize(
        (
            _acquired_json_file("notes/alpha.json", "not an object or array"),
            _acquired_json_file("notes/beta.json", {"title": "beta"}),
        )
    )
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        await provider.test_and_sample(proposal)


async def test_rejects_a_null_root_capture_shape():
    result = await _authorize(
        (
            _acquired_json_file("notes/alpha.json", None),
            _acquired_json_file("notes/beta.json", {"title": "beta"}),
        )
    )
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        await provider.test_and_sample(proposal)


async def test_rejects_an_empty_object_capture_shape():
    result = await _authorize(
        (
            _acquired_json_file("notes/alpha.json", {}),
            _acquired_json_file("notes/beta.json", {"title": "beta"}),
        )
    )
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        await provider.test_and_sample(proposal)


async def test_rejects_an_empty_array_capture_shape():
    result = await _authorize(
        (
            _acquired_json_file("notes/alpha.json", []),
            _acquired_json_file("notes/beta.json", {"title": "beta"}),
        )
    )
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        await provider.test_and_sample(proposal)


async def test_rejects_an_array_of_empty_objects_with_no_leaves():
    result = await _authorize(
        (
            _acquired_json_file("notes/alpha.json", [{}, {}]),
            _acquired_json_file("notes/beta.json", {"title": "beta"}),
        )
    )
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        await provider.test_and_sample(proposal)


_MARKDOWN_STRUCTURED_UNITS = [
    {"anchor_kind": "heading", "anchor_value": "Notes", "text": "alpha"},
    {"anchor_kind": "paragraph", "anchor_value": "Notes", "text": "beta detail"},
]


async def test_accepts_the_real_markdown_structured_unit_array_shape():
    result = await _authorize(
        (
            _acquired_json_file("notes/alpha.json", _MARKDOWN_STRUCTURED_UNITS),
            _acquired_json_file("notes/beta.json", {"title": "beta"}),
        )
    )
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    samples = await provider.test_and_sample(proposal)
    alpha_source_uri = next(
        capture.source_uri for capture in result.captures if capture.relative_path == "notes/alpha.json"
    )
    alpha_sample = next(sample for sample in samples if sample.source_ref == alpha_source_uri)
    fields = {field.field_path: field for field in alpha_sample.fields}

    assert fields["/0/anchor_kind"].value_kind == SourceValueKind.STRING
    assert fields["/0/anchor_kind"].observed_count == 1
    assert fields["/0/anchor_value"].value_kind == SourceValueKind.STRING
    assert fields["/0/text"].value_kind == SourceValueKind.STRING
    assert fields["/1/anchor_kind"].value_kind == SourceValueKind.STRING
    assert fields["/1/anchor_value"].value_kind == SourceValueKind.STRING
    assert fields["/1/text"].value_kind == SourceValueKind.STRING


async def test_rejects_a_proposal_that_omits_a_recorded_permission_scope_or_effect():
    result = await _two_capture_result()
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    option = catalog.options[0]
    narrowed_selection = SourceScopeSelectionV1(
        option_id=option.option_id,
        permissions=option.permission_options,
        scopes=option.scope_options,
        # Omits CONNECTION_TEST from the option's full allowed_effects set:
        # this must be rejected exactly like widening is.
        effects=(option.allowed_effects[0],),
        sample_records=option.maximum_sample_records,
    )
    proposal = SourceScopeProposalV1(
        session_id="session:ws3-local-source-provider",
        goal_ref="goal:bounded-orientation",
        catalog_id=str(catalog.catalog_id),
        catalog_digest=str(catalog.catalog_digest),
        selections=(narrowed_selection,),
        created_at=_AUTHORIZED_AT,
    )

    with pytest.raises(RecordedLocalSourceOptionProviderConflict):
        await provider.test_and_sample(proposal)


async def test_rejects_captured_payload_shape_beyond_the_bounded_depth_limit(monkeypatch):
    import core.engine.core.intelligence_builder_local_source_provider as module

    monkeypatch.setattr(module, "MAX_JSON_DEPTH", 2)
    deeply_nested = {"a": {"b": {"c": {"d": "too deep"}}}}
    result = await _authorize(
        (
            _acquired_json_file("notes/alpha.json", deeply_nested),
            _acquired_json_file("notes/beta.json", {"title": "beta"}),
        )
    )
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        await provider.test_and_sample(proposal)


async def test_rejects_captured_payload_shape_beyond_the_bounded_field_count(monkeypatch):
    import core.engine.core.intelligence_builder_local_source_provider as module

    monkeypatch.setattr(module, "MAX_FIELD_PROFILES", 3)
    result = await _two_capture_result()
    provider = RecordedLocalSourceOptionProvider(result=result, authorized_at=_AUTHORIZED_AT)
    catalog = await provider.catalog()
    proposal = _full_proposal(catalog)

    with pytest.raises(RecordedLocalSourceOptionProviderDenied):
        await provider.test_and_sample(proposal)

    # Confirm the bound is real by checking the unpatched constant is larger
    # than the field count this fixture's alpha capture actually produces.
    assert MAX_FIELD_PROFILES > 3


def test_recorded_capture_json_leaves_flattens_nested_list_and_object_pointers():
    payload = {
        "entries": [
            {"anchor_value": "a1", "text": "hello"},
            {"anchor_value": "a2", "text": "world"},
        ],
        "title": "alpha",
    }

    leaves = recorded_capture_json_leaves(payload)

    assert leaves == {
        "/entries/0/anchor_value": "a1",
        "/entries/0/text": "hello",
        "/entries/1/anchor_value": "a2",
        "/entries/1/text": "world",
        "/title": "alpha",
    }

"""Tests for the Personal Intelligence build executor (PI13 WS3)."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import EntryPoint
from types import SimpleNamespace

import pytest

from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    AuthorizedIntelligenceBuild,
    IntelligenceBuildHostServices,
    IntelligenceBuildStartV1,
    IntelligenceBuildStartV1Alpha2,
)
from ace.application.intelligence_ledger import PREPARED_RECORD_SPACE
from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectPreviewRequest,
    LocalSourceMappingScope,
    authorize_local_source_connect,
    preview_local_source_connect,
)
from ace.application.recorded_source_admission import RecordedSourceAdmission
from ace.core.contracts import canonical_hash
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordV1
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, ResolvedApprovalReceiptV1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    EntitySnapshotV1Alpha1,
    EvidenceAcquisitionMode,
    IntelligenceResourceMode,
    ObservationV1Alpha1,
)
from ace.intelligence.contracts.source_mapping import ResolvedSubjectBindingV1Alpha1
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from core.engine.core.intelligence_build_executor_registry import (
    IntelligenceBuildExecutorRegistryError,
    _reset_intelligence_build_executor_registry_for_tests,
    load_installed_intelligence_build_executors,
    resolve_intelligence_build_executor,
)
from core.engine.core.local_source_connect import LocalSourceConnectRecordRepository
from core.engine.personal_intelligence.build_executor import (
    PERSONAL_PROFILE_ID,
    PersonalIntelligenceBuildExecutor,
    PersonalIntelligenceBuildExecutorError,
)

pytestmark = pytest.mark.asyncio

PRODUCT = "product:pi13-ws3"
ACTOR = "actor:pi13-ws3-owner"
CANONICAL_PAYLOAD = '[{"anchor_kind":"heading","anchor_value":"PI13 WS0 Vault Note","text":"This fixture note."}]'


def _pack() -> CompiledPackRefV1:
    digest = canonical_hash({"pack": "pi13-ws3"})
    return CompiledPackRefV1(
        pack_id="personal_intelligence",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{digest[:32]}",
        pack_digest=f"sha256:{digest}",
    )


def _scope() -> LocalSourceMappingScope:
    return LocalSourceMappingScope(
        mapping_id="local_markdown_note",
        source_definition_ref="local_markdown_notes",
        source_type_ref="markdown.note",
        subject_binding_id="note_subject",
        entity_type_id="note",
        include=("notes/*.md",),
    )


def _preview_request() -> LocalSourceConnectPreviewRequest:
    return LocalSourceConnectPreviewRequest(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        pack=_pack(),
        profile_id=PERSONAL_PROFILE_ID,
        profile_digest=f"sha256:{canonical_hash({'profile': 'personal'})}",
        source_group_id="vault_notes",
        expected_contribution="A cited orientation over the reviewed vault.",
        authorized_root="/nonexistent/pi13-ws3-root",
        mapping_scopes=(_scope(),),
        exclude=(),
    )


class _SpyProvider:
    def __init__(self, files: tuple[AcquiredLocalFile, ...]) -> None:
        self.artifact_identity = CapabilityArtifactIdentityV1Alpha1(
            capability="source_snapshot",
            contract="ace.source.snapshot/v1alpha1",
            implementation_id="spy-provider",
            implementation_version="1.0.0",
            artifact_digest=f"sha256:{canonical_hash({'provider': 'spy'})}",
        )
        self.files = files

    async def snapshot(self, request):
        return self.files


async def _persist_one_capture(store: InMemoryImmutableRecordStore, *, authorized_at: datetime):
    preview = preview_local_source_connect(_preview_request())
    request = LocalSourceConnectAuthorizationRequest(preview=preview, authorized=True, authorized_at=authorized_at)
    file = AcquiredLocalFile(
        relative_path="notes/vault.md",
        extension="md",
        byte_digest=f"sha256:{canonical_hash({'bytes': 'vault.md'})}",
        size_bytes=len(CANONICAL_PAYLOAD),
        status="acquired",
        structured_payload_json=CANONICAL_PAYLOAD,
    )
    result = await authorize_local_source_connect(request, _SpyProvider(files=(file,)))
    repository = LocalSourceConnectRecordRepository(store)
    reopened = await repository.persist(request, result, authorized_at)
    return reopened.captures[0]


def _build(request) -> AuthorizedIntelligenceBuild:
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:pi13-ws3",
        authentication_receipt_digest="sha256:" + "1" * 64,
        authenticated_at=datetime(2026, 8, 20, 11, tzinfo=UTC),
        expires_at=datetime(2026, 8, 20, 13, tzinfo=UTC),
    )
    authority_use = AuthorityUseReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authenticated_context=context,
        use_subject_ref="intelligence_build:pi13-ws3",
        use_subject_digest="sha256:" + "2" * 64,
        operation="start_intelligence_build",
        authority="intelligence_build",
        grant_ref="authority_grant:pi13-ws3",
        grant_hash="3" * 64,
        evaluated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=PRODUCT,
            state_id="authority_grant:pi13-ws3",
            sequence=1,
            revision_id="authority_grant_revision:pi13-ws3",
            commit_receipt_id="governed_state_commit:pi13-ws3",
        ),
    )
    approval = ResolvedApprovalReceiptV1(
        receipt_ref="approval_receipt:pi13-ws3",
        product_id=PRODUCT,
        subject_ref="activation_spec:pi13-ws3",
        actor_ref=ACTOR,
        receipt_hash="4" * 64,
        approved_at=datetime(2026, 8, 20, 11, 30, tzinfo=UTC),
    )
    return AuthorizedIntelligenceBuild(
        build_id="intelligence_build:pi13-ws3",
        request_digest="sha256:" + "2" * 64,
        product_id=PRODUCT,
        actor_ref=ACTOR,
        request=request,
        authority_use=authority_use,
        activation_approval=approval,
    )


def _v1alpha2_request(*, selection_refs=(), profile_id=PERSONAL_PROFILE_ID):
    return IntelligenceBuildStartV1Alpha2(
        authority_grant_ref="authority_grant:pi13-ws3",
        resource_authority_grant_ref="authority_grant:pi13-ws3-resources",
        activation_approval_receipt_ref="approval_receipt:pi13-ws3",
        activation_approval_subject_ref="activation_spec:pi13-ws3",
        client_request_id="atrium_request:pi13-ws3",
        profile_id=profile_id,
        subject="Track the reviewed Personal vault for material changes.",
        outcome_id="decision_readiness",
        source_group_ids=("vault_notes",),
        recorded_source_selection_refs=selection_refs,
        cadence_id="daily_pulse",
        approved_effects=REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
        requested_at=datetime(2026, 8, 20, 11, 45, tzinfo=UTC),
    )


CORPUS_AS_OF = datetime(2026, 8, 20, 11, 40, tzinfo=UTC)
CORPUS_AVAILABLE_AT = datetime(2026, 8, 20, 11, 50, tzinfo=UTC)
CORPUS_COMMITTED_AT = datetime(2026, 8, 20, 11, 55, tzinfo=UTC)


def _activation_revision() -> ActivationRevisionReferenceV1Alpha1:
    return ActivationRevisionReferenceV1Alpha1(
        product_id=PRODUCT,
        activation_key="personal_intelligence",
        activation_id=f"domain_activation:{canonical_hash([PRODUCT, 'personal_intelligence'])[:32]}",
        revision=1,
        revision_id="activation_revision:" + "5" * 32,
        revision_digest="sha256:" + "5" * 64,
    )


def _admission(
    *,
    as_of: datetime = CORPUS_AS_OF,
    available_at: datetime = CORPUS_AVAILABLE_AT,
    committed_at: datetime = CORPUS_COMMITTED_AT,
    entity_as_of: datetime | None = None,
) -> RecordedSourceAdmission:
    revision = _activation_revision()
    observation = ObservationV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=revision,
        as_of=as_of,
        source_ref="source_snapshot:" + "6" * 32,
        source_digest="sha256:" + "6" * 64,
        acquisition_mode=EvidenceAcquisitionMode.RECORDED_REPLAY,
        acquisition_receipt_ref="recorded_source_acquisition:" + "7" * 32,
        acquisition_receipt_digest="sha256:" + "7" * 64,
        observed_at=as_of,
        ingested_at=available_at,
        payload=CanonicalJsonValueV1Alpha1(value_json='{"text":"fixture"}'),
        confidence=1.0,
    )
    entity = EntitySnapshotV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=revision,
        as_of=entity_as_of if entity_as_of is not None else as_of,
        entity_ref="note:vault",
        entity_type_ref="entity_type:note",
        attributes=CanonicalJsonValueV1Alpha1(value_json='{"title":"fixture"}'),
        projected_at=available_at,
        confidence=1.0,
    )
    record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space=PREPARED_RECORD_SPACE,
        record_kind="observation",
        record_key=str(observation.resource_id),
        payload_contract=observation.contract,
        payload=observation.model_dump(mode="python"),
        as_of=observation.as_of,
        available_at=available_at,
        processing_order=0,
    )
    receipt = AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space=PREPARED_RECORD_SPACE,
        transaction_key="recorded_source_admission:" + "8" * 32,
        records=(record,),
        submitted_at=committed_at,
    ).receipt()
    return RecordedSourceAdmission(
        acquisition_receipts=(),
        source_snapshots=(),
        observations=(observation,),
        entity_snapshots=(entity,),
        transaction_receipt=receipt,
        replayed=False,
    )


class _FakeRecordedSources:
    def __init__(self, *, admission=None, events=None) -> None:
        self.bind_calls = []
        self.admit_calls = []
        self.admission = admission if admission is not None else _admission()
        self.events = events if events is not None else []

    def bind_subject(self, *, subject_binding_id, entity_type_id, entity_ref):
        self.bind_calls.append((subject_binding_id, entity_type_id, entity_ref))
        return ResolvedSubjectBindingV1Alpha1(
            product_id=PRODUCT,
            activation_revision=_activation_revision(),
            subject_binding_id=subject_binding_id,
            entity_type_id=entity_type_id,
            entity_ref=entity_ref,
        )

    async def admit(self, materials):
        self.admit_calls.append(materials)
        self.events.append("admit")
        return self.admission


class _FakeFirstBrief:
    def __init__(self, *, events=None) -> None:
        self.requests = []
        self.events = events if events is not None else []

    async def create_initial_corpus_first_brief(self, request):
        self.requests.append(request)
        self.events.append("first_brief")
        return "first-brief-outcome"


class _FailingFirstBrief(_FakeFirstBrief):
    async def create_initial_corpus_first_brief(self, request):
        raise RuntimeError("simulated first-Brief failure")


class _FailingRecordedSources(_FakeRecordedSources):
    async def admit(self, materials):
        raise AssertionError("admit must not be called when a guard should fail closed")

    def bind_subject(self, **kwargs):
        raise AssertionError("bind_subject must not be called when a guard should fail closed")


class _FakeDerivations:
    """The narrow prepared-derivation port, recording how the executor asks."""

    def __init__(self, *, outcomes=None, events=None) -> None:
        self.calls: list[dict] = []
        self.outcomes = outcomes or {}
        self.events = events if events is not None else []

    async def derive(self, request):  # pragma: no cover - the executor uses the baseline-resolving call
        raise AssertionError("the executor must let Core resolve the declared prior_snapshot baseline")

    async def derive_against_prior_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        self.events.append("derive")
        return self.outcomes.get(kwargs["current_snapshot"].resource_id)


class _MaterialOutcome:
    """Stand-in for a material PreparedShiftSignalDerivationOutcome."""

    material_shift = True

    def __init__(self, *, derivation_key: str, receipt_id: str) -> None:
        self.request = SimpleNamespace(derivation_key=derivation_key)
        self.admission = SimpleNamespace(
            attention_receipt=SimpleNamespace(
                receipt_id=receipt_id,
                receipt_digest="sha256:" + "c" * 64,
            )
        )


class _UnchangedOutcome:
    material_shift = False
    admission = None
    request = SimpleNamespace(derivation_key="prepared_derivation:unchanged")


class _RoutedFirstBrief(_FakeFirstBrief):
    """Records both Brief paths so a test can prove which one the build used."""

    def __init__(self, *, events=None) -> None:
        super().__init__(events=events)
        self.routed_requests = []

    async def create_first_brief(self, request):
        self.routed_requests.append(request)
        self.events.append("routed_brief")
        return "routed-brief-outcome"


class _FakeResources:
    def __init__(self, *, events=None) -> None:
        self.query_calls = []
        self.events = events if events is not None else []

    async def query(self, **kwargs):
        self.query_calls.append(kwargs)
        self.events.append("query")
        return "resource-page"


class _FailingLoader(LocalSourceConnectRecordRepository):
    async def load_capture(self, *args, **kwargs):
        raise RuntimeError("simulated capture loader failure")


def _host_services(*, records, recorded_sources=None, resources=None, first_brief=None, prepared_derivations=None):
    return IntelligenceBuildHostServices(
        records=records,
        resources=resources if resources is not None else _FakeResources(),
        activation_authority=object(),
        recorded_sources=recorded_sources,
        first_brief=first_brief,
        # A first read is exactly "the port reports no prior snapshot", so the
        # default double answers None rather than being absent.
        prepared_derivations=prepared_derivations if prepared_derivations is not None else _FakeDerivations(),
    )


# --- entry-point / registry ---


async def test_entry_point_target_is_zero_arg_and_registry_resolves_it() -> None:
    _reset_intelligence_build_executor_registry_for_tests()
    entry_point = EntryPoint(
        name="personal_intelligence",
        value="core.engine.personal_intelligence.build_executor:PersonalIntelligenceBuildExecutor",
        group="ace.intelligence_builders",
    )
    try:
        load_installed_intelligence_build_executors((entry_point,))
        resolved = resolve_intelligence_build_executor(PERSONAL_PROFILE_ID)
        assert isinstance(resolved, PersonalIntelligenceBuildExecutor)
        assert resolved.profile_id == PERSONAL_PROFILE_ID
    finally:
        _reset_intelligence_build_executor_registry_for_tests()


async def test_registry_rejects_a_second_executor_claiming_the_same_profile() -> None:
    _reset_intelligence_build_executor_registry_for_tests()
    entry_points = (
        EntryPoint(
            name="a",
            value="core.engine.personal_intelligence.build_executor:PersonalIntelligenceBuildExecutor",
            group="ace.intelligence_builders",
        ),
        EntryPoint(
            name="b",
            value="core.engine.personal_intelligence.build_executor:PersonalIntelligenceBuildExecutor",
            group="ace.intelligence_builders",
        ),
    )
    try:
        with pytest.raises(IntelligenceBuildExecutorRegistryError):
            load_installed_intelligence_build_executors(entry_points)
    finally:
        _reset_intelligence_build_executor_registry_for_tests()


# --- fail-closed guards ---


async def test_rejects_legacy_v1alpha1_request() -> None:
    executor = PersonalIntelligenceBuildExecutor()
    legacy_request = IntelligenceBuildStartV1(
        authority_grant_ref="authority_grant:pi13-ws3",
        resource_authority_grant_ref="authority_grant:pi13-ws3-resources",
        activation_approval_receipt_ref="approval_receipt:pi13-ws3",
        activation_approval_subject_ref="activation_spec:pi13-ws3",
        client_request_id="atrium_request:pi13-ws3",
        profile_id=PERSONAL_PROFILE_ID,
        subject="Track the reviewed Personal vault for material changes.",
        outcome_id="decision_readiness",
        cadence_id="daily_pulse",
        approved_effects=REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
        requested_at=datetime(2026, 8, 20, 11, 45, tzinfo=UTC),
    )
    build = _build(legacy_request)
    with pytest.raises(PersonalIntelligenceBuildExecutorError, match="v1alpha2"):
        await executor.start(
            build, _host_services(records=InMemoryImmutableRecordStore(), recorded_sources=_FailingRecordedSources())
        )


async def test_rejects_wrong_profile() -> None:
    executor = PersonalIntelligenceBuildExecutor()
    build = _build(_v1alpha2_request(profile_id="intelligence_onboarding_profile:other"))
    with pytest.raises(PersonalIntelligenceBuildExecutorError, match="Personal onboarding profile"):
        await executor.start(
            build, _host_services(records=InMemoryImmutableRecordStore(), recorded_sources=_FailingRecordedSources())
        )


async def test_rejects_missing_recorded_sources_port() -> None:
    executor = PersonalIntelligenceBuildExecutor()
    build = _build(_v1alpha2_request())
    with pytest.raises(PersonalIntelligenceBuildExecutorError, match="recorded-source admission port"):
        await executor.start(build, _host_services(records=InMemoryImmutableRecordStore(), recorded_sources=None))


async def test_rejects_empty_selection_refs() -> None:
    executor = PersonalIntelligenceBuildExecutor()
    build = _build(_v1alpha2_request(selection_refs=()))
    with pytest.raises(PersonalIntelligenceBuildExecutorError, match="at least one reviewed"):
        await executor.start(
            build,
            _host_services(
                records=InMemoryImmutableRecordStore(),
                recorded_sources=_FailingRecordedSources(),
                first_brief=_FakeFirstBrief(),
            ),
        )


async def test_rejects_missing_first_brief_port() -> None:
    executor = PersonalIntelligenceBuildExecutor()
    build = _build(_v1alpha2_request())
    with pytest.raises(PersonalIntelligenceBuildExecutorError, match="first-Brief port"):
        await executor.start(
            build,
            _host_services(
                records=InMemoryImmutableRecordStore(),
                recorded_sources=_FailingRecordedSources(),
                first_brief=None,
            ),
        )


# --- successful path ---


async def test_successful_path_admits_exact_capture_material_and_queries_exact_kinds_and_times() -> None:
    store = InMemoryImmutableRecordStore()
    authorized_at = datetime(2026, 8, 20, 11, tzinfo=UTC)
    capture = await _persist_one_capture(store, authorized_at=authorized_at)

    build = _build(_v1alpha2_request(selection_refs=(capture.selection.reference(),)))
    events = []
    recorded_sources = _FakeRecordedSources(events=events)
    resources = _FakeResources(events=events)
    first_brief = _FakeFirstBrief(events=events)

    page = await PersonalIntelligenceBuildExecutor().start(
        build,
        _host_services(records=store, recorded_sources=recorded_sources, resources=resources, first_brief=first_brief),
    )

    assert events == ["admit", "first_brief", "query"]
    assert len(first_brief.requests) == 1
    brief_request = first_brief.requests[0]
    assert brief_request.build_id == build.build_id
    assert brief_request.build_request_digest == build.request_digest
    assert brief_request.orientation_policy_id == "personal_initial_orientation"
    assert brief_request.corpus_as_of == CORPUS_AS_OF
    assert brief_request.corpus_available_at == CORPUS_COMMITTED_AT
    assert brief_request.requested_at == CORPUS_COMMITTED_AT

    assert page == "resource-page"
    assert recorded_sources.bind_calls == [
        (capture.selection.subject_binding_id, capture.selection.entity_type_id, capture.selection.entity_ref)
    ]
    assert len(recorded_sources.admit_calls) == 1
    (materials,) = recorded_sources.admit_calls
    assert len(materials) == 1
    material = materials[0]
    assert material.source_group_id == capture.selection.source_group_id
    assert material.mapping_id == capture.selection.mapping_id
    assert material.source_definition_ref == capture.selection.source_definition_ref
    assert material.source_type_ref == capture.selection.source_type_ref
    assert material.source_uri == capture.selection.source_uri
    assert material.captured_payload_json == capture.structured_payload_json
    assert material.captured_payload_digest == capture.selection.captured_payload_digest
    assert material.source_published_at == capture.selection.source_published_at
    assert material.event_effective_at == capture.selection.event_effective_at
    assert material.observed_at == capture.selection.observed_at
    assert material.locator == capture.selection.locator
    assert material.acquisition_mode == capture.acquisition_mode

    assert len(resources.query_calls) == 1
    query = resources.query_calls[0]
    assert query["as_of"] == CORPUS_AS_OF
    assert query["available_at"] == CORPUS_COMMITTED_AT
    assert query["evaluated_at"] == CORPUS_COMMITTED_AT
    assert CORPUS_COMMITTED_AT != build.authority_use.evaluated_at
    assert query["subject_refs"] == ()
    assert query["page_size"] == 200
    assert {kind.value for kind in query["resource_kinds"]} == {"source_health", "entity", "observation", "brief"}


async def test_capture_loader_failure_is_fail_closed() -> None:
    store = InMemoryImmutableRecordStore()
    authorized_at = datetime(2026, 8, 20, 11, tzinfo=UTC)
    capture = await _persist_one_capture(store, authorized_at=authorized_at)
    build = _build(_v1alpha2_request(selection_refs=(capture.selection.reference(),)))

    executor = PersonalIntelligenceBuildExecutor()

    import core.engine.personal_intelligence.build_executor as module

    original = module.LocalSourceConnectRecordRepository
    module.LocalSourceConnectRecordRepository = _FailingLoader
    try:
        with pytest.raises(RuntimeError, match="simulated capture loader failure"):
            await executor.start(
                build,
                _host_services(records=store, recorded_sources=_FakeRecordedSources(), first_brief=_FakeFirstBrief()),
            )
    finally:
        module.LocalSourceConnectRecordRepository = original


async def test_malformed_admission_fails_closed_before_first_brief() -> None:
    store = InMemoryImmutableRecordStore()
    capture = await _persist_one_capture(store, authorized_at=datetime(2026, 8, 20, 11, tzinfo=UTC))
    build = _build(_v1alpha2_request(selection_refs=(capture.selection.reference(),)))
    recorded_sources = _FakeRecordedSources()
    recorded_sources.admission = "admitted"
    first_brief = _FakeFirstBrief()
    resources = _FakeResources()
    with pytest.raises(PersonalIntelligenceBuildExecutorError, match="exact admission material"):
        await PersonalIntelligenceBuildExecutor().start(
            build,
            _host_services(
                records=store, recorded_sources=recorded_sources, resources=resources, first_brief=first_brief
            ),
        )
    assert first_brief.requests == []
    assert resources.query_calls == []


async def test_divergent_as_of_fails_closed_before_first_brief() -> None:
    store = InMemoryImmutableRecordStore()
    capture = await _persist_one_capture(store, authorized_at=datetime(2026, 8, 20, 11, tzinfo=UTC))
    build = _build(_v1alpha2_request(selection_refs=(capture.selection.reference(),)))
    recorded_sources = _FakeRecordedSources(
        admission=_admission(entity_as_of=datetime(2026, 8, 20, 11, 35, tzinfo=UTC))
    )
    first_brief = _FakeFirstBrief()
    with pytest.raises(PersonalIntelligenceBuildExecutorError, match="share one exact as_of"):
        await PersonalIntelligenceBuildExecutor().start(
            build, _host_services(records=store, recorded_sources=recorded_sources, first_brief=first_brief)
        )
    assert first_brief.requests == []


async def test_first_brief_failure_is_fail_closed_before_query() -> None:
    store = InMemoryImmutableRecordStore()
    capture = await _persist_one_capture(store, authorized_at=datetime(2026, 8, 20, 11, tzinfo=UTC))
    build = _build(_v1alpha2_request(selection_refs=(capture.selection.reference(),)))
    resources = _FakeResources()
    with pytest.raises(RuntimeError, match="simulated first-Brief failure"):
        await PersonalIntelligenceBuildExecutor().start(
            build,
            _host_services(
                records=store,
                recorded_sources=_FakeRecordedSources(),
                resources=resources,
                first_brief=_FailingFirstBrief(),
            ),
        )
    assert resources.query_calls == []


# --- WS5: re-ingest over an already-admitted corpus ---


async def _reingest_setup(*, outcome_factory):
    """One admitted capture whose entity already has a prior snapshot."""

    store = InMemoryImmutableRecordStore()
    authorized_at = datetime(2026, 8, 20, 11, tzinfo=UTC)
    capture = await _persist_one_capture(store, authorized_at=authorized_at)
    request = _v1alpha2_request(selection_refs=(capture.selection.reference(),))
    admission = _admission()
    entity = admission.entity_snapshots[0]
    events: list[str] = []
    derivations = _FakeDerivations(
        outcomes={str(entity.resource_id): outcome_factory()},
        events=events,
    )
    first_brief = _RoutedFirstBrief(events=events)
    services = _host_services(
        records=store,
        recorded_sources=_FakeRecordedSources(admission=admission, events=events),
        first_brief=first_brief,
        prepared_derivations=derivations,
        resources=_FakeResources(events=events),
    )
    return request, admission, derivations, first_brief, services, events


async def test_a_revised_document_derives_a_shift_and_routes_a_brief_revision() -> None:
    """Second admission of an entity that already has a snapshot is a change
    event, not another first orientation."""

    request, admission, derivations, first_brief, services, events = await _reingest_setup(
        outcome_factory=lambda: _MaterialOutcome(
            derivation_key="prepared_derivation:vault-revised",
            receipt_id="attention_disposition:" + "d" * 32,
        )
    )
    build = _build(request)

    page = await PersonalIntelligenceBuildExecutor().start(build, services)

    assert page == "resource-page"
    # Core resolved the baseline; the executor never supplied one.
    assert len(derivations.calls) == 1
    call = derivations.calls[0]
    assert call["detector_id"] == "personal_note_revised"
    assert call["current_snapshot"].resource_id == str(admission.entity_snapshots[0].resource_id)
    # The routed Brief path ran, and the initial-corpus orientation did not.
    assert len(first_brief.routed_requests) == 1
    assert first_brief.requests == []
    routed = first_brief.routed_requests[0]
    assert routed.derivation_key == "prepared_derivation:vault-revised"
    assert routed.attention_receipt_id == "attention_disposition:" + "d" * 32
    # Exact order: admit, then derive, then route, then project.
    assert events == ["admit", "derive", "routed_brief", "query"]


async def test_an_unchanged_reingest_creates_no_brief_and_still_projects() -> None:
    """Re-reading an unchanged corpus must not fabricate a revision."""

    request, _, derivations, first_brief, services, events = await _reingest_setup(outcome_factory=_UnchangedOutcome)

    page = await PersonalIntelligenceBuildExecutor().start(_build(request), services)

    assert page == "resource-page"
    assert len(derivations.calls) == 1
    assert first_brief.routed_requests == []
    assert first_brief.requests == []
    assert events == ["admit", "derive", "query"]


async def test_a_first_admission_still_produces_the_initial_corpus_orientation() -> None:
    """No prior snapshot means nothing to compare; the first pass is unchanged."""

    request, _, derivations, first_brief, services, events = await _reingest_setup(outcome_factory=lambda: None)

    await PersonalIntelligenceBuildExecutor().start(_build(request), services)

    assert len(derivations.calls) == 1
    assert first_brief.routed_requests == []
    assert len(first_brief.requests) == 1
    assert events == ["admit", "derive", "first_brief", "query"]


async def test_reingest_without_a_derivation_port_fails_closed() -> None:
    """Without the derivation port the build cannot tell a revision from a first
    read, so it must refuse rather than silently re-orient."""

    store = InMemoryImmutableRecordStore()
    capture = await _persist_one_capture(store, authorized_at=datetime(2026, 8, 20, 11, tzinfo=UTC))
    request = _v1alpha2_request(selection_refs=(capture.selection.reference(),))
    services = IntelligenceBuildHostServices(
        records=store,
        resources=_FakeResources(),
        activation_authority=object(),
        recorded_sources=_FakeRecordedSources(),
        first_brief=_RoutedFirstBrief(),
        prepared_derivations=None,
    )

    with pytest.raises(PersonalIntelligenceBuildExecutorError):
        await PersonalIntelligenceBuildExecutor().start(_build(request), services)

"""Tests for the host observation-admission slice (PI13 WS3 addendum 9).

Builds one real durable Builder progression -- local Connect authorization,
source-scope proposal/approval/connect, concept-model proposal/approval --
through the existing production host bridges, then exercises
``admit_local_source_observations`` against it.
"""

from __future__ import annotations

import json
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
from ace.application.ontology_agent import OntologyAgent
from ace.application.ontology_agent_contracts import OrganizationTerminologyV1
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import MAX_CANONICAL_VALUE_CHARS
from ace.testing.immutable_records import InMemoryImmutableRecordStore
from ace.testing.ontology_agent import FixtureConceptModelStrategy
from core.engine.core.intelligence_builder_disposition_authority import (
    BuilderConceptModelApproveRequestV1Alpha1,
    BuilderSourceScopeApproveRequestV1Alpha1,
    RecordedIntelligenceBuilderDispositionAuthority,
    approve_builder_concept_model,
    approve_builder_source_scope,
)
from core.engine.core.intelligence_builder_observation_admission import (
    ObservationAdmissionBoundError,
    ObservationAdmissionClosureError,
    ObservationAdmissionDenied,
    ObservationAdmissionStaleInput,
    admit_local_source_observations,
)
from core.engine.core.local_owner_authority import LOCAL_OWNER_ACTOR_REF, LOCAL_OWNER_PRODUCT_ID
from core.engine.core.local_source_connect import LocalSourceConnectRecordRepository
from core.engine.core.local_source_connect_progression import (
    LocalSourceConnectScopeProgressionRuntime,
    connect_local_source_connect_scope,
    propose_local_source_connect_scope,
)

pytestmark = pytest.mark.unit

_AUTHORIZED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


class _NoGrantAuthority:
    async def resolve_approval(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("unexpected direct approval resolution on the grant delegate")

    async def resolve_grant(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("observation admission never resolves a grant")


def _owner(**overrides) -> dict:
    values = {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": ["intelligence_build", "observe_read"],
        "local_owner": True,
    }
    values.update(overrides)
    return values


def _pack(name: str = "pi13-ws3-observation-admission") -> CompiledPackRefV1:
    digest = canonical_hash({"pack": name})
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
        authorized_root="/nonexistent/pi13-ws3/host-observation-admission-root",
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


def _acquired_markdown_file(relative_path: str, payload: object, **overrides) -> AcquiredLocalFile:
    payload_json = canonical_json(payload)
    values = dict(
        relative_path=relative_path,
        extension="md",
        byte_digest=f"sha256:{canonical_hash({'bytes': relative_path})}",
        size_bytes=len(payload_json),
        status="acquired",
        structured_payload_json=payload_json,
    )
    values.update(overrides)
    return AcquiredLocalFile(**values)


_ALPHA_PAYLOAD = {
    "status": "ready",
    "value": 42,
    "notes": ["- Reviewed the exact recorded source material.", "- Confirmed status against captured evidence."],
}
_BETA_PAYLOAD = {
    "status": "pending",
    "value": 7,
    "notes": ["- Needs one more pass before it is considered ready."],
}


async def _build_result(request, files):
    return await authorize_local_source_connect(request, SpyProvider(files=files))


def _raise_if_touched(*args, **kwargs):
    raise AssertionError("observation admission must never touch the filesystem")


@contextmanager
def _forbidden_filesystem():
    with (
        unittest.mock.patch("os.path.exists", _raise_if_touched),
        unittest.mock.patch("os.stat", _raise_if_touched),
        unittest.mock.patch("os.scandir", _raise_if_touched),
        unittest.mock.patch("builtins.open", _raise_if_touched),
    ):
        yield


def _runtime(store) -> LocalSourceConnectScopeProgressionRuntime:
    return LocalSourceConnectScopeProgressionRuntime(
        records=store,
        repository=LocalSourceConnectRecordRepository(store),
        grants=_NoGrantAuthority(),
    )


async def _concept_model_approved_chain(
    *,
    correlation_id: str = "correlation:ws3-observation-admission",
    mapping_id: str = "mapping-a",
    alpha_payload: dict = _ALPHA_PAYLOAD,
    beta_payload: dict = _BETA_PAYLOAD,
):
    """Build one real durable sequence through CONCEPT_MODEL_APPROVED.

    Source proposal + separate approval + connect + concept proposal +
    separate concept approval, entirely through the existing production host
    bridges (never a direct strategy/authority call, never a filesystem read).
    """

    request = _authorization_request(mapping_scopes=(_scope(mapping_id=mapping_id),))
    result = await _build_result(
        request,
        (
            _acquired_markdown_file("notes/alpha.md", alpha_payload),
            _acquired_markdown_file("notes/beta.md", beta_payload),
        ),
    )
    store = InMemoryImmutableRecordStore()
    repository = LocalSourceConnectRecordRepository(store)
    await repository.persist(request, result, _AUTHORIZED_AT)

    sessions = IntelligenceBuilderSessionService(store=store)
    started = await sessions.start(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        correlation_id=correlation_id,
        goal_ref="goal:bounded-orientation",
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=_AUTHORIZED_AT,
    )
    runtime = _runtime(store)

    scope = await propose_local_source_connect_scope(
        request=request,
        result=result,
        session=started.revision,
        user=_owner(),
        runtime=runtime,
        occurred_at=_AUTHORIZED_AT,
    )
    approved_at = _AUTHORIZED_AT + timedelta(seconds=1)
    scope_approval = await approve_builder_source_scope(
        request=BuilderSourceScopeApproveRequestV1Alpha1(
            decision="approve", current=scope.session.revision, proposal=scope.proposal, approved_at=approved_at
        ),
        user=_owner(),
        records=store,
    )
    connect_at = approved_at + timedelta(seconds=1)
    connected = await connect_local_source_connect_scope(
        request=request,
        result=result,
        session=scope.session.revision,
        proposal=scope.proposal,
        approval_receipt_ref=scope_approval.approval.receipt_ref,
        user=_owner(),
        runtime=runtime,
        occurred_at=connect_at,
    )
    assert connected.connected is True

    resolver = RecordedIntelligenceBuilderDispositionAuthority(records=store, grants=_NoGrantAuthority())
    ontology_agent = OntologyAgent(sessions=sessions, authority=resolver, strategy=FixtureConceptModelStrategy())
    mapped_at = connect_at + timedelta(seconds=1)
    proposed = await ontology_agent.propose(
        connected.session.revision,
        source_profile=connected.profile,
        user_intent="Understand the status and value of approved source-grounded records.",
        organization_terminology=(
            OrganizationTerminologyV1(
                term_id="record",
                preferred_term="Record",
                definition="A bounded source-grounded item.",
                synonyms=("item",),
            ),
        ),
        actor_ref="agent:ontology",
        occurred_at=mapped_at,
    )
    assert proposed.proposed is True and proposed.proposal is not None
    concept_current = proposed.proposal.session.revision
    concept_proposal = proposed.proposal.proposal
    concept_approved_at = mapped_at + timedelta(seconds=1)
    concept_approval = await approve_builder_concept_model(
        request=BuilderConceptModelApproveRequestV1Alpha1(
            decision="approve", current=concept_current, proposal=concept_proposal, approved_at=concept_approved_at
        ),
        user=_owner(),
        records=store,
    )
    concept_approved = await ontology_agent.approve(
        concept_current,
        proposal=concept_proposal,
        approval_receipt_ref=concept_approval.approval.receipt_ref,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        occurred_at=concept_approved_at,
    )
    assert concept_approved.session.revision.stage is OnboardingStage.CONCEPT_MODEL_APPROVED

    return {
        "request": request,
        "result": result,
        "store": store,
        "sessions": sessions,
        "repository": repository,
        "session": concept_approved.session.revision,
        "source_profile": connected.profile,
        "concept_model": concept_proposal,
        "concept_disposition": concept_approved.disposition,
        "connect_at": connect_at,
    }


async def _admit(chain: dict, *, admitted_at: datetime, **overrides):
    kwargs = dict(
        request=chain["request"],
        result=chain["result"],
        session=chain["session"],
        source_profile=chain["source_profile"],
        concept_model=chain["concept_model"],
        concept_disposition=chain["concept_disposition"],
        user=_owner(),
        admitted_at=admitted_at,
        repository=chain["repository"],
        sessions=chain["sessions"],
    )
    kwargs.update(overrides)
    return await admit_local_source_observations(**kwargs)


async def test_admits_real_markdown_leaves_with_exact_attribution_and_no_io():
    chain = await _concept_model_approved_chain()
    admitted_at = chain["connect_at"] + timedelta(seconds=5)

    with _forbidden_filesystem():
        admission = await _admit(chain, admitted_at=admitted_at)

    observation_set = admission.observation_set
    assert observation_set.session_id == chain["session"].session_id
    assert observation_set.source_profile_proposal_id == str(chain["source_profile"].proposal_id)
    assert observation_set.closure_complete is True
    assert len(observation_set.observations) == 2

    samples_by_ref = {sample.source_ref: sample for sample in chain["source_profile"].samples}
    captures_by_uri = {capture.source_uri: capture for capture in chain["result"].captures}
    for observation in observation_set.observations:
        sample = samples_by_ref[observation.source_ref]
        capture = captures_by_uri[observation.source_ref]
        assert observation.source_sample_id == str(sample.sample_id)
        assert observation.source_sample_digest == str(sample.sample_digest)
        assert observation.evidence_digest == sample.evidence_digest == capture.byte_digest
        assert observation.subject_ref == capture.selection.entity_ref
        assert observation.entity_type_id == "record"
        attributes = json.loads(observation.attributes.value_json)
        assert attributes["notes/0"].startswith("- ")
        assert attributes["status"] in {"ready", "pending"}


async def test_restart_replays_the_exact_same_observation_artifact():
    chain = await _concept_model_approved_chain()
    admitted_at = chain["connect_at"] + timedelta(seconds=5)

    first = await _admit(chain, admitted_at=admitted_at)
    second = await _admit(chain, admitted_at=admitted_at)

    assert first.observation_set == second.observation_set
    assert first.observation_set.observation_set_id == second.observation_set.observation_set_id


async def test_changed_admitted_at_on_the_same_approved_session_fails_closed_not_a_second_set():
    chain = await _concept_model_approved_chain()
    admitted_at = chain["connect_at"] + timedelta(seconds=5)
    await _admit(chain, admitted_at=admitted_at)

    with pytest.raises(ObservationAdmissionClosureError):
        await _admit(chain, admitted_at=admitted_at + timedelta(seconds=1))


async def test_fails_closed_on_crossed_owner():
    chain = await _concept_model_approved_chain()
    admitted_at = chain["connect_at"] + timedelta(seconds=5)

    with pytest.raises(ObservationAdmissionDenied):
        await _admit(chain, admitted_at=admitted_at, user=_owner(sub="user:someone-else"))


async def test_fails_closed_on_crossed_result():
    chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-crossed-result", mapping_id="mapping-b"
    )
    other = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-other-result", mapping_id="mapping-c"
    )
    admitted_at = chain["connect_at"] + timedelta(seconds=5)

    with pytest.raises(ObservationAdmissionStaleInput):
        await _admit(chain, admitted_at=admitted_at, result=other["result"])


async def test_fails_closed_on_crossed_source_profile():
    chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-crossed-profile", mapping_id="mapping-d"
    )
    other = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-other-profile", mapping_id="mapping-e"
    )
    admitted_at = chain["connect_at"] + timedelta(seconds=5)

    with pytest.raises(ObservationAdmissionStaleInput):
        await _admit(chain, admitted_at=admitted_at, source_profile=other["source_profile"])


async def test_fails_closed_on_crossed_concept_model_and_disposition():
    chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-crossed-concept", mapping_id="mapping-f"
    )
    other = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-other-concept", mapping_id="mapping-g"
    )
    admitted_at = chain["connect_at"] + timedelta(seconds=5)

    with pytest.raises(ObservationAdmissionStaleInput):
        await _admit(
            chain,
            admitted_at=admitted_at,
            concept_model=other["concept_model"],
            concept_disposition=other["concept_disposition"],
        )


async def test_fails_closed_on_crossed_session():
    chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-crossed-session", mapping_id="mapping-h"
    )
    other = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-other-session", mapping_id="mapping-i"
    )
    admitted_at = chain["connect_at"] + timedelta(seconds=5)

    with pytest.raises(ObservationAdmissionStaleInput):
        await _admit(chain, admitted_at=admitted_at, session=other["session"])


async def test_retry_with_an_earlier_still_valid_admitted_at_fails_closed_not_a_second_set():
    chain = await _concept_model_approved_chain()
    later_admitted_at = chain["connect_at"] + timedelta(seconds=10)
    earlier_admitted_at = chain["connect_at"] + timedelta(seconds=5)
    assert earlier_admitted_at < later_admitted_at

    first = await _admit(chain, admitted_at=later_admitted_at)

    with pytest.raises(ObservationAdmissionClosureError):
        await _admit(chain, admitted_at=earlier_admitted_at)

    store: InMemoryImmutableRecordStore = chain["store"]
    records = await store.read_as_of(
        product_id=chain["session"].product_id,
        record_space="ace.application.intelligence-builder",
        record_kind="onboarding_artifact",
        available_at=datetime.max.replace(tzinfo=UTC),
    )
    observation_set_records = [
        record
        for record in records
        if record.payload_contract == "ace.application.authorized-observation-set/v1alpha1"
        and record.payload.get("session_id") == chain["session"].session_id
    ]
    assert len(observation_set_records) == 1
    assert observation_set_records[0].record_key == first.observation_set.observation_set_id


async def test_fails_closed_when_admitted_at_precedes_a_recorded_capture_observed_at():
    chain = await _concept_model_approved_chain()
    stale_admitted_at = chain["connect_at"] - timedelta(seconds=1)

    with pytest.raises(ObservationAdmissionStaleInput):
        await _admit(chain, admitted_at=stale_admitted_at)


async def test_fails_closed_on_the_32kb_flattened_attribute_bound():
    oversized_note = "x" * (MAX_CANONICAL_VALUE_CHARS + 1000)
    chain = await _concept_model_approved_chain(
        correlation_id="correlation:ws3-observation-admission-oversized",
        mapping_id="mapping-j",
        alpha_payload={**_ALPHA_PAYLOAD, "notes": [oversized_note]},
    )
    admitted_at = chain["connect_at"] + timedelta(seconds=5)

    with pytest.raises(ObservationAdmissionBoundError):
        await _admit(chain, admitted_at=admitted_at)

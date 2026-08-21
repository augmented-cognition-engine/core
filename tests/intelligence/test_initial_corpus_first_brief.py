"""Initial-corpus first Brief: domain-neutral orientation over the admitted corpus.

Covers the corrected PI13 WS3b slice: the orientation pack module contract and
its compiler/runtime resolution, the initial-corpus synthesis service, and the
build-bound application path. The routed Shift/Signal ``create_first_brief``
path is untouched and keeps its own suite.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import timedelta

import pytest

from ace.application import (
    CoreIntelligenceBuildFirstBriefService,
    DomainActivationAdmissionService,
    InitialCorpusBriefSynthesisError,
    InitialCorpusBriefSynthesisService,
    IntelligenceBuildFirstBriefCognition,
    IntelligenceBuildFirstBriefError,
    IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1,
    PreparedIntelligenceLedgerService,
    bind_committed_activation,
)
from ace.application.initial_corpus_brief_synthesis import _corpus_transaction_key
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    GovernedOperationBindingV1Alpha1,
    GovernedReasoningService,
    GovernedStateHeadV1,
    ProviderRouteV1Alpha1,
    ProviderStructuredOutputV1Alpha1,
    ProviderUsageV1Alpha1,
    ReasoningExecutionBindingV1Alpha1,
    canonical_json,
    capability_state_ref_for_artifact,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence import (
    ActivationState,
    BriefDraftClaimV1Alpha1,
    BriefDraftSectionV1Alpha1,
    BriefSynthesisDraftV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    ClaimGroundingKind,
    EntitySnapshotV1Alpha1,
    EvidenceAcquisitionMode,
    InitialCorpusBriefSynthesisRequestV1Alpha1,
    IntelligenceRecordKind,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    ObservationV1Alpha1,
    OrganizationOverlayV1,
    PreparedResourceSetAdmissionV1Alpha1,
    deterministic_resource_order,
    resource_reference,
)
from ace.intelligence.packs.activation import (
    compile_overlay,
    prepare_activation_revision,
    prepare_domain_activation,
)
from ace.intelligence.packs.compiler import PackCompilationError, compile_pack_document
from ace.intelligence.packs.runtime import (
    PreparedActivationBindingError,
    bind_prepared_activation,
    resolve_initial_orientation_policy,
)
from ace.testing import InMemoryImmutableRecordStore
from tests.intelligence.test_brief_synthesis import (
    ACTIVATED_AT,
    APPEND_ARTIFACT,
    ARTIFACT,
    BASELINE_AS_OF,
    GENERATED_AT,
    PRODUCT,
    REQUESTED_AT,
    _ActivationAuthority,
    _ActivationStore,
    _Clock,
    _encoded,
    _head,
    _PackArchive,
    _Runtime,
)
from tests.intelligence.test_intelligence_build_first_brief import _active_session
from tests.intelligence.test_prepared_shift_signal import _build, _CurrentBuildAuthority

pytestmark = pytest.mark.unit

CORPUS_AS_OF = BASELINE_AS_OF
CORPUS_AVAILABLE_AT = CORPUS_AS_OF + timedelta(seconds=90)
POLICY_ID = "initial_orientation"
TEMPLATE_ID = "initial_orientation_brief"
PERSONA_ID = "orientation_analyst"


def _orientation_modules(
    *,
    template_id: str = TEMPLATE_ID,
    policy_template_id: str = TEMPLATE_ID,
    policy_persona_ids: tuple[str, ...] = (PERSONA_ID,),
) -> dict:
    return {
        "ontology": {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "product",
                    "attributes": [
                        {"attribute_id": "name", "value_type": "string", "required": True},
                        {"attribute_id": "price", "value_type": "number", "required": True},
                    ],
                }
            ],
            "relation_types": [],
        },
        "synthesis": {
            "contract": "ace.intelligence.synthesis/v1alpha2",
            "module_id": "synthesis",
            "brief_templates": [
                {
                    "template_id": template_id,
                    "brief_type": "orientation_brief",
                    "display_name": "Initial Orientation Brief",
                    "objective": "Orient over the exact admitted corpus at one as_of; cite or mark inference.",
                    "required_sections": ["orientation"],
                    "recommendation_required": False,
                }
            ],
        },
        "orientation": {
            "contract": "ace.intelligence.orientation/v1alpha1",
            "module_id": "orientation",
            "personas": [
                {
                    "persona_id": PERSONA_ID,
                    "display_name": "Orientation Analyst",
                    "description": "Orients over the exact admitted corpus without inventing change events.",
                }
            ],
            "initial_orientation_policies": [
                {
                    "policy_id": POLICY_ID,
                    "brief_template_id": policy_template_id,
                    "persona_ids": list(policy_persona_ids),
                }
            ],
        },
    }


def _orientation_pack(modules: dict | None = None, *, extra_orientation: dict | None = None):
    modules = dict(modules or _orientation_modules())
    if extra_orientation is not None:
        modules["orientation_two"] = extra_orientation
    resources = {f"modules/{module_id}.json": _encoded(payload) for module_id, payload in modules.items()}
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {
            "pack_id": "orientation_fixture",
            "version": "0.1.0",
            "display_name": "Orientation Fixture",
        },
        "resources": [
            {
                "resource_id": module_id,
                "path": f"modules/{module_id}.json",
                "digest": f"sha256:{hashlib.sha256(resources[f'modules/{module_id}.json']).hexdigest()}",
            }
            for module_id in modules
        ],
        "modules": [
            {
                "module_id": module_id,
                "contract": payload["contract"],
                "resource_id": module_id,
                "depends_on": [],
            }
            for module_id, payload in modules.items()
        ],
        "capability_requirements": [],
        "authority_requests": [],
        "overlay_slots": [],
    }
    return compile_pack_document(_encoded(manifest), resources)


def _lineage(resource) -> LineageReferenceV1Alpha1:
    reference = resource_reference(resource)
    return LineageReferenceV1Alpha1(
        resource_kind=LineageResourceKind.OBSERVATION,
        relation=LineageRelation.DERIVED_FROM,
        resource_id=reference.resource_id,
        resource_digest=reference.resource_digest,
        resource_as_of=reference.as_of,
        resource_available_at=reference.available_at,
    )


def _observation(reference, *, suffix: str, as_of) -> ObservationV1Alpha1:
    return ObservationV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=as_of,
        source_ref=f"source:notes-{suffix}",
        source_digest="sha256:" + "1" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref=f"acquisition:notes-{suffix}",
        acquisition_receipt_digest="sha256:" + "2" * 64,
        source_published_at=as_of,
        observed_at=as_of,
        ingested_at=as_of,
        subject_refs=("entity:doc-one",),
        payload=CanonicalJsonValueV1Alpha1(
            value_json=canonical_json({"name": f"Doc {suffix}", "price": {"amount": 10, "currency": "USD"}})
        ),
        confidence=0.9,
    )


def _snapshot(reference, observations, *, suffix: str, as_of, projected_at) -> EntitySnapshotV1Alpha1:
    return EntitySnapshotV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=as_of,
        lineage=tuple(_lineage(item) for item in observations),
        entity_ref=f"entity:doc-{suffix}",
        entity_type_ref="product",
        attributes=CanonicalJsonValueV1Alpha1(value_json=canonical_json({"name": f"Doc {suffix}", "price": 10.0})),
        projected_at=projected_at,
        confidence=0.9,
    )


class _OrientationProvider:
    artifact_identity = ARTIFACT

    def __init__(self, *, omit_support: bool = False) -> None:
        self.calls = 0
        self.omit_support = omit_support

    async def execute(self, request):
        self.calls += 1
        observations = tuple(item.record_key for item in request.context_items if item.record_kind == "observation")
        snapshots = tuple(item.record_key for item in request.context_items if item.record_kind == "entity_snapshot")
        cited = BriefDraftClaimV1Alpha1(
            statement="The corpus currently describes the tracked documents.",
            grounding_kind=ClaimGroundingKind.CITED,
            support_refs=observations[:-1] if self.omit_support else observations,
            confidence=0.9,
        )
        inference = BriefDraftClaimV1Alpha1(
            statement="What currently matters is keeping these documents in view.",
            grounding_kind=ClaimGroundingKind.INFERENCE,
            support_refs=snapshots,
            confidence=0.7,
            uncertainty="A single initial corpus cannot establish trends or priorities.",
        )
        draft = BriefSynthesisDraftV1Alpha1(
            brief_type="orientation_brief",
            persona_ids=(PERSONA_ID,),
            sections=(BriefDraftSectionV1Alpha1(section_id="orientation", claims=(cited, inference)),),
            recommendation_claim_id=None,
        )
        return ProviderStructuredOutputV1Alpha1(
            route=ProviderRouteV1Alpha1(
                provider_id="fixture",
                model_id="deterministic",
                model_version="1",
                configuration_digest="sha256:" + "c" * 64,
            ),
            usage=ProviderUsageV1Alpha1(input_units=100, output_units=30, total_units=130, duration_ms=2),
            structured_json=canonical_json(draft.model_dump(mode="json")),
            referenced_context_ids=tuple(str(item.context_id) for item in request.context_items),
        )


@dataclass(frozen=True, slots=True)
class _OrientationEnvironment:
    service: InitialCorpusBriefSynthesisService
    activation_service: DomainActivationAdmissionService
    pack: object
    store: InMemoryImmutableRecordStore
    provider: _OrientationProvider
    execution_binding: ReasoningExecutionBindingV1Alpha1
    append_binding: object
    request: InitialCorpusBriefSynthesisRequestV1Alpha1
    binding: object


async def _orientation_environment(
    *,
    provider: _OrientationProvider | None = None,
    admit_corpus: bool = True,
    synthesis_store=None,
) -> _OrientationEnvironment:
    pack = _orientation_pack()
    activation_store = _ActivationStore()
    activation_service = DomainActivationAdmissionService(
        store=activation_store,
        authority=_ActivationAuthority(),
    )
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="orientation_fixture",
            version="0.1.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
        ),
    )
    spec = prepare_domain_activation(
        product_id=PRODUCT,
        activation_key=pack.metadata.pack_id,
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref="receipt:orientation-compilation",
        conformance_receipt_refs=("receipt:orientation-conformance",),
    )
    revision = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:orientation-owner",
        approval_receipt_ref="receipt:orientation-approval",
        occurred_at=ACTIVATED_AT,
    )
    committed = await activation_service.admit(
        revision,
        expected_head_revision_id=None,
        committed_at=ACTIVATED_AT + timedelta(seconds=1),
    )
    binding = bind_committed_activation(pack=pack, committed=committed)
    store = InMemoryImmutableRecordStore()
    reference = binding.prepared_binding.reference
    if admit_corpus:
        first = _observation(reference, suffix="one", as_of=CORPUS_AS_OF)
        second = _observation(reference, suffix="two", as_of=CORPUS_AS_OF)
        snapshot = _snapshot(
            reference,
            (first, second),
            suffix="one",
            as_of=CORPUS_AS_OF,
            projected_at=CORPUS_AVAILABLE_AT,
        )
        resources = (first, second, snapshot)
        await PreparedIntelligenceLedgerService(binding=binding, store=store).admit_resource_set(
            PreparedResourceSetAdmissionV1Alpha1(
                admission_key="resource_set:initial-corpus",
                product_id=PRODUCT,
                activation_revision=reference,
                pack=binding.prepared_binding.revision.spec.pack,
                resources=resources,
                processing_order=deterministic_resource_order(resources),
                admitted_at=CORPUS_AVAILABLE_AT,
            )
        )
    execution_head = _head("reasoning_configuration", "reasoning_configuration:orientation")
    execution_binding = ReasoningExecutionBindingV1Alpha1(
        product_id=PRODUCT,
        artifact=ARTIFACT,
        configuration_ref="reasoning_configuration:orientation",
        authority="reason",
        grant_ref="authority_grant:orientation",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(execution_head),
    )
    append_head = _head(
        "governed_operation_configuration",
        "governed_operation_configuration:orientation-append",
    )
    append_binding = GovernedOperationBindingV1Alpha1(
        product_id=PRODUCT,
        artifact=APPEND_ARTIFACT,
        configuration_ref="governed_operation_configuration:orientation-append",
        authority="append_immutable_records",
        grant_ref="authority_grant:orientation-append",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(append_head),
    )
    activation_head = activation_store.heads[
        (
            committed.commit_receipt.state_kind,
            committed.commit_receipt.product_id,
            committed.commit_receipt.state_id,
        )
    ]
    for head in (
        execution_head,
        append_head,
        _head("capability_state", capability_state_ref_for_artifact(ARTIFACT)),
        _head("authority_grant", execution_binding.grant_ref),
        _head("capability_state", capability_state_ref_for_artifact(APPEND_ARTIFACT)),
        _head("authority_grant", append_binding.grant_ref),
        activation_head,
    ):
        store.set_governed_state_head(head)
    runtime = _Runtime(execution_binding=execution_binding, append_binding=append_binding)
    runtime.store = store
    actual_provider = provider or _OrientationProvider()
    reasoning = GovernedReasoningService(
        store=store,
        runtime_use=runtime,
        provider=actual_provider,
        clock=_Clock(
            REQUESTED_AT,
            REQUESTED_AT + timedelta(seconds=5),
            REQUESTED_AT + timedelta(seconds=10),
            GENERATED_AT,
            GENERATED_AT,
        ),
    )
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref="principal:orientation-owner",
        authentication_receipt_ref="authentication:orientation",
        authentication_receipt_digest="sha256:" + "e" * 64,
        authenticated_at=CORPUS_AS_OF - timedelta(minutes=1),
        expires_at=REQUESTED_AT + timedelta(minutes=5),
    )
    request = InitialCorpusBriefSynthesisRequestV1Alpha1(
        synthesis_key="orientation-synthesis-key",
        reasoning_attempt_key="orientation-reasoning-key",
        product_id=PRODUCT,
        authenticated_context=context,
        activation_revision=reference,
        pack=binding.prepared_binding.revision.spec.pack,
        orientation_policy_id=POLICY_ID,
        corpus_as_of=CORPUS_AS_OF,
        corpus_available_at=CORPUS_AVAILABLE_AT,
        requested_at=REQUESTED_AT,
    )
    service = InitialCorpusBriefSynthesisService(
        activation_service=activation_service,
        pack=pack,
        store=synthesis_store if synthesis_store is not None else store,
        reasoning=reasoning,
        execution_binding=execution_binding,
        append_binding=append_binding,
        clock=_Clock(GENERATED_AT),
    )
    return _OrientationEnvironment(
        service=service,
        activation_service=activation_service,
        pack=pack,
        store=store,
        provider=actual_provider,
        execution_binding=execution_binding,
        append_binding=append_binding,
        request=request,
        binding=binding,
    )


# -- generic orientation pack contract ----------------------------------------


def test_orientation_module_compiles_and_resolves_the_exact_policy():
    pack = _orientation_pack()
    revision = prepare_activation_revision(
        spec=prepare_domain_activation(
            product_id=PRODUCT,
            activation_key=pack.metadata.pack_id,
            pack=pack,
            overlay=compile_overlay(
                pack,
                OrganizationOverlayV1(
                    overlay_id="orientation_fixture",
                    version="0.1.0",
                    pack_id=pack.metadata.pack_id,
                    pack_version=pack.metadata.version,
                    pack_digest=pack.pack_digest,
                ),
            ),
            compilation_receipt_ref="receipt:orientation-compilation",
            conformance_receipt_refs=("receipt:orientation-conformance",),
        ),
        state=ActivationState.ACTIVE,
        actor_ref="principal:orientation-owner",
        approval_receipt_ref="receipt:orientation-approval",
        occurred_at=ACTIVATED_AT,
    )
    binding = bind_prepared_activation(pack=pack, revision=revision)

    resolved = resolve_initial_orientation_policy(binding, policy_id=POLICY_ID)

    assert resolved.policy.policy_id == POLICY_ID
    assert resolved.policy.brief_template_id == TEMPLATE_ID
    assert resolved.synthesis.template.template_id == TEMPLATE_ID
    assert tuple(item.persona_id for item in resolved.synthesis.personas) == (PERSONA_ID,)
    assert resolved.policy_digest.startswith("sha256:")
    with pytest.raises(PreparedActivationBindingError, match="must resolve exactly once"):
        resolve_initial_orientation_policy(binding, policy_id="missing_policy")


def test_orientation_policy_template_and_persona_mismatches_fail_compilation():
    with pytest.raises(PackCompilationError, match="unresolved_orientation_template"):
        _orientation_pack(_orientation_modules(policy_template_id="missing_template"))
    with pytest.raises(PackCompilationError, match="unresolved_orientation_personas"):
        _orientation_pack(_orientation_modules(policy_persona_ids=("missing_persona",)))
    duplicate = {
        "contract": "ace.intelligence.orientation/v1alpha1",
        "module_id": "orientation_two",
        "personas": [],
        "initial_orientation_policies": [
            {
                "policy_id": POLICY_ID,
                "brief_template_id": TEMPLATE_ID,
                "persona_ids": [PERSONA_ID],
            }
        ],
    }
    with pytest.raises(PackCompilationError, match="duplicate_orientation_policy_id"):
        _orientation_pack(extra_orientation=duplicate)


# -- initial-corpus synthesis service -----------------------------------------


@pytest.mark.asyncio
async def test_initial_corpus_brief_orients_without_shift_signal_and_replays_once():
    env = await _orientation_environment()

    first = await env.service.synthesize(env.request)
    replay = await env.service.synthesize(env.request)

    assert replay == replace(first, replayed=True)
    assert env.provider.calls == 1
    assert first.brief.as_of == CORPUS_AS_OF
    assert first.brief.citations
    assert {item.resource_kind for item in first.brief.lineage} <= {
        LineageResourceKind.OBSERVATION,
        LineageResourceKind.ENTITY_SNAPSHOT,
    }
    receipt = first.synthesis_receipt
    assert receipt.orientation_policy_id == POLICY_ID
    assert receipt.template_id == TEMPLATE_ID
    assert receipt.persona_ids == (PERSONA_ID,)
    assert receipt.corpus_as_of == CORPUS_AS_OF
    assert receipt.corpus_available_at == CORPUS_AVAILABLE_AT
    assert len(receipt.corpus_observation_ids) == 2
    assert len(receipt.corpus_entity_snapshot_ids) == 1
    ledger = PreparedIntelligenceLedgerService(binding=env.binding, store=env.store)
    assert (
        await ledger.read_as_of(
            product_id=PRODUCT,
            mode=IntelligenceResourceMode.PREPARED,
            kind=IntelligenceRecordKind.SIGNAL,
            available_at=GENERATED_AT,
        )
        == ()
    )
    assert (
        await ledger.read_as_of(
            product_id=PRODUCT,
            mode=IntelligenceResourceMode.PREPARED,
            kind=IntelligenceRecordKind.SHIFT,
            available_at=GENERATED_AT,
        )
        == ()
    )


@pytest.mark.asyncio
async def test_empty_corpus_fails_closed_before_any_provider_call():
    env = await _orientation_environment(admit_corpus=False)

    with pytest.raises(InitialCorpusBriefSynthesisError, match="corpus is empty"):
        await env.service.synthesize(env.request)

    assert env.provider.calls == 0


@pytest.mark.asyncio
async def test_material_outside_the_exact_corpus_as_of_is_future_leakage():
    env = await _orientation_environment()
    reference = env.binding.prepared_binding.reference
    later_as_of = CORPUS_AS_OF + timedelta(minutes=2)
    later_available = later_as_of + timedelta(seconds=30)
    late_observation = _observation(reference, suffix="late", as_of=later_as_of)
    late_snapshot = _snapshot(
        reference,
        (late_observation,),
        suffix="late",
        as_of=later_as_of,
        projected_at=later_available,
    )
    resources = (late_observation, late_snapshot)
    await PreparedIntelligenceLedgerService(binding=env.binding, store=env.store).admit_resource_set(
        PreparedResourceSetAdmissionV1Alpha1(
            admission_key="resource_set:late-corpus",
            product_id=PRODUCT,
            activation_revision=reference,
            pack=env.binding.prepared_binding.revision.spec.pack,
            resources=resources,
            processing_order=deterministic_resource_order(resources),
            admitted_at=later_available,
        )
    )
    material = env.request.model_dump(mode="python", exclude={"request_id", "request_digest"})
    leaking = InitialCorpusBriefSynthesisRequestV1Alpha1(**{**material, "corpus_available_at": later_available})

    with pytest.raises(InitialCorpusBriefSynthesisError, match="one exact as_of"):
        await env.service.synthesize(leaking)

    assert env.provider.calls == 0


class _HidingStore:
    """Delegate to the real store while hiding one exact record key."""

    def __init__(self, inner, *, hidden_record_key: str) -> None:
        self._inner = inner
        self._hidden = hidden_record_key

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def read_as_of(self, **kwargs):
        records = await self._inner.read_as_of(**kwargs)
        return tuple(item for item in records if item.record_key != self._hidden)

    async def load_record(self, storage_id, **kwargs):
        record = await self._inner.load_record(storage_id, **kwargs)
        if record is not None and record.record_key == self._hidden:
            return None
        return record


@pytest.mark.asyncio
async def test_missing_source_observation_locator_fails_closed():
    probe = await _orientation_environment()
    reference = probe.binding.prepared_binding.reference
    hidden = str(resource_reference(_observation(reference, suffix="one", as_of=CORPUS_AS_OF)).resource_id)
    env = await _orientation_environment(
        synthesis_store=_HidingStore(probe.store, hidden_record_key=hidden),
    )
    # Activation identity is content-derived, so both environments bind the
    # same durable material and the hidden key names the probe's Observation.
    assert env.request.activation_revision == probe.request.activation_revision

    with pytest.raises(InitialCorpusBriefSynthesisError, match="missing source Observation locator"):
        await env.service.synthesize(env.request)

    assert env.provider.calls == 0


@pytest.mark.asyncio
async def test_unused_selected_support_is_rejected_and_nothing_is_appended():
    env = await _orientation_environment(provider=_OrientationProvider(omit_support=True))

    with pytest.raises(InitialCorpusBriefSynthesisError):
        await env.service.synthesize(env.request)

    assert env.provider.calls == 1
    assert (
        await env.store.load_transaction_receipt(
            product_id=PRODUCT,
            record_space="prepared",
            transaction_key=_corpus_transaction_key(env.request.synthesis_key),
        )
        is None
    )
    ledger = PreparedIntelligenceLedgerService(binding=env.binding, store=env.store)
    assert (
        await ledger.read_as_of(
            product_id=PRODUCT,
            mode=IntelligenceResourceMode.PREPARED,
            kind=IntelligenceRecordKind.BRIEF,
            available_at=GENERATED_AT + timedelta(minutes=5),
        )
        == ()
    )


@pytest.mark.asyncio
async def test_crossed_activation_scope_fails_before_provider_use():
    env = await _orientation_environment()
    material = env.request.model_dump(mode="python", exclude={"request_id", "request_digest"})
    crossed = InitialCorpusBriefSynthesisRequestV1Alpha1(
        **{
            **material,
            "activation_revision": env.request.activation_revision.model_copy(
                update={
                    "revision_digest": "sha256:" + "9" * 64,
                    "revision_id": "activation_revision:" + "9" * 32,
                }
            ),
        }
    )

    with pytest.raises(InitialCorpusBriefSynthesisError, match="does not bind the current committed activation"):
        await env.service.synthesize(crossed)

    assert env.provider.calls == 0


# -- build-bound application path ---------------------------------------------


async def _corpus_stack(*, cognition: bool = True):
    env = await _orientation_environment()
    binding = env.binding
    sessions, session = await _active_session(env, binding)
    grant = GovernedStateHeadV1(
        state_kind="authority_grant",
        product_id=PRODUCT,
        state_id="authority_grant:atrium-intelligence-build",
        sequence=1,
        revision_id="authority_grant_revision:initial-corpus",
        commit_receipt_id="governed_state_commit:initial-corpus",
        updated_at=ACTIVATED_AT,
    )
    env.store.set_governed_state_head(grant)
    build = _build(binding, grant, evaluated_at=REQUESTED_AT)
    actor = binding.commit_receipt.actor_ref
    original_context = build.authority_use.authenticated_context
    context = AuthenticatedRuntimeContextV1Alpha1(
        **original_context.model_dump(mode="python", exclude={"actor_ref"}),
        actor_ref=actor,
    )
    authority_use = AuthorityUseReceiptV1Alpha1(
        **build.authority_use.model_dump(
            mode="python",
            exclude={"actor_ref", "authenticated_context", "receipt_id", "receipt_digest"},
        ),
        actor_ref=actor,
        authenticated_context=context,
    )
    build = replace(build, actor_ref=actor, authority_use=authority_use)
    request = IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1(
        build_id=build.build_id,
        build_request_digest=build.request_digest,
        orientation_policy_id=POLICY_ID,
        corpus_as_of=CORPUS_AS_OF,
        corpus_available_at=CORPUS_AVAILABLE_AT,
        requested_at=REQUESTED_AT,
    )
    composition = (
        IntelligenceBuildFirstBriefCognition(
            reasoning=env.service.reasoning,
            execution_binding=env.execution_binding,
            append_binding=env.append_binding,
        )
        if cognition
        else None
    )
    service = CoreIntelligenceBuildFirstBriefService(
        build=build,
        sessions=sessions,
        activations=env.activation_service,
        packs=_PackArchive(env.pack),
        records=env.store,
        runtime_use=_CurrentBuildAuthority(build.authority_use),
        cognition=composition,
        active_session=session,
    )
    return env, build, request, service


@pytest.mark.asyncio
async def test_build_bound_initial_corpus_first_brief_synthesizes_and_replays():
    env, _, request, service = await _corpus_stack()

    first = await service.create_initial_corpus_first_brief(request)
    replay = await service.create_initial_corpus_first_brief(request)

    assert replay == replace(first, admission=replace(first.admission, replayed=True))
    assert env.provider.calls == 1
    assert first.admission.brief.as_of == CORPUS_AS_OF
    assert first.admission.brief.citations
    assert first.admission.synthesis_receipt.orientation_policy_id == POLICY_ID
    assert first.admission.synthesis_receipt.template_id == TEMPLATE_ID
    assert first.admission.synthesis_receipt.persona_ids == (PERSONA_ID,)


@pytest.mark.asyncio
async def test_missing_cognition_composition_fails_closed_before_provider():
    env, _, request, service = await _corpus_stack(cognition=False)

    with pytest.raises(IntelligenceBuildFirstBriefError, match="composition is not installed"):
        await service.create_initial_corpus_first_brief(request)

    assert env.provider.calls == 0


@pytest.mark.asyncio
async def test_cross_build_and_unknown_policy_fail_before_provider_use():
    env, _, request, service = await _corpus_stack()
    material = request.model_dump(mode="python", exclude={"request_id", "request_digest"})

    crossed = IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1(
        **{**material, "build_request_digest": "sha256:" + "8" * 64}
    )
    with pytest.raises(IntelligenceBuildFirstBriefError, match="crossed the authorized build"):
        await service.create_initial_corpus_first_brief(crossed)

    unknown = IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1(
        **{**material, "orientation_policy_id": "missing_policy"}
    )
    with pytest.raises(IntelligenceBuildFirstBriefError, match="failed exact resolution"):
        await service.create_initial_corpus_first_brief(unknown)

    assert env.provider.calls == 0


def test_initial_corpus_request_contract_is_orientation_shaped():
    request = IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1(
        build_id="intelligence_build:initial-corpus",
        build_request_digest="sha256:" + "1" * 64,
        orientation_policy_id=POLICY_ID,
        corpus_as_of=CORPUS_AS_OF,
        corpus_available_at=CORPUS_AVAILABLE_AT,
        requested_at=REQUESTED_AT,
    )

    dumped = request.model_dump()
    assert request.contract.endswith("initial-corpus-first-brief-request/v1alpha1")
    assert "derivation_key" not in dumped
    assert "attention_receipt_id" not in dumped
    assert str(request.request_id).startswith("intelligence_build_initial_corpus_first_brief:")
    with pytest.raises(ValueError, match="cannot follow"):
        IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1(
            build_id="intelligence_build:initial-corpus",
            build_request_digest="sha256:" + "1" * 64,
            orientation_policy_id=POLICY_ID,
            corpus_as_of=CORPUS_AVAILABLE_AT,
            corpus_available_at=CORPUS_AS_OF,
            requested_at=REQUESTED_AT,
        )


def test_orientation_fixture_pack_declares_no_detection_or_routing_policy():
    pack = _orientation_pack()
    contracts = {module.contract for module in pack.modules}
    assert not any(item.startswith("ace.intelligence.detection/") for item in contracts)
    assert not any(item.startswith("ace.intelligence.personas/") for item in contracts)
    assert (
        json.loads(next(module.canonical_payload for module in pack.modules if module.module_id == "orientation"))[
            "initial_orientation_policies"
        ][0]["policy_id"]
        == POLICY_ID
    )

from __future__ import annotations

from datetime import timedelta

import pytest

from ace.application.domain_activation import DomainActivationAdmissionService
from ace.application.domain_activation_compatibility import DomainActivationCompatibilityService
from ace.application.domain_activation_plan import (
    DomainActivationPlanAdmissionService,
    prepare_activation_onboarding_handoff,
)
from ace.application.domain_activation_plan_contracts import ActivationPlanAction
from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    AuthorizedIntelligenceBuild,
    IntelligenceBuildStartV1,
    ProductScopedImmutableRecordStore,
)
from ace.application.intelligence_build_host import (
    DurableIntelligenceBuildHostComposer,
    IntelligenceBuildHostCompositionError,
)
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_activation import IntelligenceBuilderActivationService
from ace.application.recorded_source_admission import CoreRecordedSourceAdmissionService
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore
from ace.testing.watch_brief import exercise_watch_brief_restart
from tests.intelligence.test_domain_activation_plan_admission import (
    _activation_material,
    _Authority,
    _MemoryStore,
    _PackResolver,
    _plan,
    _revision,
)

pytestmark = pytest.mark.unit


class _Resources:
    async def query(self, **_kwargs):
        raise AssertionError("host composition must not query resource projections")


class _RuntimeUse:
    def __init__(self) -> None:
        self.calls = []

    async def resolve_authority_use(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("composition alone must not spend a second build authority use")


async def _activated_stack(*, records=None, governed=None):
    records = records or InMemoryImmutableRecordStore()
    watch = await exercise_watch_brief_restart(store=records)
    session = watch.briefing.session.revision
    handoff = prepare_activation_onboarding_handoff(
        session=session,
        observations=watch.observations.observation_set,
        intelligence_model=watch.approved.proposal,
        intelligence_disposition=watch.approved.disposition,
        first_briefing=watch.briefing.brief,
    )
    pack, conformance, spec = _activation_material(product_id=session.product_id)
    created = session.occurred_at + timedelta(seconds=1)
    plan = _plan(
        spec=spec,
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        created_at=created,
        handoff=handoff,
    )
    revision = _revision(plan=plan, revision=1, occurred_at=created + timedelta(seconds=2))
    authority = _Authority(approved_at=created + timedelta(seconds=1))
    governed = governed or _MemoryStore()
    plans = DomainActivationPlanAdmissionService(store=governed, authority=authority)
    committed_plan = await plans.admit(
        revision,
        pack=pack,
        conformance_receipts=(conformance,),
        committed_at=revision.occurred_at + timedelta(seconds=1),
        session=session,
        observations=watch.observations.observation_set,
        intelligence_model=watch.approved.proposal,
        intelligence_disposition=watch.approved.disposition,
        first_briefing=watch.briefing.brief,
    )
    activation = IntelligenceBuilderActivationService(
        sessions=IntelligenceBuilderSessionService(store=records),
        plans=plans,
        compatibility=DomainActivationCompatibilityService(authority=authority),
        canonical=DomainActivationAdmissionService(store=governed, authority=authority),
        packs=_PackResolver(pack),
    )
    recorded = await activation.record_current_plan(
        product_id=session.product_id,
        session_id=session.session_id,
        committed=committed_plan,
        pack=spec.pack,
        recorded_at=revision.occurred_at + timedelta(seconds=2),
    )
    active = await activation.activate(
        product_id=session.product_id,
        session_id=recorded.session.revision.session_id,
        activation_approval_receipt_ref="approval:canonical-spec",
        evaluated_at=revision.occurred_at + timedelta(seconds=3),
    )
    return records, governed, pack, authority, active


def _build(active) -> AuthorizedIntelligenceBuild:
    evaluated_at = active.receipt_artifact.activated_at + timedelta(minutes=1)
    product_id = active.binding.prepared_binding.reference.product_id
    actor_ref = active.binding.commit_receipt.actor_ref
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        authentication_receipt_ref="authentication_receipt:build-host",
        authentication_receipt_digest="sha256:" + "1" * 64,
        authenticated_at=evaluated_at - timedelta(minutes=2),
        expires_at=evaluated_at + timedelta(hours=1),
    )
    request = IntelligenceBuildStartV1(
        authority_grant_ref="authority_grant:build-host",
        resource_authority_grant_ref="authority_grant:build-host-read",
        activation_approval_receipt_ref=str(active.binding.commit_receipt.approval.receipt_ref),
        activation_approval_subject_ref=str(active.binding.prepared_binding.revision.spec.spec_id),
        client_request_id="atrium_request:build-host",
        profile_id="intelligence_onboarding_profile:build-host",
        subject="Track this exact activated subject for meaningful material changes.",
        outcome_id="decision_readiness",
        source_group_ids=(),
        recorded_source_refs=(),
        cadence_id="daily_pulse",
        approved_effects=REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
        requested_at=evaluated_at - timedelta(seconds=1),
    )
    build_id = "intelligence_build:durable-host"
    request_digest = "sha256:" + "2" * 64
    authority_use = AuthorityUseReceiptV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        authenticated_context=context,
        use_subject_ref=build_id,
        use_subject_digest=request_digest,
        operation="start_intelligence_build",
        authority="intelligence_build",
        grant_ref=request.authority_grant_ref,
        grant_hash="3" * 64,
        evaluated_at=evaluated_at,
        expires_at=evaluated_at + timedelta(hours=1),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=product_id,
            state_id=request.authority_grant_ref,
            sequence=1,
            revision_id="authority_grant_revision:build-host",
            commit_receipt_id="governed_state_commit:build-host",
        ),
    )
    return AuthorizedIntelligenceBuild(
        build_id=build_id,
        request_digest=request_digest,
        product_id=product_id,
        actor_ref=actor_ref,
        request=request,
        authority_use=authority_use,
        activation_approval=active.binding.commit_receipt.approval,
    )


@pytest.mark.asyncio
async def test_exact_durable_bootstrap_composes_fresh_product_fenced_ports() -> None:
    records, governed, pack, authority, active = await _activated_stack()
    build = _build(active)
    runtime_use = _RuntimeUse()
    composer = DurableIntelligenceBuildHostComposer(
        governed_state=governed,
        runtime_use=runtime_use,
        packs=_PackResolver(pack),
    )
    scoped = ProductScopedImmutableRecordStore(product_id=build.product_id, store=records)

    first = await composer.compose(
        build=build,
        records=scoped,
        resources=_Resources(),
        activation_authority=authority,
    )
    reopened = await DurableIntelligenceBuildHostComposer(
        governed_state=governed,
        runtime_use=runtime_use,
        packs=_PackResolver(pack),
    ).compose(
        build=build,
        records=ProductScopedImmutableRecordStore(product_id=build.product_id, store=records),
        resources=_Resources(),
        activation_authority=authority,
    )

    assert isinstance(first.recorded_sources, CoreRecordedSourceAdmissionService)
    assert first.prepared_derivations is not None
    assert first.first_brief is None
    assert first.records.product_id == build.product_id
    assert first.recorded_sources.store is first.records
    assert first.prepared_derivations.ledger.store is first.records
    assert first.prepared_derivations.runtime_use is runtime_use
    assert first.activation_authority is authority
    assert reopened.recorded_sources is not first.recorded_sources
    assert reopened.prepared_derivations is not first.prepared_derivations
    assert reopened.recorded_sources.binding == first.recorded_sources.binding == active.binding
    assert runtime_use.calls == []


@pytest.mark.asyncio
async def test_missing_or_unavailable_exact_bootstrap_keeps_ports_unavailable() -> None:
    records, governed, pack, authority, active = await _activated_stack()
    build = _build(active)
    empty = ProductScopedImmutableRecordStore(
        product_id=build.product_id,
        store=InMemoryImmutableRecordStore(),
    )
    missing_bootstrap = await DurableIntelligenceBuildHostComposer(
        governed_state=governed,
        runtime_use=_RuntimeUse(),
        packs=_PackResolver(pack),
    ).compose(
        build=build,
        records=empty,
        resources=_Resources(),
        activation_authority=authority,
    )

    class _MissingPack:
        async def load_exact(self, *, reference):
            return None

    missing_pack = await DurableIntelligenceBuildHostComposer(
        governed_state=governed,
        runtime_use=_RuntimeUse(),
        packs=_MissingPack(),
    ).compose(
        build=build,
        records=ProductScopedImmutableRecordStore(product_id=build.product_id, store=records),
        resources=_Resources(),
        activation_authority=authority,
    )

    for services in (missing_bootstrap, missing_pack):
        assert services.recorded_sources is None
        assert services.prepared_derivations is None


@pytest.mark.asyncio
async def test_correlated_malformed_or_ambiguous_bootstrap_fails_closed() -> None:
    records, governed, pack, authority, active = await _activated_stack()
    build = _build(active)

    class _DuplicateArtifacts:
        def __init__(self, store):
            self.store = store

        async def read_as_of(self, **kwargs):
            result = await self.store.read_as_of(**kwargs)
            if kwargs["record_kind"] == "onboarding_artifact":
                return (*result, *result)
            return result

        def __getattr__(self, name):
            return getattr(self.store, name)

    composer = DurableIntelligenceBuildHostComposer(
        governed_state=governed,
        runtime_use=_RuntimeUse(),
        packs=_PackResolver(pack),
    )
    with pytest.raises(IntelligenceBuildHostCompositionError, match="more than one"):
        await composer.compose(
            build=build,
            records=ProductScopedImmutableRecordStore(
                product_id=build.product_id,
                store=_DuplicateArtifacts(records),
            ),
            resources=_Resources(),
            activation_authority=authority,
        )

    class _CorruptPlan:
        def __init__(self, store):
            self.store = store

        async def read_as_of(self, **kwargs):
            result = await self.store.read_as_of(**kwargs)
            if kwargs["record_kind"] != "onboarding_artifact":
                return result
            return tuple(
                item.model_copy(update={"payload": {**item.payload, "artifact_digest": "sha256:" + "f" * 64}})
                if item.payload_contract == "ace.application.builder-activation-plan-artifact/v1alpha1"
                else item
                for item in result
            )

        def __getattr__(self, name):
            return getattr(self.store, name)

    with pytest.raises(IntelligenceBuildHostCompositionError, match="correlated Builder activation plan"):
        await composer.compose(
            build=build,
            records=ProductScopedImmutableRecordStore(
                product_id=build.product_id,
                store=_CorruptPlan(records),
            ),
            resources=_Resources(),
            activation_authority=authority,
        )

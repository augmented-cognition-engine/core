from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

import ace.application as application_api
from ace.application import (
    BuilderActivationPlanArtifactV1,
    BuilderActivationReceiptArtifactV1,
    CoreIntelligenceBuildFirstBriefService,
    IntelligenceBuilderSessionService,
    IntelligenceBuildFirstBriefCognition,
    IntelligenceBuildFirstBriefError,
    IntelligenceBuildFirstBriefRequestV1Alpha1,
    OnboardingArtifactKind,
    OnboardingArtifactReferenceV1,
    OnboardingStage,
    OnboardingTransitionAuthority,
    ProductScopedImmutableRecordStore,
    bind_committed_activation,
)
from ace.application.domain_activation_plan_contracts import (
    ActivationRuntimeState,
    DomainActivationCommitReferenceV1Alpha2,
)
from ace.application.intelligence_build_host import DurableIntelligenceBuildHostComposer
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    GovernedStateHeadV1,
)
from ace.intelligence import ActivationRevisionReferenceV1Alpha1
from tests.intelligence.test_brief_synthesis import (
    ACTIVATED_AT,
    PRODUCT,
    REQUESTED_AT,
    _Environment,
    _environment,
    _PackArchive,
)
from tests.intelligence.test_prepared_shift_signal import (
    _build,
    _CurrentBuildAuthority,
)

pytestmark = pytest.mark.unit


async def _binding(env: _Environment):
    committed = await env.activation_service.reload(
        product_id=PRODUCT,
        activation_key=env.request.activation_revision.activation_key,
    )
    assert committed is not None
    return bind_committed_activation(pack=env.pack, committed=committed)


async def _active_session(env: _Environment, binding):
    sessions = IntelligenceBuilderSessionService(store=env.store)
    actor = env.request.authenticated_context.actor_ref
    at = ACTIVATED_AT - timedelta(minutes=2)
    current = (
        await sessions.start(
            product_id=PRODUCT,
            correlation_id="builder_correlation:first-brief",
            goal_ref="builder_goal:first-brief",
            actor_ref=actor,
            occurred_at=at,
        )
    ).revision
    transitions = (
        (OnboardingStage.SOURCES_CONNECTING, OnboardingTransitionAuthority.AGENT_PROPOSAL, None),
        (
            OnboardingStage.SOURCES_READY,
            OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION,
            "approval:source-scope",
        ),
        (OnboardingStage.CONCEPT_MODEL_PROPOSED, OnboardingTransitionAuthority.AGENT_PROPOSAL, None),
        (
            OnboardingStage.CONCEPT_MODEL_APPROVED,
            OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION,
            "approval:concept-model",
        ),
        (
            OnboardingStage.INTELLIGENCE_MODEL_PROPOSED,
            OnboardingTransitionAuthority.AGENT_PROPOSAL,
            None,
        ),
        (
            OnboardingStage.INTELLIGENCE_MODEL_APPROVED,
            OnboardingTransitionAuthority.HUMAN_CORE_DISPOSITION,
            "approval:intelligence-model",
        ),
        (OnboardingStage.FIRST_BRIEFING_READY, OnboardingTransitionAuthority.AGENT_PROPOSAL, None),
    )
    for offset, (stage, authority, approval) in enumerate(transitions, start=1):
        current = (
            await sessions.advance(
                current,
                stage=stage,
                authority=authority,
                actor_ref=actor,
                occurred_at=at + timedelta(seconds=offset),
                approval_receipt_ref=approval,
            )
        ).revision

    source_commit = DomainActivationCommitReferenceV1Alpha2(
        product_id=PRODUCT,
        activation_key=binding.prepared_binding.reference.activation_key,
        activation_id=binding.prepared_binding.reference.activation_id,
        state=ActivationRuntimeState.ACTIVE,
        plan_id="activation_plan:first-brief",
        plan_digest="sha256:" + "1" * 64,
        revision=1,
        revision_id="activation_revision_v1alpha2:first-brief",
        revision_digest="sha256:" + "2" * 64,
        commit_receipt_id="activation_commit_v1alpha2:first-brief",
        commit_receipt_digest="sha256:" + "3" * 64,
        committed_at=ACTIVATED_AT - timedelta(seconds=1),
    )
    plan = BuilderActivationPlanArtifactV1(
        session_id=current.session_id,
        session_revision_id=str(current.revision_id),
        session_revision_digest=str(current.revision_digest),
        source_commit=source_commit,
        spec_id=str(binding.prepared_binding.revision.spec.spec_id),
        spec_digest=f"sha256:{binding.prepared_binding.revision.spec.spec_hash}",
        pack=binding.prepared_binding.revision.spec.pack,
        created_at=ACTIVATED_AT,
    )
    await sessions.persist_artifact(product_id=PRODUCT, artifact=plan)
    plan_ref = OnboardingArtifactReferenceV1(
        artifact_kind=OnboardingArtifactKind.ACTIVATION_PLAN,
        artifact_id=str(plan.artifact_id),
        artifact_digest=str(plan.artifact_digest),
    )
    current = (
        await sessions.advance(
            current,
            stage=OnboardingStage.ACTIVATION_PENDING,
            authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
            actor_ref=actor,
            occurred_at=ACTIVATED_AT + timedelta(seconds=2),
            artifacts=(plan_ref,),
        )
    ).revision
    canonical = binding.commit_receipt
    receipt = BuilderActivationReceiptArtifactV1(
        session_id=current.session_id,
        activation_plan_artifact_id=str(plan.artifact_id),
        activation_plan_artifact_digest=str(plan.artifact_digest),
        source_commit=source_commit,
        canonical_revision=ActivationRevisionReferenceV1Alpha1.model_validate(
            binding.prepared_binding.reference.model_dump(mode="python")
        ),
        canonical_state_kind=canonical.state_kind,
        canonical_commit_receipt_id=str(canonical.receipt_id),
        canonical_commit_receipt_digest=f"sha256:{canonical.receipt_hash}",
        activated_at=canonical.committed_at,
    )
    await sessions.persist_artifact(product_id=PRODUCT, artifact=receipt)
    receipt_ref = OnboardingArtifactReferenceV1(
        artifact_kind=OnboardingArtifactKind.ACTIVATION_RECEIPT,
        artifact_id=str(receipt.artifact_id),
        artifact_digest=str(receipt.artifact_digest),
    )
    current = (
        await sessions.advance(
            current,
            stage=OnboardingStage.ACTIVE,
            authority=OnboardingTransitionAuthority.CORE_ACTIVATION,
            actor_ref=actor,
            occurred_at=ACTIVATED_AT + timedelta(seconds=3),
            artifacts=(plan_ref, receipt_ref),
            approval_receipt_ref=str(canonical.approval.receipt_ref),
        )
    ).revision
    return sessions, current


async def _stack(*, cognition: bool = True):
    env = await _environment()
    binding = await _binding(env)
    sessions, session = await _active_session(env, binding)
    grant = GovernedStateHeadV1(
        state_kind="authority_grant",
        product_id=PRODUCT,
        state_id="authority_grant:atrium-intelligence-build",
        sequence=1,
        revision_id="authority_grant_revision:first-brief",
        commit_receipt_id="governed_state_commit:first-brief",
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
    original_authority = build.authority_use
    authority_use = AuthorityUseReceiptV1Alpha1(
        **original_authority.model_dump(
            mode="python",
            exclude={
                "actor_ref",
                "authenticated_context",
                "receipt_id",
                "receipt_digest",
            },
        ),
        actor_ref=actor,
        authenticated_context=context,
    )
    build = replace(build, actor_ref=actor, authority_use=authority_use)
    request = IntelligenceBuildFirstBriefRequestV1Alpha1(
        session_id=session.session_id,
        session_revision_id=str(session.revision_id),
        session_revision_digest=str(session.revision_digest),
        derivation_key=env.request.derivation_key,
        attention_receipt_id=str(env.attention.receipt_id),
        attention_receipt_digest=str(env.attention.receipt_digest),
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
    )
    return env, build, sessions, session, request, service


class _Resources:
    async def query(self, **_kwargs):
        raise AssertionError("first-Brief host composition must not query projections")


@pytest.mark.asyncio
async def test_durable_host_exposes_first_brief_only_with_injected_governed_cognition():
    env, build, _, _, _, service = await _stack()
    scoped = ProductScopedImmutableRecordStore(product_id=PRODUCT, store=env.store)

    host = await DurableIntelligenceBuildHostComposer(
        governed_state=env.activation_service.store,
        runtime_use=_CurrentBuildAuthority(build.authority_use),
        packs=_PackArchive(env.pack),
        first_brief_cognition=service.cognition,
    ).compose(
        build=build,
        records=scoped,
        resources=_Resources(),
        activation_authority=env.activation_service.authority,
    )
    unavailable = await DurableIntelligenceBuildHostComposer(
        governed_state=env.activation_service.store,
        runtime_use=_CurrentBuildAuthority(build.authority_use),
        packs=_PackArchive(env.pack),
    ).compose(
        build=build,
        records=scoped,
        resources=_Resources(),
        activation_authority=env.activation_service.authority,
    )

    assert isinstance(host.first_brief, CoreIntelligenceBuildFirstBriefService)
    assert unavailable.first_brief is None


@pytest.mark.asyncio
async def test_canonical_first_brief_reopens_and_replays_without_second_provider_call():
    env, build, sessions, _, request, service = await _stack()

    first = await service.create_first_brief(request)
    restarted = CoreIntelligenceBuildFirstBriefService(
        build=build,
        sessions=IntelligenceBuilderSessionService(store=env.store),
        activations=env.activation_service,
        packs=_PackArchive(env.pack),
        records=env.store,
        runtime_use=_CurrentBuildAuthority(build.authority_use),
        cognition=IntelligenceBuildFirstBriefCognition(
            reasoning=env.service.reasoning,
            execution_binding=env.execution_binding,
            append_binding=env.append_binding,
        ),
    )
    replay = await restarted.create_first_brief(request)

    assert replay == replace(first, admission=replace(first.admission, replayed=True))
    assert replay.session == await sessions.load_latest(
        product_id=PRODUCT,
        session_id=request.session_id,
        available_at=REQUESTED_AT,
    )
    assert env.provider.calls == 1
    assert replay.admission.brief.citations
    assert replay.admission.synthesis_receipt.template_id == "price_brief"
    assert replay.admission.synthesis_receipt.persona_ids == ("pricing_reviewer",)


@pytest.mark.asyncio
async def test_missing_cognition_setup_fails_closed_before_provider_or_append():
    env, _, _, _, request, service = await _stack(cognition=False)

    with pytest.raises(IntelligenceBuildFirstBriefError, match="composition is not installed"):
        await service.create_first_brief(request)

    assert env.provider.calls == 0


@pytest.mark.asyncio
async def test_stale_session_wrong_attention_and_revoked_build_authority_fail_closed():
    env, build, sessions, session, request, service = await _stack()
    material = request.model_dump(mode="python", exclude={"request_id", "request_digest"})
    stale = IntelligenceBuildFirstBriefRequestV1Alpha1(
        **{**material, "session_revision_id": str(session.prior_revision_id)}
    )
    with pytest.raises(IntelligenceBuildFirstBriefError, match="exact current active Builder revision"):
        await service.create_first_brief(stale)

    wrong_attention = IntelligenceBuildFirstBriefRequestV1Alpha1(
        **{**material, "attention_receipt_digest": "sha256:" + "9" * 64}
    )
    with pytest.raises(IntelligenceBuildFirstBriefError, match="exact current routed attention receipt"):
        await service.create_first_brief(wrong_attention)

    denied = CoreIntelligenceBuildFirstBriefService(
        build=build,
        sessions=sessions,
        activations=env.activation_service,
        packs=_PackArchive(env.pack),
        records=env.store,
        runtime_use=_CurrentBuildAuthority(build.authority_use, denied=True),
        cognition=service.cognition,
    )
    with pytest.raises(IntelligenceBuildFirstBriefError, match="current build authority denied"):
        await denied.create_first_brief(request)
    assert env.provider.calls == 0


def test_first_brief_contracts_are_public_without_expanding_core_or_intelligence():
    assert application_api.IntelligenceBuildFirstBriefPort
    assert application_api.CoreIntelligenceBuildFirstBriefService
    assert application_api.IntelligenceBuildFirstBriefRequestV1Alpha1

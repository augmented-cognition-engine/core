from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application import (
    IntelligenceBuilderPresentationService,
    IntelligenceBuilderResourceProjectionReader,
    IntelligenceBuilderSessionService,
    OnboardingBlockReason,
    OnboardingStage,
    OnboardingTransitionAuthority,
)
from ace.core import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence import (
    IntelligenceOnboardingCadenceV1Alpha1,
    IntelligenceOnboardingFirstValueV1Alpha1,
    IntelligenceOnboardingGuardrailsV1Alpha1,
    IntelligenceOnboardingOutcomeV1Alpha1,
    IntelligenceOnboardingProfileV1Alpha1,
    IntelligenceOnboardingSourceGroupV1Alpha1,
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourceQueryV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

BASE = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
PRODUCT = "product:atrium-demo"


def _profile() -> IntelligenceOnboardingProfileV1Alpha1:
    return IntelligenceOnboardingProfileV1Alpha1(
        profile_id="onboarding_profile:ai-command-center",
        topic_id="artificial-intelligence",
        domain_label="World Intelligence",
        topic_label="Artificial intelligence",
        display_name="AI Command Center",
        prompt="What should your AI command center help you understand?",
        description="Connect authoritative AI sources and receive a grounded first briefing.",
        starter_prompts=("Keep me ahead of meaningful AI capability, cost, and policy shifts.",),
        outcomes=(
            IntelligenceOnboardingOutcomeV1Alpha1(
                outcome_id="track-model-economics",
                label="Track model economics",
                description="Watch model releases, pricing, and cost-per-capability shifts.",
                icon_hint="coins",
                recommended_watch_ids=("model-economics",),
                recommended_intelligence_ids=("market-shifts",),
                recommended_topic_labels=("Model economics",),
                recommended_intelligence_labels=("Market shifts",),
            ),
        ),
        source_groups=(
            IntelligenceOnboardingSourceGroupV1Alpha1(
                source_group_id="independent-evidence",
                label="Independent evidence",
                description="Reviewed measurements that test first-party claims.",
                evidence_role="independent-measurement",
                source_ids=("stanford-helm", "metr"),
                source_labels=("Stanford HELM", "METR"),
                access_label="Public · no credentials",
                default_selected=True,
            ),
        ),
        cadences=(
            IntelligenceOnboardingCadenceV1Alpha1(
                cadence_id="daily",
                label="Daily",
                description="One daily executive briefing plus material alerts.",
            ),
        ),
        default_cadence_id="daily",
        first_value=IntelligenceOnboardingFirstValueV1Alpha1(
            completion_label="Open your first AI briefing",
        ),
        guardrails=IntelligenceOnboardingGuardrailsV1Alpha1(),
    )


def _query(*kinds: IntelligenceResourceKind) -> IntelligenceResourceQueryV1Alpha1:
    return IntelligenceResourceQueryV1Alpha1(
        authenticated_context=AuthenticatedRuntimeContextV1Alpha1(
            product_id=PRODUCT,
            actor_ref="principal:analyst",
            authentication_receipt_ref="authentication_receipt:builder-projection",
            authentication_receipt_digest="sha256:" + "d" * 64,
            authenticated_at=BASE,
            expires_at=BASE + timedelta(hours=1),
        ),
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=kinds,
        as_of=BASE + timedelta(minutes=10),
        available_at=BASE + timedelta(minutes=10),
        page_size=30,
    )


@pytest.mark.asyncio
async def test_multiple_domain_profiles_form_one_product_scoped_catalog() -> None:
    store = InMemoryImmutableRecordStore()
    service = IntelligenceBuilderPresentationService(store=store)
    world = _profile()
    market_payload = world.model_dump(mode="python")
    market_payload.update(
        {
            "profile_id": "onboarding_profile:market-intelligence",
            "profile_digest": None,
            "topic_id": "market-intelligence",
            "domain_label": "Marketing Intelligence",
            "topic_label": "Your market and competitors",
            "display_name": "Marketing Intelligence Command Center",
        }
    )
    market = IntelligenceOnboardingProfileV1Alpha1.model_validate(market_payload)

    await service.admit_profile(product_id=PRODUCT, profile=world, admitted_at=BASE)
    await service.admit_profile(product_id=PRODUCT, profile=market, admitted_at=BASE + timedelta(seconds=1))

    batch = await IntelligenceBuilderResourceProjectionReader(store=store).read(
        query=_query(IntelligenceResourceKind.BUILDER_PROFILE),
        after=None,
        limit=30,
    )

    assert [record.reference.resource_id for record in batch.records] == [
        "onboarding_profile:ai-command-center",
        "onboarding_profile:market-intelligence",
    ]
    assert [record.payload.parsed_value()["domain_label"] for record in batch.records if record.payload] == [
        "World Intelligence",
        "Marketing Intelligence",
    ]


@pytest.mark.asyncio
async def test_profile_and_session_revisions_project_through_one_rebuildable_reader() -> None:
    store = InMemoryImmutableRecordStore()
    profile_service = IntelligenceBuilderPresentationService(store=store)
    session_service = IntelligenceBuilderSessionService(store=store)

    first_profile = await profile_service.admit_profile(
        product_id=PRODUCT,
        profile=_profile(),
        admitted_at=BASE,
    )
    replay = await profile_service.admit_profile(
        product_id=PRODUCT,
        profile=_profile(),
        admitted_at=BASE,
    )
    assert first_profile.replayed is False
    assert replay.replayed is True
    assert replay.transaction_receipt == first_profile.transaction_receipt

    started = await session_service.start(
        product_id=PRODUCT,
        correlation_id="correlation:ai-command-center-demo",
        goal_ref="goal:track-ai-change",
        actor_ref="principal:analyst",
        occurred_at=BASE + timedelta(minutes=1),
    )
    connecting = await session_service.advance(
        started.revision,
        stage=OnboardingStage.SOURCES_CONNECTING,
        authority=OnboardingTransitionAuthority.AGENT_PROPOSAL,
        actor_ref="agent:connection",
        occurred_at=BASE + timedelta(minutes=2),
    )

    reader = IntelligenceBuilderResourceProjectionReader(store=store)
    batch = await reader.read(
        query=_query(IntelligenceResourceKind.BUILDER_PROFILE, IntelligenceResourceKind.BUILDER_SESSION),
        after=None,
        limit=30,
    )

    assert batch.state is IntelligenceResourcePageState.COMPLETE
    assert [item.reference.resource_kind for item in batch.records] == [
        IntelligenceResourceKind.BUILDER_PROFILE,
        IntelligenceResourceKind.BUILDER_SESSION,
        IntelligenceResourceKind.BUILDER_SESSION,
    ]
    profile_record, first_session, second_session = batch.records
    assert profile_record.payload is not None
    assert profile_record.payload.parsed_value()["guardrails"]["authorizes_connections"] is False
    assert profile_record.payload.parsed_value()["domain_label"] == "World Intelligence"
    assert profile_record.payload.parsed_value()["topic_label"] == "Artificial intelligence"
    assert profile_record.payload.parsed_value()["starter_prompts"] == [
        "Keep me ahead of meaningful AI capability, cost, and policy shifts."
    ]
    assert profile_record.payload.parsed_value()["source_groups"] == [
        {
            "access_label": "Public · no credentials",
            "default_selected": True,
            "description": "Reviewed measurements that test first-party claims.",
            "evidence_role": "independent-measurement",
            "label": "Independent evidence",
            "source_group_id": "independent-evidence",
            "source_ids": ["metr", "stanford-helm"],
            "source_labels": ["METR", "Stanford HELM"],
        }
    ]
    assert first_session.reference.revision == 1
    assert second_session.reference.revision == 2
    assert second_session.supersedes == first_session.reference
    assert second_session.payload is not None
    assert second_session.payload.parsed_value()["stage"] == "sources_connecting"

    restarted = await IntelligenceBuilderResourceProjectionReader(store=store).read(
        query=_query(IntelligenceResourceKind.BUILDER_PROFILE, IntelligenceResourceKind.BUILDER_SESSION),
        after=None,
        limit=30,
    )
    assert restarted == batch
    assert connecting.revision.revision_digest == second_session.reference.resource_digest


@pytest.mark.asyncio
async def test_blocked_builder_session_is_truthfully_degraded() -> None:
    store = InMemoryImmutableRecordStore()
    service = IntelligenceBuilderSessionService(store=store)
    started = await service.start(
        product_id=PRODUCT,
        correlation_id="correlation:blocked-demo",
        goal_ref="goal:track-ai-change",
        actor_ref="principal:analyst",
        occurred_at=BASE,
    )
    blocked = await service.block(
        started.revision,
        reason=OnboardingBlockReason.FAILED_CONNECTOR,
        actor_ref="agent:connection",
        safe_diagnostic="The public policy source did not respond. Retry is safe.",
        occurred_at=BASE + timedelta(minutes=1),
    )

    batch = await IntelligenceBuilderResourceProjectionReader(store=store).read(
        query=_query(IntelligenceResourceKind.BUILDER_SESSION),
        after=None,
        limit=30,
    )

    assert batch.state is IntelligenceResourcePageState.DEGRADED
    assert len(batch.records) == 2
    latest = batch.records[-1]
    assert latest.availability is IntelligenceResourceAvailability.DEGRADED
    assert latest.summary == "The public policy source did not respond. Retry is safe."
    assert latest.degraded_reason_refs == ("degraded_reason:intelligence-builder:failed_connector",)
    assert blocked.revision.revision_digest == latest.reference.resource_digest

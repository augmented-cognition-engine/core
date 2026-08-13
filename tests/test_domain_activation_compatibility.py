from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.domain_activation_compatibility import (
    DOMAIN_ACTIVATION_V1ALPHA2_TO_V1ALPHA1_VERSION,
    DomainActivationCompatibilityError,
    DomainActivationCompatibilityService,
    adapt_initial_activation_to_canonical_v1alpha1,
)
from ace.application.domain_activation_plan_contracts import (
    ActivationOnboardingHandoffV1Alpha2,
    ActivationPlanAction,
    ActivationRequestedEffect,
    ActivationRuntimeState,
    DomainActivationRevisionV1Alpha2,
    IntelligenceActivationPlanV1Alpha2,
)
from ace.core import ResolvedApprovalReceiptV1, canonical_hash
from ace.intelligence.contracts.activation import (
    ActivationState,
    CompiledOverlayV1,
    CompiledPackRefV1,
    DomainActivationSpecV1,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
PRODUCT = "product:personal"
ACTOR = "user:personal"
SPEC_APPROVAL = "approval:canonical-activation-spec"
PLAN_APPROVAL = "approval:v1alpha2-activation-plan"
DIGEST = "sha256:" + "a" * 64


def _handoff() -> ActivationOnboardingHandoffV1Alpha2:
    fields = {
        "session_id": "intelligence_builder_session:one",
        "session_revision_id": "intelligence_builder_session_revision:one",
        "concept_model_proposal_id": "concept_model_proposal:one",
        "concept_model_disposition_id": "concept_model_disposition:one",
        "observation_set_id": "authorized_observation_set:one",
        "intelligence_model_proposal_id": "intelligence_model_proposal:one",
        "intelligence_model_disposition_id": "intelligence_model_disposition:one",
        "briefing_derivation_id": "briefing_derivation:one",
        "first_briefing_preview_id": "first_briefing_preview:one",
    }
    digests = {key.replace("_id", "_digest"): DIGEST for key in fields if key != "session_id"}
    return ActivationOnboardingHandoffV1Alpha2(**fields, **digests)


def _spec() -> DomainActivationSpecV1:
    pack = CompiledPackRefV1(
        pack_id="fixture_pack",
        pack_version="1.0.0",
        compiled_pack_id="pack_ir:" + "a" * 32,
        pack_digest=DIGEST,
    )
    return DomainActivationSpecV1(
        product_id=PRODUCT,
        activation_key="fixture_activation",
        pack=pack,
        overlay=CompiledOverlayV1(
            overlay_id="personal_overlay",
            version="1.0.0",
            pack_id=pack.pack_id,
            pack_version=pack.pack_version,
            pack_digest=pack.pack_digest,
        ),
        compilation_receipt_ref="compilation:fixture",
        conformance_receipt_refs=("conformance:fixture",),
    )


def _revision() -> DomainActivationRevisionV1Alpha2:
    plan = IntelligenceActivationPlanV1Alpha2(
        action=ActivationPlanAction.INITIAL_ACTIVATION,
        onboarding_handoff=_handoff(),
        spec=_spec(),
        requested_effects=(ActivationRequestedEffect.PACK_ACTIVATION,),
        created_at=NOW,
    )
    return DomainActivationRevisionV1Alpha2(
        revision=1,
        plan=plan,
        state=ActivationRuntimeState.ACTIVE,
        actor_ref=ACTOR,
        approval_receipt_ref=PLAN_APPROVAL,
        occurred_at=NOW + timedelta(minutes=2),
    )


def _approval(**changes) -> ResolvedApprovalReceiptV1:
    revision = _revision()
    material = {
        "receipt_ref": SPEC_APPROVAL,
        "product_id": PRODUCT,
        "subject_ref": str(revision.plan.spec.spec_id),
        "actor_ref": ACTOR,
        "receipt_hash": canonical_hash("canonical-spec-approval"),
        "approved_at": NOW + timedelta(minutes=1),
    }
    material.update(changes)
    return ResolvedApprovalReceiptV1(**material)


def test_initial_plan_adapts_with_separate_exact_spec_approval() -> None:
    revision = _revision()
    result = adapt_initial_activation_to_canonical_v1alpha1(
        revision=revision,
        activation_approval=_approval(),
    )
    assert result.contract == DOMAIN_ACTIVATION_V1ALPHA2_TO_V1ALPHA1_VERSION
    assert result.source_plan_id == revision.plan.plan_id
    assert result.canonical_revision.spec == revision.plan.spec
    assert result.canonical_revision.state is ActivationState.ACTIVE
    assert result.canonical_revision.approval_receipt_ref == SPEC_APPROVAL
    assert result.canonical_revision.approval_receipt_ref != revision.approval_receipt_ref


@pytest.mark.parametrize(
    "changes",
    [
        {"subject_ref": "activation_spec:other"},
        {"product_id": "product:other"},
        {"actor_ref": "user:other"},
        {"approved_at": NOW - timedelta(seconds=1)},
        {"approved_at": NOW + timedelta(minutes=3)},
        {"receipt_ref": PLAN_APPROVAL},
    ],
)
def test_mismatched_reused_or_stale_approval_fails_closed(changes) -> None:
    with pytest.raises(DomainActivationCompatibilityError):
        adapt_initial_activation_to_canonical_v1alpha1(
            revision=_revision(),
            activation_approval=_approval(**changes),
        )


def test_non_initial_plan_is_not_silently_downgraded() -> None:
    initial = _revision()
    plan = IntelligenceActivationPlanV1Alpha2(
        action=ActivationPlanAction.SUSPEND,
        onboarding_handoff=initial.plan.onboarding_handoff,
        spec=initial.plan.spec,
        requested_effects=(ActivationRequestedEffect.ACTIVATION_SUSPENSION,),
        expected_head_revision_id=str(initial.revision_id),
        created_at=NOW + timedelta(minutes=3),
    )
    suspended = DomainActivationRevisionV1Alpha2(
        revision=2,
        plan=plan,
        state=ActivationRuntimeState.SUSPENDED,
        prior_revision_id=str(initial.revision_id),
        actor_ref=ACTOR,
        approval_receipt_ref="approval:suspend-plan",
        occurred_at=NOW + timedelta(minutes=5),
    )
    with pytest.raises(DomainActivationCompatibilityError, match="only an initial active"):
        adapt_initial_activation_to_canonical_v1alpha1(
            revision=suspended,
            activation_approval=_approval(),
        )


class _Authority:
    def __init__(self, *, revoked: bool = False) -> None:
        self.revoked = revoked
        self.calls: list[dict] = []

    async def resolve_approval(self, **kwargs):
        self.calls.append(kwargs)
        if self.revoked:
            raise PermissionError("approval revoked")
        return _approval(receipt_ref=kwargs["receipt_ref"])

    async def resolve_grant(self, **_kwargs):
        raise AssertionError("compatibility must not resolve or create grants")


@pytest.mark.asyncio
async def test_service_reresolves_current_approval_and_revocation_fails_closed() -> None:
    revision = _revision()
    authority = _Authority()
    result = await DomainActivationCompatibilityService(authority=authority).prepare_initial_canonical_activation(
        revision=revision,
        activation_approval_receipt_ref=SPEC_APPROVAL,
        evaluated_at=revision.occurred_at + timedelta(seconds=1),
    )
    assert result.canonical_revision.spec == revision.plan.spec
    assert authority.calls[0]["subject_ref"] == revision.plan.spec.spec_id
    assert authority.calls[0]["effective_at"] > revision.occurred_at

    with pytest.raises(DomainActivationCompatibilityError, match="did not resolve"):
        await DomainActivationCompatibilityService(
            authority=_Authority(revoked=True)
        ).prepare_initial_canonical_activation(
            revision=revision,
            activation_approval_receipt_ref=SPEC_APPROVAL,
            evaluated_at=revision.occurred_at + timedelta(seconds=1),
        )

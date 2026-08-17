"""Governed admission for exact approved v1alpha2 activation plans.

This is an additive sibling to :mod:`ace.application.domain_activation`.  It
does not accept or reinterpret persisted v1alpha1 activation revisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ace.application.briefing_agent_contracts import FirstBriefingPreviewV1
from ace.application.domain_activation import LEGACY_DOMAIN_ACTIVATION_STATE_KIND
from ace.application.domain_activation_plan_contracts import (
    DOMAIN_ACTIVATION_REVISION_V1ALPHA2_VERSION,
    ActivationOnboardingHandoffV1Alpha2,
    ActivationPlanAction,
    ActivationRuntimeState,
    DomainActivationCommitReferenceV1Alpha2,
    DomainActivationRevisionV1Alpha2,
)
from ace.application.intelligence_agent_contracts import (
    AuthorizedObservationSetV1,
    IntelligenceModelDispositionV1,
    IntelligenceModelProposalV1,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingStage,
)
from ace.core.contracts import canonical_hash
from ace.core.state import (
    CoreAuthorityResolver,
    GovernedStateCommitReceiptV1,
    GovernedStateCommitRequestV1,
    GovernedStateRevisionV1,
    GovernedStateStore,
)
from ace.intelligence.contracts.conformance import DomainPackConformanceReceiptV1
from ace.intelligence.contracts.diagnostics import PackCompatibilityStatus
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.contracts.resources import ActivationRevisionReferenceV1Alpha1
from ace.intelligence.packs.activation import prepare_domain_activation
from ace.intelligence.packs.compiler import negotiate_pack_compatibility


class DomainActivationPlanAdmissionError(RuntimeError):
    """Exact-plan activation material failed closed before durable effect."""


DOMAIN_ACTIVATION_PLAN_STATE_KIND = "domain_activation_plan_v1alpha2"
MAX_ACTIVATION_HISTORY_REVISIONS = 512


@dataclass(frozen=True, slots=True)
class CommittedDomainActivationPlan:
    revision: DomainActivationRevisionV1Alpha2
    commit_receipt: GovernedStateCommitReceiptV1
    authority_stage: Literal["committed"] = "committed"

    @property
    def live_authority(self) -> Literal[False]:
        return False


def prepare_activation_onboarding_handoff(
    *,
    session: IntelligenceBuilderSessionRevisionV1,
    observations: AuthorizedObservationSetV1,
    intelligence_model: IntelligenceModelProposalV1,
    intelligence_disposition: IntelligenceModelDispositionV1,
    first_briefing: FirstBriefingPreviewV1,
) -> ActivationOnboardingHandoffV1Alpha2:
    """Close exact inert 0.7D bodies into one non-authorizing plan handoff."""

    try:
        exact_session = IntelligenceBuilderSessionRevisionV1.model_validate(session.model_dump(mode="python"))
        exact_observations = AuthorizedObservationSetV1.model_validate(observations.model_dump(mode="python"))
        exact_model = IntelligenceModelProposalV1.model_validate(intelligence_model.model_dump(mode="python"))
        exact_disposition = IntelligenceModelDispositionV1.model_validate(
            intelligence_disposition.model_dump(mode="python")
        )
        exact_brief = FirstBriefingPreviewV1.model_validate(first_briefing.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError("0.7D activation handoff failed exact body revalidation") from exc
    derivation = exact_brief.derivation
    required_identities = (
        exact_session.revision_id,
        exact_session.revision_digest,
        exact_observations.observation_set_id,
        exact_observations.observation_set_digest,
        exact_model.proposal_id,
        exact_model.proposal_digest,
        exact_disposition.disposition_id,
        exact_disposition.disposition_digest,
        derivation.derivation_id,
        derivation.derivation_digest,
        exact_brief.brief_id,
        exact_brief.brief_digest,
    )
    if any(item is None for item in required_identities):
        raise DomainActivationPlanAdmissionError("0.7D activation handoff is missing exact derived coordinates")
    if exact_session.stage is not OnboardingStage.FIRST_BRIEFING_READY:
        raise DomainActivationPlanAdmissionError("activation handoff requires the exact first_briefing_ready session")
    session_artifacts = {
        (item.artifact_kind, item.artifact_id, item.artifact_digest) for item in exact_session.artifacts
    }
    required_session_artifacts = {
        (
            OnboardingArtifactKind.CONCEPT_MODEL_PROPOSAL,
            derivation.concept_model_proposal_id,
            derivation.concept_model_proposal_digest,
        ),
        (
            OnboardingArtifactKind.CONCEPT_MODEL_DISPOSITION,
            derivation.concept_model_disposition_id,
            derivation.concept_model_disposition_digest,
        ),
        (
            OnboardingArtifactKind.AUTHORIZED_OBSERVATION_SET,
            str(exact_observations.observation_set_id),
            str(exact_observations.observation_set_digest),
        ),
        (
            OnboardingArtifactKind.INTELLIGENCE_MODEL_PROPOSAL,
            str(exact_model.proposal_id),
            str(exact_model.proposal_digest),
        ),
        (
            OnboardingArtifactKind.INTELLIGENCE_MODEL_DISPOSITION,
            str(exact_disposition.disposition_id),
            str(exact_disposition.disposition_digest),
        ),
        (
            OnboardingArtifactKind.FIRST_BRIEFING_PREVIEW,
            str(exact_brief.brief_id),
            str(exact_brief.brief_digest),
        ),
    }
    if not required_session_artifacts.issubset(session_artifacts):
        raise DomainActivationPlanAdmissionError(
            "0.7D activation handoff is absent from the exact session artifact history"
        )
    if (
        exact_observations.session_id != exact_session.session_id
        or exact_model.session_id != exact_session.session_id
        or exact_disposition.session_id != exact_session.session_id
        or derivation.session_id != exact_session.session_id
        or exact_model.observation_set_id != exact_observations.observation_set_id
        or exact_model.observation_set_digest != exact_observations.observation_set_digest
        or exact_disposition.proposal_id != exact_model.proposal_id
        or exact_disposition.proposal_digest != exact_model.proposal_digest
        or derivation.intelligence_model_proposal_id != exact_model.proposal_id
        or derivation.intelligence_model_proposal_digest != exact_model.proposal_digest
        or derivation.intelligence_model_disposition_id != exact_disposition.disposition_id
        or derivation.intelligence_model_disposition_digest != exact_disposition.disposition_digest
        or derivation.observation_set_id != exact_observations.observation_set_id
        or derivation.observation_set_digest != exact_observations.observation_set_digest
    ):
        raise DomainActivationPlanAdmissionError(
            "0.7D activation handoff crossed exact Watch, disposition, Brief, or session material"
        )
    return ActivationOnboardingHandoffV1Alpha2(
        session_id=exact_session.session_id,
        session_revision_id=str(exact_session.revision_id),
        session_revision_digest=str(exact_session.revision_digest),
        concept_model_proposal_id=derivation.concept_model_proposal_id,
        concept_model_proposal_digest=derivation.concept_model_proposal_digest,
        concept_model_disposition_id=derivation.concept_model_disposition_id,
        concept_model_disposition_digest=derivation.concept_model_disposition_digest,
        observation_set_id=str(exact_observations.observation_set_id),
        observation_set_digest=str(exact_observations.observation_set_digest),
        intelligence_model_proposal_id=str(exact_model.proposal_id),
        intelligence_model_proposal_digest=str(exact_model.proposal_digest),
        intelligence_model_disposition_id=str(exact_disposition.disposition_id),
        intelligence_model_disposition_digest=str(exact_disposition.disposition_digest),
        briefing_derivation_id=str(derivation.derivation_id),
        briefing_derivation_digest=str(derivation.derivation_digest),
        first_briefing_preview_id=str(exact_brief.brief_id),
        first_briefing_preview_digest=str(exact_brief.brief_digest),
    )


def _revalidate_revision(
    revision: DomainActivationRevisionV1Alpha2,
) -> DomainActivationRevisionV1Alpha2:
    try:
        return DomainActivationRevisionV1Alpha2.model_validate(revision.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError("v1alpha2 activation revision failed exact revalidation") from exc


def _revalidate_pack(pack: CompiledDomainPackV1) -> CompiledDomainPackV1:
    try:
        return CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError("compiled Domain Pack failed exact admission revalidation") from exc


def _revalidate_receipt(
    receipt: DomainPackConformanceReceiptV1,
) -> DomainPackConformanceReceiptV1:
    try:
        return DomainPackConformanceReceiptV1.model_validate(receipt.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError("conformance receipt failed exact admission revalidation") from exc


def _revalidate_commit_receipt(
    receipt: GovernedStateCommitReceiptV1,
) -> GovernedStateCommitReceiptV1:
    try:
        return GovernedStateCommitReceiptV1.model_validate(receipt.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError("Core commit receipt failed exact revalidation") from exc


def _compatibility_material(pack: CompiledDomainPackV1) -> dict | None:
    return None if pack.declared_compatibility is None else pack.declared_compatibility.model_dump(mode="json")


def _validate_current_activation_material(
    *,
    revision: DomainActivationRevisionV1Alpha2,
    pack: CompiledDomainPackV1,
    conformance_receipts: tuple[DomainPackConformanceReceiptV1, ...],
) -> None:
    plan = revision.plan
    spec = plan.spec
    compatibility = negotiate_pack_compatibility(
        pack.manifest_contract,
        _compatibility_material(pack),
    )
    if compatibility.status not in {
        PackCompatibilityStatus.SUPPORTED,
        PackCompatibilityStatus.DEPRECATED,
    }:
        raise DomainActivationPlanAdmissionError(
            "activation plan uses a pack outside the current supported compatibility window"
        )
    if (
        compatibility.compiler_contract != pack.compiler_contract
        or compatibility.intelligence_contract != pack.intelligence_contract
    ):
        raise DomainActivationPlanAdmissionError("compiled pack contracts no longer match current host compatibility")

    if not conformance_receipts:
        raise DomainActivationPlanAdmissionError("v1alpha2 activation requires passing exact conformance evidence")
    exact_receipts = tuple(_revalidate_receipt(item) for item in conformance_receipts)
    exact_refs = tuple(str(item.receipt_id) for item in exact_receipts)
    if exact_refs != spec.conformance_receipt_refs:
        raise DomainActivationPlanAdmissionError(
            "activation plan conformance references do not match supplied exact evidence"
        )
    for receipt in exact_receipts:
        if not receipt.passed:
            raise DomainActivationPlanAdmissionError("activation plan refuses failed conformance evidence")
        if (
            receipt.pack_id != pack.metadata.pack_id
            or receipt.pack_version != pack.metadata.version
            or receipt.compiled_pack_id != pack.compiled_pack_id
            or receipt.pack_digest != pack.pack_digest
            or receipt.manifest_contract != pack.manifest_contract
            or receipt.compiler_contract != pack.compiler_contract
            or receipt.intelligence_contract != pack.intelligence_contract
            or receipt.compatibility_status != compatibility.status
        ):
            raise DomainActivationPlanAdmissionError(
                "conformance evidence is stale or mismatched for the current pack and host"
            )
        if receipt.compilation_result_id != spec.compilation_receipt_ref:
            raise DomainActivationPlanAdmissionError(
                "conformance evidence does not bind the activation compilation result"
            )

    try:
        reconstructed = prepare_domain_activation(
            product_id=spec.product_id,
            activation_key=spec.activation_key,
            pack=pack,
            overlay=spec.overlay,
            compilation_receipt_ref=spec.compilation_receipt_ref,
            conformance_receipt_refs=spec.conformance_receipt_refs,
            conformance_receipts=exact_receipts,
            capability_bindings=spec.capability_bindings,
            authority_bindings=spec.authority_bindings,
        )
    except (TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError(
            "embedded activation specification failed current material validation"
        ) from exc
    if reconstructed != spec:
        raise DomainActivationPlanAdmissionError(
            "embedded activation specification drifted from current exact material"
        )


def _envelope(revision: DomainActivationRevisionV1Alpha2) -> GovernedStateRevisionV1:
    if (
        revision.activation_id is None
        or revision.revision_id is None
        or revision.revision_digest is None
        or revision.plan.plan_id is None
    ):
        raise DomainActivationPlanAdmissionError("v1alpha2 activation material is missing a derived identity")
    return GovernedStateRevisionV1(
        state_kind=DOMAIN_ACTIVATION_PLAN_STATE_KIND,
        product_id=revision.plan.spec.product_id,
        state_id=revision.activation_id,
        sequence=revision.revision,
        revision_id=revision.revision_id,
        material_hash=revision.revision_digest.removeprefix("sha256:"),
        prior_revision_id=revision.prior_revision_id,
        approval_subject_ref=revision.plan.plan_id,
        payload_contract=DOMAIN_ACTIVATION_REVISION_V1ALPHA2_VERSION,
        payload=revision.model_dump(mode="python"),
    )


def _validate_committed_pair(
    revision: DomainActivationRevisionV1Alpha2,
    receipt: GovernedStateCommitReceiptV1,
) -> CommittedDomainActivationPlan:
    receipt = _revalidate_commit_receipt(receipt)
    envelope = _envelope(revision)
    expected = {
        "product_id": envelope.product_id,
        "state_id": envelope.state_id,
        "sequence": envelope.sequence,
        "revision_id": envelope.revision_id,
        "material_hash": envelope.material_hash,
        "prior_revision_id": envelope.prior_revision_id,
    }
    if receipt.state_kind not in {DOMAIN_ACTIVATION_PLAN_STATE_KIND, LEGACY_DOMAIN_ACTIVATION_STATE_KIND} or any(
        getattr(receipt, name) != value for name, value in expected.items()
    ):
        raise DomainActivationPlanAdmissionError(
            "Core commit receipt does not bind the exact v1alpha2 activation revision"
        )
    if (
        receipt.approval.subject_ref != revision.plan.plan_id
        or receipt.approval.receipt_ref != revision.approval_receipt_ref
        or receipt.approval.disposition != revision.approval_disposition
        or receipt.approval.product_id != revision.plan.spec.product_id
        or receipt.approval.actor_ref != revision.actor_ref
        or receipt.actor_ref != revision.actor_ref
        or receipt.approval.approved_at < revision.plan.created_at
        or receipt.approval.approved_at > revision.occurred_at
        or receipt.committed_at < revision.occurred_at
    ):
        raise DomainActivationPlanAdmissionError(
            "Core commit receipt does not preserve the exact activation-plan approval"
        )
    authority_by_grant = {item.grant_ref: item for item in receipt.authority_grants}
    expected_authority = {item.grant_ref: item for item in revision.plan.requested_authorities}
    if len(authority_by_grant) != len(receipt.authority_grants) or set(authority_by_grant) != set(expected_authority):
        raise DomainActivationPlanAdmissionError(
            "Core commit receipt does not preserve the exact activation-plan authority set"
        )
    for grant_ref, binding in expected_authority.items():
        grant = authority_by_grant[grant_ref]
        if (
            grant.product_id != revision.plan.spec.product_id
            or grant.authority != binding.authority
            or grant.effective_at != revision.occurred_at
            or (grant.expires_at is not None and grant.expires_at <= revision.occurred_at)
        ):
            raise DomainActivationPlanAdmissionError(
                "Core commit receipt contains mismatched activation-plan authority"
            )
    return CommittedDomainActivationPlan(revision=revision, commit_receipt=receipt)


def activation_commit_reference(
    committed: CommittedDomainActivationPlan,
) -> DomainActivationCommitReferenceV1Alpha2:
    """Return immutable lineage coordinates without granting present authority."""

    if not isinstance(committed, CommittedDomainActivationPlan):
        raise DomainActivationPlanAdmissionError("activation commit reference requires an exact committed plan tuple")
    validated = _validate_committed_pair(
        _revalidate_revision(committed.revision),
        committed.commit_receipt,
    )
    revision = validated.revision
    receipt = validated.commit_receipt
    if (
        revision.activation_id is None
        or revision.plan.plan_id is None
        or revision.plan.plan_digest is None
        or revision.revision_id is None
        or revision.revision_digest is None
        or receipt.receipt_id is None
        or receipt.receipt_hash is None
    ):
        raise DomainActivationPlanAdmissionError("committed activation is missing exact historical coordinates")
    return DomainActivationCommitReferenceV1Alpha2(
        product_id=revision.plan.spec.product_id,
        activation_key=revision.plan.spec.activation_key,
        activation_id=revision.activation_id,
        state=revision.state,
        plan_id=revision.plan.plan_id,
        plan_digest=revision.plan.plan_digest,
        revision=revision.revision,
        revision_id=revision.revision_id,
        revision_digest=revision.revision_digest,
        commit_receipt_id=receipt.receipt_id,
        commit_receipt_digest=f"sha256:{receipt.receipt_hash}",
        committed_at=receipt.committed_at,
    )


def validate_activation_commit_reference(
    reference: DomainActivationCommitReferenceV1Alpha2,
    *,
    committed: CommittedDomainActivationPlan,
) -> DomainActivationCommitReferenceV1Alpha2:
    """Resolve serialized lineage coordinates against exact committed material."""

    try:
        validated_reference = DomainActivationCommitReferenceV1Alpha2.model_validate(
            reference.model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError(
            "activation commit reference failed exact structural revalidation"
        ) from exc
    expected = activation_commit_reference(committed)
    if validated_reference != expected:
        raise DomainActivationPlanAdmissionError(
            "activation commit reference does not match exact committed coordinates"
        )
    return expected


def _parse_persisted_revision(
    envelope: GovernedStateRevisionV1,
) -> DomainActivationRevisionV1Alpha2:
    if envelope.payload_contract != DOMAIN_ACTIVATION_REVISION_V1ALPHA2_VERSION:
        raise DomainActivationPlanAdmissionError(
            "mixed v1alpha1/v1alpha2 activation history requires an explicit future migration"
        )
    try:
        revision = DomainActivationRevisionV1Alpha2.model_validate(envelope.payload)
    except (TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError(
            "persisted v1alpha2 activation revision failed exact revalidation"
        ) from exc
    expected = _envelope(revision)
    fields = (
        "contract",
        "product_id",
        "state_id",
        "sequence",
        "revision_id",
        "material_hash",
        "prior_revision_id",
        "approval_subject_ref",
        "payload_contract",
    )
    if envelope.state_kind not in {DOMAIN_ACTIVATION_PLAN_STATE_KIND, LEGACY_DOMAIN_ACTIVATION_STATE_KIND} or any(
        getattr(expected, name) != getattr(envelope, name) for name in fields
    ):
        raise DomainActivationPlanAdmissionError("persisted envelope does not match exact v1alpha2 activation material")
    return revision


class DomainActivationPlanAdmissionService:
    """Resolve exact-plan authority and atomically commit v1alpha2 revisions."""

    def __init__(self, *, store: GovernedStateStore, authority: CoreAuthorityResolver) -> None:
        self.store = store
        self.authority = authority

    async def _current(
        self,
        revision: DomainActivationRevisionV1Alpha2,
    ) -> DomainActivationRevisionV1Alpha2 | None:
        head = await self.store.load_head(
            state_kind=DOMAIN_ACTIVATION_PLAN_STATE_KIND,
            product_id=revision.plan.spec.product_id,
            state_id=str(revision.activation_id),
        )
        if head is None:
            return None
        envelope = await self.store.load_revision(
            head.revision_id,
            product_id=revision.plan.spec.product_id,
        )
        if envelope is None:
            raise DomainActivationPlanAdmissionError("current activation head has an incomplete revision chain")
        current = _parse_persisted_revision(envelope)
        if (
            head.sequence != current.revision
            or head.revision_id != current.revision_id
            or head.state_id != current.activation_id
        ):
            raise DomainActivationPlanAdmissionError(
                "current activation head does not bind its exact v1alpha2 revision"
            )
        return current

    async def _validate_transition(
        self,
        revision: DomainActivationRevisionV1Alpha2,
    ) -> None:
        current = await self._current(revision)
        action = revision.plan.action
        if action is ActivationPlanAction.INITIAL_ACTIVATION:
            if current is not None or revision.revision != 1:
                raise DomainActivationPlanAdmissionError("initial activation requires an empty exact activation scope")
            return
        if current is None:
            raise DomainActivationPlanAdmissionError("non-initial activation requires a current v1alpha2 head")
        if (
            revision.prior_revision_id != current.revision_id
            or revision.plan.expected_head_revision_id != current.revision_id
            or revision.revision != current.revision + 1
        ):
            raise DomainActivationPlanAdmissionError("activation plan is stale or superseded by the current head")
        if revision.occurred_at <= current.occurred_at:
            raise DomainActivationPlanAdmissionError("activation transition time must follow the current revision")

        same_spec = revision.plan.spec == current.plan.spec
        if action is ActivationPlanAction.UPGRADE:
            if current.state is not ActivationRuntimeState.ACTIVE or same_spec:
                raise DomainActivationPlanAdmissionError(
                    "upgrade requires an active head and a changed exact activation specification"
                )
        elif action is ActivationPlanAction.SUSPEND:
            if current.state is not ActivationRuntimeState.ACTIVE or not same_spec:
                raise DomainActivationPlanAdmissionError("suspension requires the exact current active specification")
        elif action is ActivationPlanAction.REACTIVATE:
            if current.state is not ActivationRuntimeState.SUSPENDED or not same_spec:
                raise DomainActivationPlanAdmissionError(
                    "reactivation requires the exact current suspended specification"
                )
        elif action is ActivationPlanAction.RETIRE:
            if (
                current.state
                not in {
                    ActivationRuntimeState.ACTIVE,
                    ActivationRuntimeState.SUSPENDED,
                }
                or not same_spec
            ):
                raise DomainActivationPlanAdmissionError(
                    "retirement requires the exact current active or suspended specification"
                )
        else:
            await self._validate_rollback(revision=revision, current=current)

    async def _validate_rollback(
        self,
        *,
        revision: DomainActivationRevisionV1Alpha2,
        current: DomainActivationRevisionV1Alpha2,
    ) -> None:
        target_id = revision.plan.rollback_target_revision_id
        target_digest = revision.plan.rollback_target_revision_digest
        if target_id is None or target_digest is None:
            raise DomainActivationPlanAdmissionError("rollback is missing its exact historical target")
        envelope = await self.store.load_revision(
            target_id,
            product_id=revision.plan.spec.product_id,
        )
        if envelope is None:
            raise DomainActivationPlanAdmissionError("rollback target does not exist in exact activation history")
        target = _parse_persisted_revision(envelope)
        if (
            target.activation_id != current.activation_id
            or target.revision >= current.revision
            or target.state is not ActivationRuntimeState.ACTIVE
            or target.revision_digest != target_digest
            or target.plan.spec != revision.plan.spec
        ):
            raise DomainActivationPlanAdmissionError("rollback target does not match the exact earlier active revision")

    async def admit(
        self,
        revision: DomainActivationRevisionV1Alpha2,
        *,
        pack: CompiledDomainPackV1,
        conformance_receipts: tuple[DomainPackConformanceReceiptV1, ...],
        session: IntelligenceBuilderSessionRevisionV1,
        observations: AuthorizedObservationSetV1,
        intelligence_model: IntelligenceModelProposalV1,
        intelligence_disposition: IntelligenceModelDispositionV1,
        first_briefing: FirstBriefingPreviewV1,
        committed_at: datetime,
    ) -> CommittedDomainActivationPlan:
        validated = _revalidate_revision(revision)
        validated_pack = _revalidate_pack(pack)
        if committed_at.tzinfo is None or committed_at.utcoffset() is None:
            raise DomainActivationPlanAdmissionError("commit time must include a timezone")
        if validated.occurred_at > committed_at:
            raise DomainActivationPlanAdmissionError("commit cannot predate the approved activation transition")

        exact_handoff = prepare_activation_onboarding_handoff(
            session=session,
            observations=observations,
            intelligence_model=intelligence_model,
            intelligence_disposition=intelligence_disposition,
            first_briefing=first_briefing,
        )
        if validated.plan.onboarding_handoff != exact_handoff:
            raise DomainActivationPlanAdmissionError("activation plan does not bind the exact current 0.7D handoff")

        await self._validate_transition(validated)
        _validate_current_activation_material(
            revision=validated,
            pack=validated_pack,
            conformance_receipts=conformance_receipts,
        )

        plan = validated.plan
        approval = await self.authority.resolve_approval(
            receipt_ref=validated.approval_receipt_ref,
            product_id=plan.spec.product_id,
            subject_ref=str(plan.plan_id),
            actor_ref=validated.actor_ref,
            effective_at=validated.occurred_at,
        )
        if (
            approval.receipt_ref != validated.approval_receipt_ref
            or approval.product_id != plan.spec.product_id
            or approval.subject_ref != plan.plan_id
            or approval.actor_ref != validated.actor_ref
            or approval.disposition != validated.approval_disposition
            or approval.approved_at < plan.created_at
            or approval.approved_at > validated.occurred_at
        ):
            raise DomainActivationPlanAdmissionError(
                "approval receipt did not resolve to the exact current activation plan"
            )

        grants = []
        for binding in plan.requested_authorities:
            grant = await self.authority.resolve_grant(
                grant_ref=binding.grant_ref,
                product_id=plan.spec.product_id,
                authority=binding.authority,
                effective_at=validated.occurred_at,
            )
            if (
                grant.grant_ref != binding.grant_ref
                or grant.product_id != plan.spec.product_id
                or grant.authority != binding.authority
                or grant.effective_at != validated.occurred_at
                or (grant.expires_at is not None and grant.expires_at <= validated.occurred_at)
            ):
                raise DomainActivationPlanAdmissionError(
                    f"authority grant {binding.request_id} did not resolve for the exact plan"
                )
            grants.append(grant)

        request = GovernedStateCommitRequestV1(
            revision=_envelope(validated),
            expected_head_revision_id=validated.prior_revision_id,
            actor_ref=validated.actor_ref,
            approval=approval,
            authority_grants=tuple(grants),
            committed_at=committed_at,
        )
        receipt = await self.store.commit(request)
        return _validate_committed_pair(validated, receipt)

    async def reload(
        self,
        *,
        product_id: str,
        activation_key: str,
    ) -> CommittedDomainActivationPlan | None:
        return await _reload_domain_activation_plan(
            store=self.store,
            product_id=product_id,
            activation_key=activation_key,
        )

    async def load_history(
        self,
        *,
        product_id: str,
        activation_key: str,
    ) -> tuple[CommittedDomainActivationPlan, ...]:
        """Read one exact append-only activation chain, newest first.

        Historical commits are lineage only. Loading them neither re-resolves
        current grants nor makes an earlier revision live.
        """

        return await load_domain_activation_plan_history(
            store=self.store,
            product_id=product_id,
            activation_key=activation_key,
        )

    async def resolve_live_for_session(
        self,
        *,
        product_id: str,
        activation_key: str,
        session: IntelligenceBuilderSessionRevisionV1,
    ) -> ActivationRevisionReferenceV1Alpha1 | None:
        """Resolve the exact live activation revision bound to one accepted session."""

        return await resolve_live_activation_revision_for_session(
            store=self.store,
            product_id=product_id,
            activation_key=activation_key,
            session=session,
        )


async def load_domain_activation_plan_history(
    *,
    store: GovernedStateStore,
    product_id: str,
    activation_key: str,
) -> tuple[CommittedDomainActivationPlan, ...]:
    """Read one exact append-only v1alpha2 activation chain, newest first."""

    current = await _reload_domain_activation_plan(
        store=store,
        product_id=product_id,
        activation_key=activation_key,
    )
    if current is None:
        return ()
    history: list[CommittedDomainActivationPlan] = []
    seen: set[str] = set()
    expected = current.revision
    while True:
        revision_id = str(expected.revision_id)
        if revision_id in seen:
            raise DomainActivationPlanAdmissionError("activation history contains a revision cycle")
        if len(history) >= MAX_ACTIVATION_HISTORY_REVISIONS:
            raise DomainActivationPlanAdmissionError("activation history exceeds the bounded read limit")
        seen.add(revision_id)
        receipt = (
            current.commit_receipt
            if not history
            else await store.load_receipt_for_revision(revision_id, product_id=product_id)
        )
        if receipt is None:
            raise DomainActivationPlanAdmissionError("activation history has an incomplete commit chain")
        history.append(_validate_committed_pair(expected, receipt))
        prior_id = expected.prior_revision_id
        if prior_id is None:
            if expected.revision != 1:
                raise DomainActivationPlanAdmissionError("activation history terminated before revision one")
            break
        envelope = await store.load_revision(prior_id, product_id=product_id)
        if envelope is None:
            raise DomainActivationPlanAdmissionError("activation history has an incomplete revision chain")
        prior = _parse_persisted_revision(envelope)
        if (
            prior.activation_id != current.revision.activation_id
            or prior.plan.spec.product_id != product_id
            or prior.plan.spec.activation_key != activation_key
            or prior.revision != expected.revision - 1
            or prior.revision_id != prior_id
        ):
            raise DomainActivationPlanAdmissionError("activation history crossed exact scope or sequence")
        expected = prior
    return tuple(history)


async def _reload_domain_activation_plan(
    *,
    store: GovernedStateStore,
    product_id: str,
    activation_key: str,
) -> CommittedDomainActivationPlan | None:
    activation_id = f"domain_activation:{canonical_hash([product_id, activation_key])[:32]}"
    head = await store.load_head(
        state_kind=DOMAIN_ACTIVATION_PLAN_STATE_KIND,
        product_id=product_id,
        state_id=activation_id,
    )
    if head is None:
        head = await store.load_head(
            state_kind=LEGACY_DOMAIN_ACTIVATION_STATE_KIND,
            product_id=product_id,
            state_id=activation_id,
        )
    if head is None:
        return None
    envelope = await store.load_revision(head.revision_id, product_id=product_id)
    receipt = await store.load_receipt(
        head.commit_receipt_id,
        product_id=product_id,
    )
    if envelope is None or receipt is None:
        raise DomainActivationPlanAdmissionError("persisted activation head has an incomplete commit chain")
    revision = _parse_persisted_revision(envelope)
    if (
        revision.plan.spec.product_id != product_id
        or revision.plan.spec.activation_key != activation_key
        or head.revision_id != revision.revision_id
        or head.commit_receipt_id != receipt.receipt_id
    ):
        raise DomainActivationPlanAdmissionError("persisted activation head crossed exact product or activation scope")
    return _validate_committed_pair(revision, receipt)


def _activation_revision_reference(
    revision: DomainActivationRevisionV1Alpha2,
) -> ActivationRevisionReferenceV1Alpha1:
    return ActivationRevisionReferenceV1Alpha1(
        product_id=revision.plan.spec.product_id,
        activation_key=revision.plan.spec.activation_key,
        activation_id=str(revision.activation_id),
        revision=revision.revision,
        revision_id=str(revision.revision_id),
        revision_digest=str(revision.revision_digest),
    )


async def resolve_live_activation_revision_for_session(
    *,
    store: GovernedStateStore,
    product_id: str,
    activation_key: str,
    session: IntelligenceBuilderSessionRevisionV1,
) -> ActivationRevisionReferenceV1Alpha1 | None:
    """Resolve the exact live activation revision bound to one accepted session.

    This is the durable accepted-session-to-activation-revision association:
    it reuses the existing append-only v1alpha2 activation chain and the
    exact ``onboarding_handoff`` every committed revision already embeds. It
    introduces no second activation, session, or persistence model.

    The caller must already hold the exact ``activation_key`` (never inferred
    from a Pack ID or UI state) and an exactly reloaded ``session`` revision.
    Resolution fails closed to ``None`` — never a guess — when: no activation
    has been committed yet, the current activation is not ``ACTIVE``, or the
    current activation's bound onboarding handoff does not name this exact
    session identity (stale, superseded, or a different session). A crossed
    product scope or an unrevalidatable session raises instead of guessing.
    """

    try:
        exact_session = IntelligenceBuilderSessionRevisionV1.model_validate(session.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationPlanAdmissionError("session failed exact revalidation") from exc
    if exact_session.product_id != product_id:
        raise DomainActivationPlanAdmissionError(
            "session product scope does not match the requested activation product"
        )
    if exact_session.revision_id is None or exact_session.revision_digest is None:
        raise DomainActivationPlanAdmissionError("session is missing its exact durable revision identity")

    current = await _reload_domain_activation_plan(
        store=store,
        product_id=product_id,
        activation_key=activation_key,
    )
    if current is None:
        return None
    revision = current.revision
    if revision.state is not ActivationRuntimeState.ACTIVE:
        return None
    handoff = revision.plan.onboarding_handoff
    if (
        handoff.session_id != exact_session.session_id
        or handoff.session_revision_id != exact_session.revision_id
        or handoff.session_revision_digest != exact_session.revision_digest
    ):
        return None
    return _activation_revision_reference(revision)


__all__ = [
    "CommittedDomainActivationPlan",
    "DomainActivationPlanAdmissionError",
    "DomainActivationPlanAdmissionService",
    "DOMAIN_ACTIVATION_PLAN_STATE_KIND",
    "MAX_ACTIVATION_HISTORY_REVISIONS",
    "activation_commit_reference",
    "load_domain_activation_plan_history",
    "prepare_activation_onboarding_handoff",
    "resolve_live_activation_revision_for_session",
    "validate_activation_commit_reference",
]

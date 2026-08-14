"""Durable invocation-scoped host capabilities for one authorized Intelligence build."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ace.application.domain_activation import (
    CommittedDomainActivation,
    DomainActivationAdmissionService,
    bind_committed_activation,
)
from ace.application.installed_pack_artifacts import InstalledPackArtifactError
from ace.application.intelligence_build_execution import (
    AuthorizedIntelligenceBuild,
    IntelligenceBuildHostServices,
    IntelligenceBuildResourcePagePort,
    IntelligenceBuildStartV1Alpha2,
)
from ace.application.intelligence_build_first_brief import (
    CoreIntelligenceBuildFirstBriefService,
    IntelligenceBuildFirstBriefCognition,
)
from ace.application.intelligence_builder import (
    INTELLIGENCE_BUILDER_RECORD_SPACE,
    ONBOARDING_ARTIFACT_RECORD_KIND,
    IntelligenceBuilderSessionError,
    IntelligenceBuilderSessionService,
)
from ace.application.intelligence_builder_activation import ExactCompiledPackResolver
from ace.application.intelligence_builder_activation_contracts import (
    BUILDER_ACTIVATION_PLAN_ARTIFACT_VERSION,
    BUILDER_ACTIVATION_RECEIPT_ARTIFACT_VERSION,
    BuilderActivationPlanArtifactV1,
    BuilderActivationReceiptArtifactV1,
)
from ace.application.intelligence_builder_contracts import (
    OnboardingArtifactKind,
    OnboardingArtifactReferenceV1,
    OnboardingStage,
)
from ace.application.intelligence_ledger import PreparedIntelligenceLedgerService
from ace.application.prepared_shift_signal import CorePreparedShiftSignalDerivationService
from ace.application.recorded_source_admission import (
    CoreRecordedSourceAdmissionService,
    CoreRecordedSourceAdmissionV1Alpha2Service,
)
from ace.core import CoreAuthorityResolver, ImmutableRecordStore, RuntimeUseResolver
from ace.core.state import GovernedStateStore
from ace.intelligence.contracts.resources import ActivationRevisionReferenceV1Alpha1


class IntelligenceBuildHostCompositionError(RuntimeError):
    """Durable activation/bootstrap material could not compose safe build ports."""


@dataclass(frozen=True, slots=True)
class _BootstrapCandidate:
    plan_reference: OnboardingArtifactReferenceV1
    receipt_reference: OnboardingArtifactReferenceV1
    plan: BuilderActivationPlanArtifactV1
    receipt: BuilderActivationReceiptArtifactV1


def _artifact_reference(
    kind: OnboardingArtifactKind,
    artifact_id: str | None,
    artifact_digest: str | None,
) -> OnboardingArtifactReferenceV1:
    if artifact_id is None or artifact_digest is None:
        raise IntelligenceBuildHostCompositionError("Builder activation artifact is missing exact identity")
    return OnboardingArtifactReferenceV1(
        artifact_kind=kind,
        artifact_id=artifact_id,
        artifact_digest=artifact_digest,
    )


def _record_matches_artifact(record, artifact, *, timestamp: datetime) -> bool:
    return (
        record.record_key == artifact.artifact_id
        and record.payload_contract == artifact.contract
        and record.as_of == timestamp
        and record.available_at == timestamp
    )


class DurableIntelligenceBuildHostComposer:
    """Recover exact Builder activation material and grant only bounded build ports."""

    def __init__(
        self,
        *,
        governed_state: GovernedStateStore,
        runtime_use: RuntimeUseResolver,
        packs: ExactCompiledPackResolver,
        first_brief_cognition: IntelligenceBuildFirstBriefCognition | None = None,
    ) -> None:
        self.governed_state = governed_state
        self.runtime_use = runtime_use
        self.packs = packs
        self.first_brief_cognition = first_brief_cognition

    async def _matching_candidates(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        records: ImmutableRecordStore,
    ) -> tuple[_BootstrapCandidate, ...]:
        evaluated_at = build.authority_use.evaluated_at
        try:
            artifacts = await records.read_as_of(
                product_id=build.product_id,
                record_space=INTELLIGENCE_BUILDER_RECORD_SPACE,
                record_kind=ONBOARDING_ARTIFACT_RECORD_KIND,
                available_at=evaluated_at,
            )
        except Exception:
            raise IntelligenceBuildHostCompositionError(
                "durable Builder activation artifacts are unavailable"
            ) from None

        plans: list[tuple[OnboardingArtifactReferenceV1, BuilderActivationPlanArtifactV1]] = []
        correlated_plan_ids: set[str] = set()
        for record in artifacts:
            if record.payload_contract != BUILDER_ACTIVATION_PLAN_ARTIFACT_VERSION:
                continue
            raw_spec = record.payload.get("spec_id") if isinstance(record.payload, dict) else None
            try:
                plan = BuilderActivationPlanArtifactV1.model_validate(record.payload, strict=False)
            except Exception:
                if raw_spec == build.request.activation_approval_subject_ref:
                    raise IntelligenceBuildHostCompositionError(
                        "correlated Builder activation plan failed exact revalidation"
                    ) from None
                continue
            if plan.spec_id != build.request.activation_approval_subject_ref:
                continue
            if plan.source_commit.product_id != build.product_id or not _record_matches_artifact(
                record,
                plan,
                timestamp=plan.created_at,
            ):
                raise IntelligenceBuildHostCompositionError(
                    "correlated Builder activation plan crossed exact product or persistence material"
                )
            reference = _artifact_reference(
                OnboardingArtifactKind.ACTIVATION_PLAN,
                plan.artifact_id,
                plan.artifact_digest,
            )
            plans.append((reference, plan))
            correlated_plan_ids.add(reference.artifact_id)
        if not plans:
            return ()

        receipts: list[tuple[OnboardingArtifactReferenceV1, BuilderActivationReceiptArtifactV1]] = []
        for record in artifacts:
            if record.payload_contract != BUILDER_ACTIVATION_RECEIPT_ARTIFACT_VERSION:
                continue
            raw_plan_id = (
                record.payload.get("activation_plan_artifact_id") if isinstance(record.payload, dict) else None
            )
            try:
                receipt = BuilderActivationReceiptArtifactV1.model_validate(record.payload, strict=False)
            except Exception:
                if raw_plan_id in correlated_plan_ids:
                    raise IntelligenceBuildHostCompositionError(
                        "correlated Builder activation receipt failed exact revalidation"
                    ) from None
                continue
            if receipt.activation_plan_artifact_id not in correlated_plan_ids:
                continue
            if receipt.canonical_revision.product_id != build.product_id or not _record_matches_artifact(
                record,
                receipt,
                timestamp=receipt.activated_at,
            ):
                raise IntelligenceBuildHostCompositionError(
                    "correlated Builder activation receipt crossed exact product or persistence material"
                )
            receipts.append(
                (
                    _artifact_reference(
                        OnboardingArtifactKind.ACTIVATION_RECEIPT,
                        receipt.artifact_id,
                        receipt.artifact_digest,
                    ),
                    receipt,
                )
            )

        sessions = IntelligenceBuilderSessionService(store=records)
        candidates: list[_BootstrapCandidate] = []
        for plan_reference, plan in plans:
            matching_receipts = [
                (reference, receipt)
                for reference, receipt in receipts
                if receipt.activation_plan_artifact_id == plan_reference.artifact_id
                and receipt.activation_plan_artifact_digest == plan_reference.artifact_digest
                and receipt.source_commit == plan.source_commit
                and receipt.session_id == plan.session_id
            ]
            for receipt_reference, receipt in matching_receipts:
                try:
                    session = await sessions.load_latest(
                        product_id=build.product_id,
                        session_id=receipt.session_id,
                        available_at=evaluated_at,
                    )
                except IntelligenceBuilderSessionError:
                    raise IntelligenceBuildHostCompositionError(
                        "correlated active Builder session failed exact durable replay"
                    ) from None
                if session is None or session.stage is not OnboardingStage.ACTIVE:
                    continue
                if (
                    session.approval_receipt_ref != build.request.activation_approval_receipt_ref
                    or plan_reference not in session.artifacts
                    or receipt_reference not in session.artifacts
                ):
                    raise IntelligenceBuildHostCompositionError(
                        "correlated active Builder session changed approval or activation artifacts"
                    )
                candidates.append(
                    _BootstrapCandidate(
                        plan_reference=plan_reference,
                        receipt_reference=receipt_reference,
                        plan=plan,
                        receipt=receipt,
                    )
                )
        return tuple(candidates)

    async def _binding(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        records: ImmutableRecordStore,
        activation_authority: CoreAuthorityResolver,
    ):
        candidates = await self._matching_candidates(build=build, records=records)
        if not candidates:
            return None
        if len(candidates) != 1:
            raise IntelligenceBuildHostCompositionError(
                "authorized build resolves more than one exact active Builder bootstrap"
            )
        candidate = candidates[0]
        sessions = IntelligenceBuilderSessionService(store=records)
        try:
            plan = await sessions.load_artifact(
                product_id=build.product_id,
                reference=candidate.plan_reference,
                artifact_type=BuilderActivationPlanArtifactV1,
                available_at=build.authority_use.evaluated_at,
            )
            receipt = await sessions.load_artifact(
                product_id=build.product_id,
                reference=candidate.receipt_reference,
                artifact_type=BuilderActivationReceiptArtifactV1,
                available_at=build.authority_use.evaluated_at,
            )
        except IntelligenceBuilderSessionError:
            raise IntelligenceBuildHostCompositionError(
                "authorized Builder bootstrap artifacts failed exact reload"
            ) from None
        if plan != candidate.plan or receipt != candidate.receipt:
            raise IntelligenceBuildHostCompositionError("Builder bootstrap changed during exact reload")

        canonical = DomainActivationAdmissionService(
            store=self.governed_state,
            authority=activation_authority,
        )
        try:
            committed = await canonical.load_exact(
                product_id=build.product_id,
                revision_id=receipt.canonical_revision.revision_id,
                commit_receipt_id=receipt.canonical_commit_receipt_id,
            )
        except Exception:
            raise IntelligenceBuildHostCompositionError(
                "Builder bootstrap canonical activation failed exact durable reload"
            ) from None
        if committed is None:
            return None
        current = await canonical.reload(
            product_id=build.product_id,
            activation_key=receipt.canonical_revision.activation_key,
        )
        if current is None or current != committed:
            return None
        revision = committed.revision
        canonical_reference = ActivationRevisionReferenceV1Alpha1(
            product_id=build.product_id,
            activation_key=revision.spec.activation_key,
            activation_id=str(revision.activation_id),
            revision=revision.revision,
            revision_id=str(revision.revision_id),
            revision_digest=f"sha256:{revision.revision_hash}",
        )
        if (
            receipt.canonical_revision != canonical_reference
            or receipt.canonical_state_kind != committed.commit_receipt.state_kind
            or receipt.canonical_commit_receipt_digest != f"sha256:{committed.commit_receipt.receipt_hash}"
            or committed.commit_receipt.approval != build.activation_approval
            or committed.commit_receipt.actor_ref != build.actor_ref
            or revision.spec.spec_id != build.request.activation_approval_subject_ref
            or revision.spec.pack != plan.pack
        ):
            raise IntelligenceBuildHostCompositionError(
                "authorized build approval, plan, receipt, and canonical activation do not exactly agree"
            )
        try:
            pack = await self.packs.load_exact(reference=plan.pack)
        except InstalledPackArtifactError:
            raise IntelligenceBuildHostCompositionError("installed Pack artifact failed exact resolution") from None
        if pack is None:
            return None
        try:
            return bind_committed_activation(
                pack=pack,
                committed=CommittedDomainActivation(
                    revision=revision,
                    commit_receipt=committed.commit_receipt,
                ),
            )
        except Exception:
            raise IntelligenceBuildHostCompositionError(
                "installed Pack and canonical activation failed exact binding"
            ) from None

    async def compose(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        records: ImmutableRecordStore,
        resources: IntelligenceBuildResourcePagePort,
        activation_authority: CoreAuthorityResolver,
    ) -> IntelligenceBuildHostServices:
        """Create per-invocation ports, or keep both unavailable without exact bootstrap."""

        binding = await self._binding(
            build=build,
            records=records,
            activation_authority=activation_authority,
        )
        if binding is None:
            return IntelligenceBuildHostServices(
                records=records,
                resources=resources,
                activation_authority=activation_authority,
            )
        canonical = DomainActivationAdmissionService(
            store=self.governed_state,
            authority=activation_authority,
        )
        return IntelligenceBuildHostServices(
            records=records,
            resources=resources,
            activation_authority=activation_authority,
            recorded_sources=(
                CoreRecordedSourceAdmissionV1Alpha2Service(
                    build=build,
                    binding=binding,
                    store=records,
                )
                if isinstance(build.request, IntelligenceBuildStartV1Alpha2)
                else CoreRecordedSourceAdmissionService(
                    build=build,
                    binding=binding,
                    store=records,
                )
            ),
            prepared_derivations=CorePreparedShiftSignalDerivationService(
                build=build,
                binding=binding,
                ledger=PreparedIntelligenceLedgerService(binding=binding, store=records),
                governed_state=self.governed_state,
                runtime_use=self.runtime_use,
            ),
            first_brief=(
                CoreIntelligenceBuildFirstBriefService(
                    build=build,
                    sessions=IntelligenceBuilderSessionService(store=records),
                    activations=canonical,
                    packs=self.packs,
                    records=records,
                    runtime_use=self.runtime_use,
                    cognition=self.first_brief_cognition,
                )
                if self.first_brief_cognition is not None
                else None
            ),
        )


__all__ = [
    "DurableIntelligenceBuildHostComposer",
    "IntelligenceBuildHostCompositionError",
]

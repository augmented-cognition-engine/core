"""Durable invocation-scoped host capabilities for one authorized Intelligence build."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ace.application.domain_activation import (
    CommittedActivationBinding,
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
    IntelligenceBuilderSessionRevisionV1,
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
from ace.core.state import GovernedStateStore, ResolvedApprovalReceiptV1
from ace.intelligence.contracts.resources import ActivationRevisionReferenceV1Alpha1


class IntelligenceBuildHostCompositionError(RuntimeError):
    """Durable activation/bootstrap material could not compose safe build ports."""


class IntelligenceBuildFirstBriefCognitionPort(Protocol):
    """Compose the governed first-Brief cognition for one exact authorized build.

    The reasoning-execution and append bindings are product-scoped and resolved
    from *current* governed-state heads, so composition happens per authorized
    build rather than once at host start. Implementations must fail closed with
    a specific error naming the missing provider, configuration, head, grant,
    or capability; they never fabricate readiness.
    """

    async def compose_first_brief_cognition(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        records: ImmutableRecordStore,
    ) -> IntelligenceBuildFirstBriefCognition: ...


@dataclass(frozen=True, slots=True)
class _BootstrapCandidate:
    plan_reference: OnboardingArtifactReferenceV1
    receipt_reference: OnboardingArtifactReferenceV1
    plan: BuilderActivationPlanArtifactV1
    receipt: BuilderActivationReceiptArtifactV1
    session: IntelligenceBuilderSessionRevisionV1


@dataclass(frozen=True, slots=True)
class _ResolvedBootstrap:
    binding: CommittedActivationBinding
    session: IntelligenceBuilderSessionRevisionV1


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
        first_brief_cognition_resolver: IntelligenceBuildFirstBriefCognitionPort | None = None,
    ) -> None:
        if first_brief_cognition is not None and first_brief_cognition_resolver is not None:
            raise IntelligenceBuildHostCompositionError(
                "host composer cannot configure both first_brief_cognition and first_brief_cognition_resolver"
            )
        self.governed_state = governed_state
        self.runtime_use = runtime_use
        self.packs = packs
        self.first_brief_cognition = first_brief_cognition
        self.first_brief_cognition_resolver = first_brief_cognition_resolver

    async def _matching_candidates(
        self,
        *,
        product_id: str,
        activation_approval_subject_ref: str,
        activation_approval_receipt_ref: str,
        evaluated_at: datetime,
        records: ImmutableRecordStore,
    ) -> tuple[_BootstrapCandidate, ...]:
        try:
            artifacts = await records.read_as_of(
                product_id=product_id,
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
                if raw_spec == activation_approval_subject_ref:
                    raise IntelligenceBuildHostCompositionError(
                        "correlated Builder activation plan failed exact revalidation"
                    ) from None
                continue
            if plan.spec_id != activation_approval_subject_ref:
                continue
            if plan.source_commit.product_id != product_id or not _record_matches_artifact(
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
            if receipt.canonical_revision.product_id != product_id or not _record_matches_artifact(
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
                        product_id=product_id,
                        session_id=receipt.session_id,
                        available_at=evaluated_at,
                    )
                    if session is not None:
                        await sessions.reload_admission(session)
                except IntelligenceBuilderSessionError:
                    raise IntelligenceBuildHostCompositionError(
                        "correlated active Builder session failed exact durable replay"
                    ) from None
                if session is None or session.stage is not OnboardingStage.ACTIVE:
                    continue
                if (
                    session.approval_receipt_ref != activation_approval_receipt_ref
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
                        session=session,
                    )
                )
        return tuple(candidates)

    async def _bootstrap(
        self,
        *,
        product_id: str,
        actor_ref: str,
        evaluated_at: datetime,
        activation_approval_subject_ref: str,
        activation_approval_receipt_ref: str,
        activation_approval: ResolvedApprovalReceiptV1,
        records: ImmutableRecordStore,
        activation_authority: CoreAuthorityResolver,
    ) -> _ResolvedBootstrap | None:
        candidates = await self._matching_candidates(
            product_id=product_id,
            activation_approval_subject_ref=activation_approval_subject_ref,
            activation_approval_receipt_ref=activation_approval_receipt_ref,
            evaluated_at=evaluated_at,
            records=records,
        )
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
                product_id=product_id,
                reference=candidate.plan_reference,
                artifact_type=BuilderActivationPlanArtifactV1,
                available_at=evaluated_at,
            )
            receipt = await sessions.load_artifact(
                product_id=product_id,
                reference=candidate.receipt_reference,
                artifact_type=BuilderActivationReceiptArtifactV1,
                available_at=evaluated_at,
            )
            session = await sessions.load_latest(
                product_id=product_id,
                session_id=candidate.session.session_id,
                available_at=evaluated_at,
            )
            if session is not None:
                await sessions.reload_admission(session)
        except IntelligenceBuilderSessionError:
            raise IntelligenceBuildHostCompositionError(
                "authorized Builder bootstrap artifacts failed exact reload"
            ) from None
        if plan != candidate.plan or receipt != candidate.receipt or session != candidate.session:
            raise IntelligenceBuildHostCompositionError("Builder bootstrap changed during exact reload")

        canonical = DomainActivationAdmissionService(
            store=self.governed_state,
            authority=activation_authority,
        )
        try:
            committed = await canonical.load_exact(
                product_id=product_id,
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
            product_id=product_id,
            activation_key=receipt.canonical_revision.activation_key,
        )
        if current is None or current != committed:
            return None
        revision = committed.revision
        canonical_reference = ActivationRevisionReferenceV1Alpha1(
            product_id=product_id,
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
            or committed.commit_receipt.approval != activation_approval
            or committed.commit_receipt.actor_ref != actor_ref
            or revision.spec.spec_id != activation_approval_subject_ref
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
            binding = bind_committed_activation(
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
        return _ResolvedBootstrap(binding=binding, session=candidate.session)

    async def resolve_active_binding(
        self,
        *,
        product_id: str,
        actor_ref: str,
        evaluated_at: datetime,
        activation_approval_subject_ref: str,
        activation_approval_receipt_ref: str,
        activation_approval: ResolvedApprovalReceiptV1,
        records: ImmutableRecordStore,
        activation_authority: CoreAuthorityResolver,
    ) -> CommittedActivationBinding | None:
        """Independently prove and resolve the exact active canonical activation binding.

        This is the same durable Builder-artifact bootstrap ``compose`` uses to
        grant build execution ports, exposed for read-only callers that need to
        prove the current accepted activation without spending a build
        authority use. It introduces no second association: exactly one
        durable, currently ``ACTIVE`` Builder session's activation plan and
        receipt artifacts must exist for ``activation_approval_subject_ref``;
        their referenced canonical activation revision must independently
        reload to a current, matching head; and the receipt, the caller's
        independently resolved ``activation_approval``, and ``actor_ref`` must
        all exactly agree. Anything less returns ``None`` rather than a guess;
        ambiguous or corrupt durable material still raises
        ``IntelligenceBuildHostCompositionError``.
        """

        bootstrap = await self._bootstrap(
            product_id=product_id,
            actor_ref=actor_ref,
            evaluated_at=evaluated_at,
            activation_approval_subject_ref=activation_approval_subject_ref,
            activation_approval_receipt_ref=activation_approval_receipt_ref,
            activation_approval=activation_approval,
            records=records,
            activation_authority=activation_authority,
        )
        return None if bootstrap is None else bootstrap.binding

    async def compose(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        records: ImmutableRecordStore,
        resources: IntelligenceBuildResourcePagePort,
        activation_authority: CoreAuthorityResolver,
    ) -> IntelligenceBuildHostServices:
        """Create per-invocation ports, or keep both unavailable without exact bootstrap."""

        bootstrap = await self._bootstrap(
            product_id=build.product_id,
            actor_ref=build.actor_ref,
            evaluated_at=build.authority_use.evaluated_at,
            activation_approval_subject_ref=build.request.activation_approval_subject_ref,
            activation_approval_receipt_ref=build.request.activation_approval_receipt_ref,
            activation_approval=build.activation_approval,
            records=records,
            activation_authority=activation_authority,
        )
        if bootstrap is None:
            return IntelligenceBuildHostServices(
                records=records,
                resources=resources,
                activation_authority=activation_authority,
            )
        binding = bootstrap.binding
        canonical = DomainActivationAdmissionService(
            store=self.governed_state,
            authority=activation_authority,
        )
        cognition: IntelligenceBuildFirstBriefCognition | None = None
        if self.first_brief_cognition is not None:
            cognition = self.first_brief_cognition
        elif self.first_brief_cognition_resolver is not None:
            # Same per-build, current-head contract as above; a resolver failure
            # (IntelligenceBuildCognitionUnavailable or otherwise) is deliberately
            # not caught here so it propagates and fails the build response closed.
            cognition = await self.first_brief_cognition_resolver.compose_first_brief_cognition(
                build=build,
                records=records,
            )
            if cognition is None:
                raise IntelligenceBuildHostCompositionError(
                    "first-Brief cognition resolver returned no governed bindings"
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
                    cognition=cognition,
                    active_session=bootstrap.session,
                )
                if cognition is not None
                else None
            ),
        )


__all__ = [
    "DurableIntelligenceBuildHostComposer",
    "IntelligenceBuildFirstBriefCognitionPort",
    "IntelligenceBuildHostCompositionError",
]

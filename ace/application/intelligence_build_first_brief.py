"""Canonical first-Brief composition for one authorized Intelligence build."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.application.brief_synthesis import (
    BriefSynthesisError,
    BriefSynthesisService,
    PreparedBriefAppendAdmission,
)
from ace.application.domain_activation import (
    CommittedActivationBinding,
    DomainActivationAdmissionService,
    bind_committed_activation,
)
from ace.application.intelligence_build_execution import (
    AuthorizedIntelligenceBuild,
    IntelligenceBuildFirstBriefPort,
)
from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_activation import ExactCompiledPackResolver
from ace.application.intelligence_builder_activation_contracts import (
    BuilderActivationPlanArtifactV1,
    BuilderActivationReceiptArtifactV1,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingArtifactKind,
    OnboardingStage,
)
from ace.application.intelligence_ledger import PreparedIntelligenceLedgerService
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.reasoning import (
    GovernedOperationBindingV1Alpha1,
    GovernedReasoningService,
    ReasoningExecutionBindingV1Alpha1,
)
from ace.core.records import ImmutableRecordStore
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1, RuntimeUseResolver
from ace.intelligence.contracts.common import validate_digest, validate_reference
from ace.intelligence.contracts.ledger import AttentionDisposition, resource_reference
from ace.intelligence.contracts.resources import SignalV1Alpha1
from ace.intelligence.contracts.synthesis import BriefSynthesisRequestV1Alpha1
from ace.intelligence.packs.runtime import (
    PreparedActivationBindingError,
    resolve_brief_synthesis_policy,
)

INTELLIGENCE_BUILD_FIRST_BRIEF_REQUEST_VERSION = "ace.application.intelligence-build-first-brief-request/v1alpha1"
INTELLIGENCE_BUILD_FIRST_BRIEF_REQUEST_V1ALPHA2_VERSION = (
    "ace.application.intelligence-build-first-brief-request/v1alpha2"
)
CREATE_FIRST_BRIEF_EFFECT = "create_first_brief"
INTELLIGENCE_BUILD_OPERATION = "start_intelligence_build"
INTELLIGENCE_BUILD_AUTHORITY = "intelligence_build"


class IntelligenceBuildFirstBriefError(RuntimeError):
    """The canonical first Brief could not be safely synthesized or replayed."""


class IntelligenceBuildFirstBriefRequestV1Alpha1(FrozenContract):
    """Exact durable Builder and routed-derivation coordinates selected for synthesis."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )

    contract: Literal["ace.application.intelligence-build-first-brief-request/v1alpha1"] = (
        INTELLIGENCE_BUILD_FIRST_BRIEF_REQUEST_VERSION
    )
    session_id: str
    session_revision_id: str
    session_revision_digest: str
    derivation_key: str
    attention_receipt_id: str
    attention_receipt_digest: str
    requested_at: datetime
    request_id: str | None = Field(default=None, max_length=240)
    request_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator(
        "session_id",
        "session_revision_id",
        "derivation_key",
        "attention_receipt_id",
        "request_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("session_revision_digest", "attention_receipt_digest", "request_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"request_id", "request_digest"})
        digest = canonical_hash(material)
        expected_id = f"intelligence_build_first_brief:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.request_id is not None and self.request_id != expected_id:
            raise ValueError("request_id does not match exact first-Brief selection")
        if self.request_digest is not None and self.request_digest != expected_digest:
            raise ValueError("request_digest does not match exact first-Brief selection")
        object.__setattr__(self, "request_id", expected_id)
        object.__setattr__(self, "request_digest", expected_digest)
        return self


class IntelligenceBuildFirstBriefRequestV1Alpha2(FrozenContract):
    """Build-bound routed material; Core owns the exact active session."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )

    contract: Literal["ace.application.intelligence-build-first-brief-request/v1alpha2"] = (
        INTELLIGENCE_BUILD_FIRST_BRIEF_REQUEST_V1ALPHA2_VERSION
    )
    build_id: str
    build_request_digest: str
    derivation_key: str
    attention_receipt_id: str
    attention_receipt_digest: str
    requested_at: datetime
    request_id: str | None = Field(default=None, max_length=240)
    request_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("build_id", "derivation_key", "attention_receipt_id", "request_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("build_request_digest", "attention_receipt_digest", "request_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        material = self.model_dump(mode="json", exclude={"request_id", "request_digest"})
        digest = canonical_hash(material)
        expected_id = f"intelligence_build_first_brief:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.request_id is not None and self.request_id != expected_id:
            raise ValueError("request_id does not match exact first-Brief selection")
        if self.request_digest is not None and self.request_digest != expected_digest:
            raise ValueError("request_digest does not match exact first-Brief selection")
        object.__setattr__(self, "request_id", expected_id)
        object.__setattr__(self, "request_digest", expected_digest)
        return self


@dataclass(frozen=True, slots=True)
class IntelligenceBuildFirstBriefCognition:
    """Existing governed cognition and append bindings selected by the Core host."""

    reasoning: GovernedReasoningService
    execution_binding: ReasoningExecutionBindingV1Alpha1
    append_binding: GovernedOperationBindingV1Alpha1


@dataclass(frozen=True, slots=True)
class IntelligenceBuildFirstBriefOutcome:
    request: IntelligenceBuildFirstBriefRequestV1Alpha1 | IntelligenceBuildFirstBriefRequestV1Alpha2
    session: IntelligenceBuilderSessionRevisionV1
    binding: CommittedActivationBinding
    admission: PreparedBriefAppendAdmission

    @property
    def replayed(self) -> bool:
        return self.admission.replayed


class CoreIntelligenceBuildFirstBriefService(IntelligenceBuildFirstBriefPort):
    """Resolve durable Builder policy and delegate one canonical synthesis route."""

    def __init__(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        sessions: IntelligenceBuilderSessionService,
        activations: DomainActivationAdmissionService,
        packs: ExactCompiledPackResolver,
        records: ImmutableRecordStore,
        runtime_use: RuntimeUseResolver,
        cognition: IntelligenceBuildFirstBriefCognition | None,
        active_session: IntelligenceBuilderSessionRevisionV1,
    ) -> None:
        self.build = build
        self.sessions = sessions
        self.activations = activations
        self.packs = packs
        self.records = records
        self.runtime_use = runtime_use
        self.cognition = self._validate_cognition(cognition)
        self._validate_build()
        self.active_session = self._validate_active_session(active_session)

    def _validate_build(self) -> None:
        authority = self.build.authority_use
        if (
            authority.product_id != self.build.product_id
            or authority.actor_ref != self.build.actor_ref
            or authority.use_subject_ref != self.build.build_id
            or authority.use_subject_digest != self.build.request_digest
            or authority.operation != INTELLIGENCE_BUILD_OPERATION
            or authority.authority != INTELLIGENCE_BUILD_AUTHORITY
            or authority.grant_ref != self.build.request.authority_grant_ref
            or CREATE_FIRST_BRIEF_EFFECT not in self.build.request.approved_effects
        ):
            raise IntelligenceBuildFirstBriefError("authorized build does not cover the exact first-Brief operation")

    def _validate_active_session(
        self,
        session: IntelligenceBuilderSessionRevisionV1,
    ) -> IntelligenceBuilderSessionRevisionV1:
        try:
            exact = IntelligenceBuilderSessionRevisionV1.model_validate(session.model_dump(mode="python"))
        except Exception:
            raise IntelligenceBuildFirstBriefError("Core-resolved active Builder session is invalid") from None
        artifact_kinds = tuple(item.artifact_kind for item in exact.artifacts)
        if (
            exact.product_id != self.build.product_id
            or exact.stage is not OnboardingStage.ACTIVE
            or exact.transition_actor_ref != self.build.actor_ref
            or exact.approval_receipt_ref != self.build.request.activation_approval_receipt_ref
            or exact.occurred_at > self.build.authority_use.evaluated_at
            or artifact_kinds.count(OnboardingArtifactKind.ACTIVATION_PLAN) != 1
            or artifact_kinds.count(OnboardingArtifactKind.ACTIVATION_RECEIPT) != 1
        ):
            raise IntelligenceBuildFirstBriefError("Core-resolved active Builder session crossed the authorized build")
        return exact

    def _validate_cognition(
        self,
        cognition: IntelligenceBuildFirstBriefCognition | None,
    ) -> IntelligenceBuildFirstBriefCognition | None:
        if cognition is None:
            return None
        try:
            execution = ReasoningExecutionBindingV1Alpha1.model_validate(
                cognition.execution_binding.model_dump(mode="python")
            )
            append = GovernedOperationBindingV1Alpha1.model_validate(cognition.append_binding.model_dump(mode="python"))
        except Exception:
            raise IntelligenceBuildFirstBriefError("host cognition bindings failed exact revalidation") from None
        if execution.product_id != self.build.product_id or append.product_id != self.build.product_id:
            raise IntelligenceBuildFirstBriefError("host cognition bindings crossed authorized product scope")
        return IntelligenceBuildFirstBriefCognition(
            reasoning=cognition.reasoning,
            execution_binding=execution,
            append_binding=append,
        )

    async def _resolve_current_build_authority(
        self,
        request: IntelligenceBuildFirstBriefRequestV1Alpha2,
    ) -> AuthorityUseReceiptV1Alpha1:
        original = self.build.authority_use
        try:
            fresh = AuthorityUseReceiptV1Alpha1.model_validate(
                (
                    await self.runtime_use.resolve_authority_use(
                        context=original.authenticated_context,
                        use_subject_ref=self.build.build_id,
                        use_subject_digest=self.build.request_digest,
                        operation=INTELLIGENCE_BUILD_OPERATION,
                        authority=INTELLIGENCE_BUILD_AUTHORITY,
                        grant_ref=self.build.request.authority_grant_ref,
                        evaluated_at=request.requested_at,
                    )
                ).model_dump(mode="python")
            )
        except Exception:
            raise IntelligenceBuildFirstBriefError("current build authority denied first-Brief synthesis") from None
        if (
            fresh.product_id != self.build.product_id
            or fresh.actor_ref != self.build.actor_ref
            or fresh.authenticated_context != original.authenticated_context
            or fresh.use_subject_ref != self.build.build_id
            or fresh.use_subject_digest != self.build.request_digest
            or fresh.operation != original.operation
            or fresh.authority != original.authority
            or fresh.grant_ref != original.grant_ref
            or fresh.grant_hash != original.grant_hash
            or fresh.state_head_precondition != original.state_head_precondition
            or fresh.evaluated_at != request.requested_at
        ):
            raise IntelligenceBuildFirstBriefError("current build authority changed exact authorized material")
        return fresh

    async def _load_current_session(
        self,
        request: IntelligenceBuildFirstBriefRequestV1Alpha2,
    ) -> IntelligenceBuilderSessionRevisionV1:
        try:
            session = await self.sessions.load_latest(
                product_id=self.build.product_id,
                session_id=self.active_session.session_id,
                available_at=request.requested_at,
            )
            if session is None:
                raise IntelligenceBuildFirstBriefError("current Builder session is missing")
            await self.sessions.reload_admission(session)
        except IntelligenceBuildFirstBriefError:
            raise
        except Exception:
            raise IntelligenceBuildFirstBriefError("current Builder session failed exact durable reload") from None
        if session != self.active_session or session.occurred_at > request.requested_at:
            raise IntelligenceBuildFirstBriefError("first Brief requires the exact current active Builder revision")
        if session.approval_receipt_ref != self.build.request.activation_approval_receipt_ref:
            raise IntelligenceBuildFirstBriefError("active Builder revision crossed the reviewed activation approval")
        return session

    @staticmethod
    def _one_artifact(session: IntelligenceBuilderSessionRevisionV1, kind: OnboardingArtifactKind):
        matches = [item for item in session.artifacts if item.artifact_kind is kind]
        if len(matches) != 1:
            raise IntelligenceBuildFirstBriefError(f"active Builder revision must bind one exact {kind.value} artifact")
        return matches[0]

    async def _load_binding(
        self,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        available_at: datetime,
    ) -> CommittedActivationBinding:
        plan_ref = self._one_artifact(session, OnboardingArtifactKind.ACTIVATION_PLAN)
        receipt_ref = self._one_artifact(session, OnboardingArtifactKind.ACTIVATION_RECEIPT)
        try:
            plan = await self.sessions.load_artifact(
                product_id=self.build.product_id,
                reference=plan_ref,
                artifact_type=BuilderActivationPlanArtifactV1,
                available_at=available_at,
            )
            receipt = await self.sessions.load_artifact(
                product_id=self.build.product_id,
                reference=receipt_ref,
                artifact_type=BuilderActivationReceiptArtifactV1,
                available_at=available_at,
            )
            pack = await self.packs.load_exact(reference=plan.pack)
            committed = await self.activations.reload(
                product_id=self.build.product_id,
                activation_key=receipt.canonical_revision.activation_key,
            )
            if pack is None or committed is None:
                raise IntelligenceBuildFirstBriefError("exact active Pack or canonical activation is unavailable")
            binding = bind_committed_activation(pack=pack, committed=committed)
        except IntelligenceBuildFirstBriefError:
            raise
        except Exception:
            raise IntelligenceBuildFirstBriefError("active Builder Pack and activation failed exact reload") from None
        commit = binding.commit_receipt
        specification = binding.prepared_binding.revision.spec
        if (
            plan.session_id != session.session_id
            or receipt.session_id != session.session_id
            or receipt.activation_plan_artifact_id != plan.artifact_id
            or receipt.activation_plan_artifact_digest != plan.artifact_digest
            or receipt.source_commit != plan.source_commit
            or receipt.canonical_revision != binding.prepared_binding.reference
            or receipt.canonical_state_kind != commit.state_kind
            or receipt.canonical_commit_receipt_id != commit.receipt_id
            or receipt.canonical_commit_receipt_digest != f"sha256:{commit.receipt_hash}"
            or plan.spec_id != specification.spec_id
            or plan.spec_digest != f"sha256:{specification.spec_hash}"
            or plan.pack != specification.pack
            or receipt.activated_at != commit.committed_at
            or receipt.activated_at > available_at
            or commit.approval != self.build.activation_approval
            or str(commit.approval.receipt_ref) != self.build.request.activation_approval_receipt_ref
            or commit.approval.subject_ref != specification.spec_id
            or commit.approval.subject_ref != self.build.request.activation_approval_subject_ref
            or str(commit.approval.receipt_ref) != session.approval_receipt_ref
        ):
            raise IntelligenceBuildFirstBriefError("active Builder artifacts crossed exact canonical material")
        return binding

    async def create_first_brief(
        self,
        request: IntelligenceBuildFirstBriefRequestV1Alpha2,
    ) -> IntelligenceBuildFirstBriefOutcome:
        try:
            exact = IntelligenceBuildFirstBriefRequestV1Alpha2.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise IntelligenceBuildFirstBriefError("first-Brief request failed exact revalidation") from exc
        if exact.build_id != self.build.build_id or exact.build_request_digest != self.build.request_digest:
            raise IntelligenceBuildFirstBriefError("first-Brief request crossed the authorized build")
        session = await self._load_current_session(exact)
        await self._resolve_current_build_authority(exact)
        binding = await self._load_binding(session=session, available_at=exact.requested_at)
        if self.cognition is None:
            raise IntelligenceBuildFirstBriefError(
                "governed first-Brief cognition and append composition is not installed"
            )
        ledger = PreparedIntelligenceLedgerService(binding=binding, store=self.records)
        try:
            derivation = await ledger.replay(derivation_key=exact.derivation_key)
            if derivation is None:
                raise IntelligenceBuildFirstBriefError("exact routed PREPARED derivation is missing")
            attention = derivation.attention_receipt
            if (
                attention.receipt_id != exact.attention_receipt_id
                or attention.receipt_digest != exact.attention_receipt_digest
                or attention.disposition is not AttentionDisposition.ROUTE
                or attention.brief_template_id is None
                or not attention.persona_ids
                or attention.activation_revision != binding.prepared_binding.reference
                or attention.pack != binding.prepared_binding.revision.spec.pack
                or attention.evaluated_at > exact.requested_at
            ):
                raise IntelligenceBuildFirstBriefError(
                    "first Brief requires one exact current routed attention receipt"
                )
            signals = [item for item in derivation.resources if isinstance(item, SignalV1Alpha1)]
            if len(signals) != 1 or attention.signal != resource_reference(signals[0]):
                raise IntelligenceBuildFirstBriefError("routed derivation does not bind one exact Signal")
            resolve_brief_synthesis_policy(
                binding.prepared_binding,
                template_id=attention.brief_template_id,
                persona_ids=attention.persona_ids,
            )
        except IntelligenceBuildFirstBriefError:
            raise
        except PreparedActivationBindingError:
            raise IntelligenceBuildFirstBriefError(
                "routed template, personas, or Pack policy failed exact resolution"
            ) from None
        except Exception:
            raise IntelligenceBuildFirstBriefError("routed PREPARED material failed exact replay") from None
        synthesis_material = {
            "build_id": self.build.build_id,
            "request_id": exact.request_id,
            "session_revision_id": session.revision_id,
            "derivation_key": exact.derivation_key,
            "attention_receipt_id": exact.attention_receipt_id,
            "activation_revision_id": binding.prepared_binding.reference.revision_id,
            "pack_digest": binding.prepared_binding.revision.spec.pack.pack_digest,
        }
        identity = canonical_hash(synthesis_material)
        synthesis_request = BriefSynthesisRequestV1Alpha1(
            synthesis_key=f"first_brief_synthesis:{identity[:32]}",
            reasoning_attempt_key=f"first_brief_reasoning:{identity[:32]}",
            derivation_key=exact.derivation_key,
            product_id=self.build.product_id,
            authenticated_context=self.build.authority_use.authenticated_context,
            activation_revision=binding.prepared_binding.reference,
            pack=binding.prepared_binding.revision.spec.pack,
            attention_receipt_id=exact.attention_receipt_id,
            attention_receipt_digest=exact.attention_receipt_digest,
            brief_as_of=attention.evaluated_at,
            context_cutoff_at=attention.evaluated_at,
            requested_at=exact.requested_at,
        )
        service = BriefSynthesisService(
            activation_service=self.activations,
            pack=binding.prepared_binding.pack,
            pack_resolver=self.packs,
            store=self.records,
            reasoning=self.cognition.reasoning,
            execution_binding=self.cognition.execution_binding,
            append_binding=self.cognition.append_binding,
            clock=lambda: exact.requested_at,
        )
        try:
            admission = await service.synthesize(
                synthesis_request,
                delivery_context=self.build.authority_use.authenticated_context,
            )
        except BriefSynthesisError as exc:
            raise IntelligenceBuildFirstBriefError("canonical first-Brief synthesis failed closed") from exc
        return IntelligenceBuildFirstBriefOutcome(
            request=exact,
            session=session,
            binding=binding,
            admission=admission,
        )


__all__ = [
    "CREATE_FIRST_BRIEF_EFFECT",
    "CoreIntelligenceBuildFirstBriefService",
    "INTELLIGENCE_BUILD_FIRST_BRIEF_REQUEST_V1ALPHA2_VERSION",
    "INTELLIGENCE_BUILD_FIRST_BRIEF_REQUEST_VERSION",
    "IntelligenceBuildFirstBriefCognition",
    "IntelligenceBuildFirstBriefError",
    "IntelligenceBuildFirstBriefOutcome",
    "IntelligenceBuildFirstBriefRequestV1Alpha1",
    "IntelligenceBuildFirstBriefRequestV1Alpha2",
]

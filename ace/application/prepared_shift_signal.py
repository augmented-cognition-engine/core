"""Governed PREPARED Entity-to-Shift-to-Signal derivation for one Intelligence build."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.application.domain_activation import (
    CommittedActivationBinding,
    CommittedDomainActivation,
    bind_committed_activation,
)
from ace.application.intelligence_build_execution import (
    AuthorizedIntelligenceBuild,
    IntelligenceBuildPreparedDerivationPort,
)
from ace.application.intelligence_ledger import (
    PreparedIntelligenceAdmission,
    PreparedIntelligenceAdmissionError,
    PreparedIntelligenceLedgerService,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1, RuntimeUseResolver
from ace.core.state import (
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateStore,
)
from ace.intelligence.contracts.common import validate_reference, validate_slug
from ace.intelligence.contracts.detection import (
    CategoricalTransitionRuleV1,
    ContentRevisionRuleV1,
    NumericDeltaRuleV1,
)
from ace.intelligence.contracts.ledger import (
    IntelligenceRecordKind,
    IntelligenceRecordReferenceV1Alpha1,
    PreparedDerivedResourceAdmissionV1Alpha1,
    deterministic_resource_order,
    resource_reference,
)
from ace.intelligence.contracts.resources import (
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)
from ace.intelligence.detection import (
    CategoricalTransitionDetectionError,
    ContentRevisionDetectionError,
    NumericDeltaDetectionError,
    detect_categorical_shift,
    detect_content_revision_shift,
    detect_numeric_shift,
    route_categorical_shift_as_signal,
    route_content_revision_shift_as_signal,
    route_shift_as_signal,
)
from ace.intelligence.packs.runtime import (
    PreparedActivationBindingError,
    resolve_detector_rule,
)

PREPARED_SHIFT_SIGNAL_DERIVATION_REQUEST_VERSION = "ace.application.prepared-shift-signal-derivation-request/v1alpha1"
ACTIVATE_WATCH_EFFECT = "activate_watch"
INTELLIGENCE_BUILD_OPERATION = "start_intelligence_build"
INTELLIGENCE_BUILD_AUTHORITY = "intelligence_build"


class PreparedShiftSignalDerivationError(RuntimeError):
    """The exact PREPARED selection could not be safely derived or replayed."""


class PreparedShiftSignalDerivationRequestV1Alpha1(FrozenContract):
    """Exact stored Entity pair and declared Pack detector selected for one derivation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )

    contract: Literal["ace.application.prepared-shift-signal-derivation-request/v1alpha1"] = (
        PREPARED_SHIFT_SIGNAL_DERIVATION_REQUEST_VERSION
    )
    derivation_key: str
    detector_id: str
    baseline_snapshot: IntelligenceRecordReferenceV1Alpha1
    current_snapshot: IntelligenceRecordReferenceV1Alpha1
    evaluated_at: datetime
    request_id: str | None = Field(default=None, max_length=240)
    request_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("derivation_key", "request_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("detector_id")
    @classmethod
    def validate_detector_id(cls, value: str) -> str:
        return validate_slug(value, name="detector_id")

    @field_validator("evaluated_at")
    @classmethod
    def normalize_evaluated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_selection_and_identity(self) -> Self:
        snapshots = (self.baseline_snapshot, self.current_snapshot)
        if any(
            item.mode is not IntelligenceResourceMode.PREPARED
            or item.resource_kind is not IntelligenceRecordKind.ENTITY_SNAPSHOT
            for item in snapshots
        ):
            raise ValueError("derivation requires exact PREPARED Entity Snapshot references")
        if self.baseline_snapshot.product_id != self.current_snapshot.product_id:
            raise ValueError("derivation Entity Snapshots crossed product scope")
        if self.baseline_snapshot.resource_id == self.current_snapshot.resource_id:
            raise ValueError("derivation baseline and current snapshots must be distinct")
        if self.baseline_snapshot.as_of >= self.current_snapshot.as_of:
            raise ValueError("derivation baseline must precede current snapshot")
        if any(item.available_at > self.evaluated_at for item in snapshots):
            raise ValueError("derivation cannot evaluate unavailable Entity Snapshots")
        material = self.model_dump(mode="json", exclude={"request_id", "request_digest"})
        digest = canonical_hash(material)
        expected_id = f"prepared_shift_signal_derivation:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.request_id is not None and self.request_id != expected_id:
            raise ValueError("request_id does not match exact derivation selection")
        if self.request_digest is not None and self.request_digest != expected_digest:
            raise ValueError("request_digest does not match exact derivation selection")
        object.__setattr__(self, "request_id", expected_id)
        object.__setattr__(self, "request_digest", expected_digest)
        return self


@dataclass(frozen=True, slots=True)
class PreparedShiftSignalDerivationOutcome:
    """Material derivation or an explicit deterministic no-shift outcome."""

    request: PreparedShiftSignalDerivationRequestV1Alpha1
    admission: PreparedIntelligenceAdmission | None
    material_shift: bool
    replayed: bool

    @property
    def shift(self) -> ShiftV1Alpha1 | None:
        if self.admission is None:
            return None
        return next((item for item in self.admission.resources if isinstance(item, ShiftV1Alpha1)), None)

    @property
    def signal(self) -> SignalV1Alpha1 | None:
        if self.admission is None:
            return None
        return next((item for item in self.admission.resources if isinstance(item, SignalV1Alpha1)), None)


def _activation_precondition(binding: CommittedActivationBinding) -> GovernedStateHeadPreconditionV1Alpha1:
    revision = binding.prepared_binding.revision
    receipt = binding.commit_receipt
    if revision.activation_id is None or revision.revision_id is None or receipt.receipt_id is None:
        raise PreparedShiftSignalDerivationError("committed activation lacks exact current-head coordinates")
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=receipt.state_kind,
        product_id=revision.spec.product_id,
        state_id=revision.activation_id,
        sequence=revision.revision,
        revision_id=revision.revision_id,
        commit_receipt_id=receipt.receipt_id,
    )


class CorePreparedShiftSignalDerivationService(IntelligenceBuildPreparedDerivationPort):
    """Derive and atomically admit PREPARED Shift, Signal, and attention only."""

    def __init__(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        binding: CommittedActivationBinding,
        ledger: PreparedIntelligenceLedgerService,
        governed_state: GovernedStateStore,
        runtime_use: RuntimeUseResolver,
    ) -> None:
        self.build = build
        self.binding = self._validate_binding(binding)
        self.ledger = ledger
        self.governed_state = governed_state
        self.runtime_use = runtime_use
        self._validate_build()

    @staticmethod
    def _validate_binding(binding: CommittedActivationBinding) -> CommittedActivationBinding:
        try:
            exact = bind_committed_activation(
                pack=binding.prepared_binding.pack,
                committed=CommittedDomainActivation(
                    revision=binding.prepared_binding.revision,
                    commit_receipt=binding.commit_receipt,
                ),
            )
        except Exception:
            raise PreparedShiftSignalDerivationError("committed activation binding failed exact revalidation") from None
        if exact != binding:
            raise PreparedShiftSignalDerivationError("committed activation binding changed during revalidation")
        return exact

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
            or ACTIVATE_WATCH_EFFECT not in self.build.request.approved_effects
        ):
            raise PreparedShiftSignalDerivationError("authorized build does not cover the exact watch derivation")
        if self.binding.prepared_binding.reference.product_id != self.build.product_id:
            raise PreparedShiftSignalDerivationError("committed activation crossed the authorized build product")
        if self.ledger.binding != self.binding:
            raise PreparedShiftSignalDerivationError("prepared ledger does not use the exact committed activation")

    async def _current_preconditions(
        self,
        request: PreparedShiftSignalDerivationRequestV1Alpha1,
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, AuthorityUseReceiptV1Alpha1]:
        activation = _activation_precondition(self.binding)
        current_head = await self.governed_state.load_head(
            state_kind=activation.state_kind,
            product_id=activation.product_id,
            state_id=activation.state_id,
        )
        if current_head is None or GovernedStateHeadPreconditionV1Alpha1.from_head(current_head) != activation:
            raise PreparedShiftSignalDerivationError("committed activation is no longer the exact current head")
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
                        evaluated_at=request.evaluated_at,
                    )
                ).model_dump(mode="python")
            )
        except Exception:
            raise PreparedShiftSignalDerivationError("current build authority denied watch derivation") from None
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
            or fresh.evaluated_at != request.evaluated_at
        ):
            raise PreparedShiftSignalDerivationError("current build authority changed exact authorized material")
        return activation, fresh

    async def _load_snapshot(
        self,
        reference: IntelligenceRecordReferenceV1Alpha1,
    ) -> EntitySnapshotV1Alpha1:
        try:
            value = await self.ledger.load_exact(reference)
        except PreparedIntelligenceAdmissionError:
            raise PreparedShiftSignalDerivationError("selected Entity Snapshot failed exact ledger load") from None
        if not isinstance(value, EntitySnapshotV1Alpha1) or resource_reference(value) != reference:
            raise PreparedShiftSignalDerivationError("selected Entity Snapshot is missing or changed")
        if value.activation_revision != self.binding.prepared_binding.reference:
            raise PreparedShiftSignalDerivationError("selected Entity Snapshot crossed exact activation scope")
        return value

    async def derive(
        self,
        request: PreparedShiftSignalDerivationRequestV1Alpha1,
    ) -> PreparedShiftSignalDerivationOutcome:
        try:
            exact = PreparedShiftSignalDerivationRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedShiftSignalDerivationError("derivation request failed exact revalidation") from exc
        if exact.baseline_snapshot.product_id != self.build.product_id:
            raise PreparedShiftSignalDerivationError("derivation request crossed authorized product scope")
        activation, fresh_authority = await self._current_preconditions(exact)
        baseline = await self._load_snapshot(exact.baseline_snapshot)
        current = await self._load_snapshot(exact.current_snapshot)
        try:
            rule = resolve_detector_rule(self.binding.prepared_binding, detector_id=exact.detector_id)
            if isinstance(rule, NumericDeltaRuleV1):
                shift = detect_numeric_shift(
                    binding=self.binding.prepared_binding,
                    detector_id=exact.detector_id,
                    baseline=baseline,
                    current=current,
                    detected_at=exact.evaluated_at,
                )
                signal = (
                    route_shift_as_signal(
                        binding=self.binding.prepared_binding,
                        detector_id=exact.detector_id,
                        shift=shift,
                        detected_at=exact.evaluated_at,
                    )
                    if shift is not None
                    else None
                )
            elif isinstance(rule, CategoricalTransitionRuleV1):
                shift = detect_categorical_shift(
                    binding=self.binding.prepared_binding,
                    detector_id=exact.detector_id,
                    baseline=baseline,
                    current=current,
                    detected_at=exact.evaluated_at,
                )
                signal = (
                    route_categorical_shift_as_signal(
                        binding=self.binding.prepared_binding,
                        detector_id=exact.detector_id,
                        shift=shift,
                        detected_at=exact.evaluated_at,
                    )
                    if shift is not None
                    else None
                )
            elif isinstance(rule, ContentRevisionRuleV1):
                shift = detect_content_revision_shift(
                    binding=self.binding.prepared_binding,
                    detector_id=exact.detector_id,
                    baseline=baseline,
                    current=current,
                    detected_at=exact.evaluated_at,
                )
                signal = (
                    route_content_revision_shift_as_signal(
                        binding=self.binding.prepared_binding,
                        detector_id=exact.detector_id,
                        shift=shift,
                        detected_at=exact.evaluated_at,
                    )
                    if shift is not None
                    else None
                )
            else:
                raise PreparedShiftSignalDerivationError("Pack detector family is not supported by this exact port")
        except (
            PreparedActivationBindingError,
            NumericDeltaDetectionError,
            CategoricalTransitionDetectionError,
            ContentRevisionDetectionError,
        ) as exc:
            raise PreparedShiftSignalDerivationError("activation-bound detector interpretation failed") from exc
        if shift is None or signal is None:
            return PreparedShiftSignalDerivationOutcome(
                request=exact,
                admission=None,
                material_shift=False,
                replayed=False,
            )

        batch = PreparedDerivedResourceAdmissionV1Alpha1(
            derivation_key=exact.derivation_key,
            product_id=self.build.product_id,
            activation_revision=self.binding.prepared_binding.reference,
            pack=self.binding.prepared_binding.revision.spec.pack,
            baseline_snapshot=exact.baseline_snapshot,
            current_snapshot=exact.current_snapshot,
            shift=shift,
            signal=signal,
            processing_order=deterministic_resource_order((shift, signal)),
            attention_evaluated_at=exact.evaluated_at,
        )
        replay = await self.ledger.replay_derived(derivation_key=exact.derivation_key)
        try:
            admission = await self.ledger.admit_derived(
                batch,
                governed_state_preconditions=(
                    activation,
                    fresh_authority.state_head_precondition,
                ),
            )
        except Exception:
            raise PreparedShiftSignalDerivationError("derived Shift, Signal, and attention admission failed") from None
        if admission.resources != (shift, signal):
            raise PreparedShiftSignalDerivationError("derived admission replay changed exact Shift or Signal material")
        return PreparedShiftSignalDerivationOutcome(
            request=exact,
            admission=admission,
            material_shift=True,
            replayed=replay is not None,
        )


__all__ = [
    "ACTIVATE_WATCH_EFFECT",
    "CorePreparedShiftSignalDerivationService",
    "PREPARED_SHIFT_SIGNAL_DERIVATION_REQUEST_VERSION",
    "PreparedShiftSignalDerivationError",
    "PreparedShiftSignalDerivationOutcome",
    "PreparedShiftSignalDerivationRequestV1Alpha1",
]

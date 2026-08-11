"""Owner-governed monitoring lifecycle and bounded sensing-window contracts.

These contracts do not schedule work, acquire a source, deliver a notification,
publish material, or authorize an external action.  They bind explicit owner
requests and completed evaluations to immutable, content-derived receipts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.common import (
    validate_digest,
    validate_product_id,
    validate_reference,
)

EXACT_MATERIAL_REFERENCE_VERSION = "ace.intelligence.exact-material-reference/v1alpha1"
MONITORING_LIFECYCLE_ANCHOR_VERSION = "ace.intelligence.monitoring-lifecycle-anchor/v1alpha1"
MONITORING_LIFECYCLE_REVISION_VERSION = "ace.intelligence.monitoring-lifecycle-revision/v1alpha1"
MONITORING_LIFECYCLE_REQUEST_VERSION = "ace.intelligence.monitoring-lifecycle-request/v1alpha1"
MONITORING_LIFECYCLE_RECEIPT_VERSION = "ace.intelligence.monitoring-lifecycle-receipt/v1alpha1"
SENSING_WINDOW_REQUEST_VERSION = "ace.intelligence.sensing-window-request/v1alpha1"
SENSING_WINDOW_EVALUATION_VERSION = "ace.intelligence.sensing-window-evaluation/v1alpha1"
SENSING_WINDOW_RECEIPT_VERSION = "ace.intelligence.sensing-window-receipt/v1alpha1"

MONITORING_LIFECYCLE_ANCHOR_RECORD_KIND = "monitoring_lifecycle_anchor"
MONITORING_LIFECYCLE_REVISION_RECORD_KIND = "monitoring_lifecycle_revision"
MONITORING_LIFECYCLE_RECORD_KIND = "monitoring_lifecycle"
SENSING_WINDOW_RECORD_KIND = "sensing_window"

MAX_WINDOW_REFERENCES = 1_024


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _derive(
    instance: _StrictFrozenContract,
    *,
    id_field: str,
    digest_field: str,
    prefix: str,
) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact contract material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact contract material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


def _ordered_references(value: Any, *, label: str) -> tuple[ExactMaterialReferenceV1Alpha1, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be an ordered collection")
    try:
        items = tuple(
            item
            if isinstance(item, ExactMaterialReferenceV1Alpha1)
            else ExactMaterialReferenceV1Alpha1.model_validate(item)
            for item in value
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain exact material references") from exc
    keys = [item.reference for item in items]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} must bind each reference at most once")
    return tuple(sorted(items, key=lambda item: (item.reference, item.digest)))


class MonitoringTargetKind(StrEnum):
    MONITOR = "monitor"
    SUBSCRIPTION = "subscription"


class MonitoringLifecycleAction(StrEnum):
    CREATE = "create"
    PAUSE = "pause"
    RESUME = "resume"
    REVOKE = "revoke"


class MonitoringLifecycleState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"


class SensingWindowDisposition(StrEnum):
    ROUTED = "routed"
    SUPPRESSED = "suppressed"


class SensingWindowSuppressionReason(StrEnum):
    NO_MATERIAL_CHANGE = "no_material_change"
    OWNER_PAUSED = "owner_paused"
    MONITOR_REVOKED = "monitor_revoked"
    SUBSCRIPTION_PAUSED = "subscription_paused"
    SUBSCRIPTION_REVOKED = "subscription_revoked"


class SensingWindowMaterialKind(StrEnum):
    NONE = "none"
    MATERIAL_CHANGE = "material_change"
    CORRECTION = "correction"


class ExactMaterialReferenceV1Alpha1(_StrictFrozenContract):
    """One content-bound public reference without importing its payload type."""

    contract: Literal["ace.intelligence.exact-material-reference/v1alpha1"] = EXACT_MATERIAL_REFERENCE_VERSION
    reference: str
    digest: str

    @field_validator("reference")
    @classmethod
    def validate_exact_reference(cls, value: str) -> str:
        return validate_reference(value, name="reference")

    @field_validator("digest")
    @classmethod
    def validate_exact_digest(cls, value: str) -> str:
        return validate_digest(value)


def monitoring_lifecycle_identity(
    *,
    product_id: str,
    target_kind: MonitoringTargetKind,
    target: ExactMaterialReferenceV1Alpha1,
    persona_binding: ExactMaterialReferenceV1Alpha1,
) -> ExactMaterialReferenceV1Alpha1:
    """Return the one stable logical lifecycle identity for an owned intent."""

    material = {
        "contract": MONITORING_LIFECYCLE_ANCHOR_VERSION,
        "product_id": validate_product_id(product_id),
        "target_kind": target_kind.value,
        "target": target.model_dump(mode="json"),
        "persona_binding": persona_binding.model_dump(mode="json"),
    }
    digest = canonical_hash(material)
    return ExactMaterialReferenceV1Alpha1(
        reference=f"monitoring_intent:{digest[:32]}",
        digest=f"sha256:{digest}",
    )


class MonitoringLifecycleAnchorV1Alpha1(_StrictFrozenContract):
    """Stable append-once identity preventing a second lifecycle for one intent."""

    contract: Literal["ace.intelligence.monitoring-lifecycle-anchor/v1alpha1"] = MONITORING_LIFECYCLE_ANCHOR_VERSION
    product_id: str
    target_kind: MonitoringTargetKind
    target: ExactMaterialReferenceV1Alpha1
    persona_binding: ExactMaterialReferenceV1Alpha1
    lifecycle_id: str | None = None
    lifecycle_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("lifecycle_id")
    @classmethod
    def validate_lifecycle_id(cls, value: str | None) -> str | None:
        return validate_reference(value, name="lifecycle_id") if value is not None else None

    @field_validator("lifecycle_digest")
    @classmethod
    def validate_lifecycle_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        expected = monitoring_lifecycle_identity(
            product_id=self.product_id,
            target_kind=self.target_kind,
            target=self.target,
            persona_binding=self.persona_binding,
        )
        if self.lifecycle_id is not None and self.lifecycle_id != expected.reference:
            raise ValueError("lifecycle_id does not match the exact owned intent")
        if self.lifecycle_digest is not None and self.lifecycle_digest != expected.digest:
            raise ValueError("lifecycle_digest does not match the exact owned intent")
        object.__setattr__(self, "lifecycle_id", expected.reference)
        object.__setattr__(self, "lifecycle_digest", expected.digest)
        return self

    def reference(self) -> ExactMaterialReferenceV1Alpha1:
        return ExactMaterialReferenceV1Alpha1(reference=str(self.lifecycle_id), digest=str(self.lifecycle_digest))


def monitoring_lifecycle_revision_id(*, lifecycle: ExactMaterialReferenceV1Alpha1, sequence: int) -> str:
    """Return the append-once slot identity for one logical lifecycle sequence."""

    if sequence < 1:
        raise ValueError("monitoring lifecycle revision sequence must be positive")
    return f"monitoring_lifecycle_revision:{canonical_hash([lifecycle.model_dump(mode='json'), sequence])[:32]}"


class MonitoringLifecycleRevisionV1Alpha1(_StrictFrozenContract):
    """Append-once sequence slot preventing divergent lifecycle branches."""

    contract: Literal["ace.intelligence.monitoring-lifecycle-revision/v1alpha1"] = MONITORING_LIFECYCLE_REVISION_VERSION
    product_id: str
    lifecycle: ExactMaterialReferenceV1Alpha1
    sequence: int = Field(ge=1)
    receipt: ExactMaterialReferenceV1Alpha1
    revision_id: str | None = None
    revision_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("revision_id")
    @classmethod
    def validate_revision_id(cls, value: str | None) -> str | None:
        return validate_reference(value, name="revision_id") if value is not None else None

    @field_validator("revision_digest")
    @classmethod
    def validate_revision_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        expected_id = monitoring_lifecycle_revision_id(lifecycle=self.lifecycle, sequence=self.sequence)
        material = self.model_dump(mode="json", exclude={"revision_id", "revision_digest"})
        expected_digest = f"sha256:{canonical_hash(material)}"
        if self.revision_id is not None and self.revision_id != expected_id:
            raise ValueError("revision_id does not match the exact lifecycle sequence")
        if self.revision_digest is not None and self.revision_digest != expected_digest:
            raise ValueError("revision_digest does not match the exact lifecycle receipt")
        object.__setattr__(self, "revision_id", expected_id)
        object.__setattr__(self, "revision_digest", expected_digest)
        return self

    def reference(self) -> ExactMaterialReferenceV1Alpha1:
        return ExactMaterialReferenceV1Alpha1(reference=str(self.revision_id), digest=str(self.revision_digest))


class MonitoringLifecycleRequestV1Alpha1(_StrictFrozenContract):
    """One authenticated request to advance a stable monitoring intent."""

    contract: Literal["ace.intelligence.monitoring-lifecycle-request/v1alpha1"] = MONITORING_LIFECYCLE_REQUEST_VERSION
    transition_key: str
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    target_kind: MonitoringTargetKind
    target: ExactMaterialReferenceV1Alpha1
    persona_binding: ExactMaterialReferenceV1Alpha1
    lifecycle: ExactMaterialReferenceV1Alpha1 | None = None
    action: MonitoringLifecycleAction
    sequence: int = Field(ge=1)
    prior_receipt: ExactMaterialReferenceV1Alpha1 | None = None
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("transition_key", "request_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("request_digest")
    @classmethod
    def validate_request_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @model_validator(mode="after")
    def validate_scope_sequence_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("authenticated context crossed monitoring product scope")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("monitoring transition must be requested inside the authenticated window")
        if self.sequence == 1:
            if self.action is not MonitoringLifecycleAction.CREATE or self.prior_receipt is not None:
                raise ValueError("the first monitoring transition must create without a prior receipt")
        elif self.action is MonitoringLifecycleAction.CREATE or self.prior_receipt is None:
            raise ValueError("later monitoring transitions require one exact prior receipt")
        expected_lifecycle = monitoring_lifecycle_identity(
            product_id=self.product_id,
            target_kind=self.target_kind,
            target=self.target,
            persona_binding=self.persona_binding,
        )
        if self.lifecycle is not None and self.lifecycle != expected_lifecycle:
            raise ValueError("monitoring request crossed its stable logical intent")
        object.__setattr__(self, "lifecycle", expected_lifecycle)
        _derive(self, id_field="request_id", digest_field="request_digest", prefix="monitoring_lifecycle_request")
        return self


class MonitoringLifecycleReceiptV1Alpha1(_StrictFrozenContract):
    """Immutable owner-authorized transition over one Monitor or Subscription."""

    contract: Literal["ace.intelligence.monitoring-lifecycle-receipt/v1alpha1"] = MONITORING_LIFECYCLE_RECEIPT_VERSION
    product_id: str
    owner_ref: str
    target_kind: MonitoringTargetKind
    target: ExactMaterialReferenceV1Alpha1
    persona_binding: ExactMaterialReferenceV1Alpha1
    lifecycle: ExactMaterialReferenceV1Alpha1
    request: ExactMaterialReferenceV1Alpha1
    action: MonitoringLifecycleAction
    sequence: int = Field(ge=1)
    state_before: MonitoringLifecycleState | None = None
    state_after: MonitoringLifecycleState
    prior_receipt: ExactMaterialReferenceV1Alpha1 | None = None
    applied_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("owner_ref", "receipt_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("receipt_digest")
    @classmethod
    def validate_receipt_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("applied_at")
    @classmethod
    def normalize_applied_at(cls, value: datetime) -> datetime:
        return _aware(value, name="applied_at")

    @model_validator(mode="after")
    def validate_transition_and_identity(self) -> Self:
        allowed = {
            MonitoringLifecycleAction.CREATE: {
                (None, MonitoringLifecycleState.ACTIVE),
                (None, MonitoringLifecycleState.PAUSED),
            },
            MonitoringLifecycleAction.PAUSE: {
                (MonitoringLifecycleState.ACTIVE, MonitoringLifecycleState.PAUSED),
            },
            MonitoringLifecycleAction.RESUME: {
                (MonitoringLifecycleState.PAUSED, MonitoringLifecycleState.ACTIVE),
            },
            MonitoringLifecycleAction.REVOKE: {
                (MonitoringLifecycleState.ACTIVE, MonitoringLifecycleState.REVOKED),
                (MonitoringLifecycleState.PAUSED, MonitoringLifecycleState.REVOKED),
            },
        }
        if (self.state_before, self.state_after) not in allowed[self.action]:
            raise ValueError("monitoring lifecycle transition is not allowed")
        if self.sequence == 1:
            if self.action is not MonitoringLifecycleAction.CREATE or self.prior_receipt is not None:
                raise ValueError("first monitoring receipt must be an unchained create")
        elif self.action is MonitoringLifecycleAction.CREATE or self.prior_receipt is None:
            raise ValueError("later monitoring receipts must preserve the exact prior receipt")
        if self.lifecycle != monitoring_lifecycle_identity(
            product_id=self.product_id,
            target_kind=self.target_kind,
            target=self.target,
            persona_binding=self.persona_binding,
        ):
            raise ValueError("monitoring receipt crossed its stable logical intent")
        _derive(self, id_field="receipt_id", digest_field="receipt_digest", prefix="monitoring_lifecycle")
        return self

    def reference(self) -> ExactMaterialReferenceV1Alpha1:
        return ExactMaterialReferenceV1Alpha1(reference=str(self.receipt_id), digest=str(self.receipt_digest))


class SensingWindowRequestV1Alpha1(_StrictFrozenContract):
    """One explicit owner request for a bounded sensing evaluation."""

    contract: Literal["ace.intelligence.sensing-window-request/v1alpha1"] = SENSING_WINDOW_REQUEST_VERSION
    window_key: str
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    monitor_lifecycle: ExactMaterialReferenceV1Alpha1
    subscription_lifecycle: ExactMaterialReferenceV1Alpha1
    requested_at: datetime
    window_started_at: datetime
    window_ended_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("window_key", "request_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("request_digest")
    @classmethod
    def validate_request_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("requested_at", "window_started_at", "window_ended_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_window_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("authenticated context crossed sensing-window product scope")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("sensing window must be requested inside the authenticated window")
        if not self.requested_at <= self.window_started_at < self.window_ended_at:
            raise ValueError("sensing window requires one positive interval after its explicit request")
        _derive(self, id_field="request_id", digest_field="request_digest", prefix="sensing_window_request")
        return self

    def reference(self) -> ExactMaterialReferenceV1Alpha1:
        return ExactMaterialReferenceV1Alpha1(reference=str(self.request_id), digest=str(self.request_digest))


class SensingWindowEvaluationV1Alpha1(_StrictFrozenContract):
    """Exact completed evaluation material supplied to the append-only service."""

    contract: Literal["ace.intelligence.sensing-window-evaluation/v1alpha1"] = SENSING_WINDOW_EVALUATION_VERSION
    request: ExactMaterialReferenceV1Alpha1
    acquisition_requests: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    source_transactions: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    accepted_resources: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    replayed_resources: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    routed_resources: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    material_kind: SensingWindowMaterialKind
    disposition: SensingWindowDisposition
    suppression_reason: SensingWindowSuppressionReason | None = None
    correction_visible: bool = False
    evaluated_at: datetime

    @field_validator(
        "acquisition_requests",
        "source_transactions",
        "accepted_resources",
        "replayed_resources",
        "routed_resources",
        mode="before",
    )
    @classmethod
    def preserve_collections(cls, value: Any, info) -> tuple[ExactMaterialReferenceV1Alpha1, ...]:
        return _ordered_references(value, label=info.field_name)

    @field_validator("evaluated_at")
    @classmethod
    def normalize_evaluated_at(cls, value: datetime) -> datetime:
        return _aware(value, name="evaluated_at")

    @model_validator(mode="after")
    def validate_disposition_shape(self) -> Self:
        accepted = {item.reference for item in self.accepted_resources}
        replayed = {item.reference for item in self.replayed_resources}
        if accepted.intersection(replayed):
            raise ValueError("accepted and replayed sensing resources must be disjoint")
        if self.disposition is SensingWindowDisposition.ROUTED:
            if (
                self.suppression_reason is not None
                or self.material_kind is SensingWindowMaterialKind.NONE
                or not self.accepted_resources
                or not self.routed_resources
            ):
                raise ValueError("routed sensing windows require accepted and routed material without suppression")
        elif self.suppression_reason is None or self.routed_resources:
            raise ValueError("suppressed sensing windows require one reason and no routed resources")
        if self.material_kind is SensingWindowMaterialKind.CORRECTION and (
            self.disposition is not SensingWindowDisposition.ROUTED
            or not self.correction_visible
            or not self.accepted_resources
        ):
            raise ValueError("correction material must remain visibly routed")
        if self.suppression_reason is SensingWindowSuppressionReason.NO_MATERIAL_CHANGE and (
            self.material_kind is not SensingWindowMaterialKind.NONE
            or self.accepted_resources
            or not self.replayed_resources
            or self.correction_visible
        ):
            raise ValueError("no-material-change suppression requires exact replay-only material")
        if self.suppression_reason not in {None, SensingWindowSuppressionReason.NO_MATERIAL_CHANGE} and (
            self.material_kind is not SensingWindowMaterialKind.NONE
            or self.correction_visible
            or self.acquisition_requests
            or self.source_transactions
            or self.accepted_resources
            or self.replayed_resources
            or self.routed_resources
        ):
            raise ValueError("lifecycle-guard suppression requires zero acquisition and material")
        return self


class SensingWindowReceiptV1Alpha1(_StrictFrozenContract):
    """Append-only routed-or-suppressed result for one explicit sensing window."""

    contract: Literal["ace.intelligence.sensing-window-receipt/v1alpha1"] = SENSING_WINDOW_RECEIPT_VERSION
    product_id: str
    owner_ref: str
    request: ExactMaterialReferenceV1Alpha1
    monitor_lifecycle: ExactMaterialReferenceV1Alpha1
    subscription_lifecycle: ExactMaterialReferenceV1Alpha1
    monitor_state: MonitoringLifecycleState
    subscription_state: MonitoringLifecycleState
    requested_at: datetime
    window_started_at: datetime
    window_ended_at: datetime
    acquisition_requests: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    source_transactions: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    accepted_resources: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    replayed_resources: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    routed_resources: tuple[ExactMaterialReferenceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_WINDOW_REFERENCES,
    )
    material_kind: SensingWindowMaterialKind
    disposition: SensingWindowDisposition
    suppression_reason: SensingWindowSuppressionReason | None = None
    correction_visible: bool = False
    evaluated_at: datetime
    scheduler_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    external_action_authority: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("owner_ref", "receipt_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("receipt_digest")
    @classmethod
    def validate_receipt_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("requested_at", "window_started_at", "window_ended_at", "evaluated_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator(
        "acquisition_requests",
        "source_transactions",
        "accepted_resources",
        "replayed_resources",
        "routed_resources",
        mode="before",
    )
    @classmethod
    def preserve_collections(cls, value: Any, info) -> tuple[ExactMaterialReferenceV1Alpha1, ...]:
        return _ordered_references(value, label=info.field_name)

    @model_validator(mode="after")
    def validate_guard_disposition_and_identity(self) -> Self:
        if not self.requested_at <= self.window_started_at < self.window_ended_at <= self.evaluated_at:
            raise ValueError("sensing receipt times do not preserve the requested bounded interval")

        guarded_reason: SensingWindowSuppressionReason | None = None
        if self.subscription_state is MonitoringLifecycleState.REVOKED:
            guarded_reason = SensingWindowSuppressionReason.SUBSCRIPTION_REVOKED
        elif self.subscription_state is MonitoringLifecycleState.PAUSED:
            guarded_reason = SensingWindowSuppressionReason.SUBSCRIPTION_PAUSED
        elif self.monitor_state is MonitoringLifecycleState.REVOKED:
            guarded_reason = SensingWindowSuppressionReason.MONITOR_REVOKED
        elif self.monitor_state is MonitoringLifecycleState.PAUSED:
            guarded_reason = SensingWindowSuppressionReason.OWNER_PAUSED

        if guarded_reason is not None:
            if (
                self.disposition is not SensingWindowDisposition.SUPPRESSED
                or self.suppression_reason is not guarded_reason
                or self.material_kind is not SensingWindowMaterialKind.NONE
                or self.correction_visible
                or self.acquisition_requests
                or self.source_transactions
                or self.accepted_resources
                or self.replayed_resources
                or self.routed_resources
            ):
                raise ValueError("paused or revoked sensing windows require zero acquisition and exact suppression")
        elif (
            self.monitor_state is not MonitoringLifecycleState.ACTIVE
            or self.subscription_state is not MonitoringLifecycleState.ACTIVE
        ):
            raise ValueError("sensing window lifecycle state is not actionable")
        elif (
            self.disposition is SensingWindowDisposition.SUPPRESSED
            and self.suppression_reason is not SensingWindowSuppressionReason.NO_MATERIAL_CHANGE
        ):
            raise ValueError("active sensing windows may suppress only exact no-material-change replay")

        evaluation = SensingWindowEvaluationV1Alpha1(
            request=self.request,
            acquisition_requests=self.acquisition_requests,
            source_transactions=self.source_transactions,
            accepted_resources=self.accepted_resources,
            replayed_resources=self.replayed_resources,
            routed_resources=self.routed_resources,
            material_kind=self.material_kind,
            disposition=self.disposition,
            suppression_reason=self.suppression_reason,
            correction_visible=self.correction_visible,
            evaluated_at=self.evaluated_at,
        )
        if evaluation.request != self.request:
            raise ValueError("sensing receipt evaluation crossed its exact request")
        _derive(self, id_field="receipt_id", digest_field="receipt_digest", prefix="sensing_window")
        return self

    def reference(self) -> ExactMaterialReferenceV1Alpha1:
        return ExactMaterialReferenceV1Alpha1(reference=str(self.receipt_id), digest=str(self.receipt_digest))


__all__ = [
    "EXACT_MATERIAL_REFERENCE_VERSION",
    "MAX_WINDOW_REFERENCES",
    "MONITORING_LIFECYCLE_ANCHOR_RECORD_KIND",
    "MONITORING_LIFECYCLE_ANCHOR_VERSION",
    "MONITORING_LIFECYCLE_RECEIPT_VERSION",
    "MONITORING_LIFECYCLE_RECORD_KIND",
    "MONITORING_LIFECYCLE_REVISION_RECORD_KIND",
    "MONITORING_LIFECYCLE_REVISION_VERSION",
    "MONITORING_LIFECYCLE_REQUEST_VERSION",
    "SENSING_WINDOW_EVALUATION_VERSION",
    "SENSING_WINDOW_RECEIPT_VERSION",
    "SENSING_WINDOW_RECORD_KIND",
    "SENSING_WINDOW_REQUEST_VERSION",
    "ExactMaterialReferenceV1Alpha1",
    "MonitoringLifecycleAction",
    "MonitoringLifecycleAnchorV1Alpha1",
    "MonitoringLifecycleReceiptV1Alpha1",
    "MonitoringLifecycleRequestV1Alpha1",
    "MonitoringLifecycleRevisionV1Alpha1",
    "MonitoringLifecycleState",
    "MonitoringTargetKind",
    "SensingWindowDisposition",
    "SensingWindowEvaluationV1Alpha1",
    "SensingWindowMaterialKind",
    "SensingWindowReceiptV1Alpha1",
    "SensingWindowRequestV1Alpha1",
    "SensingWindowSuppressionReason",
    "monitoring_lifecycle_identity",
    "monitoring_lifecycle_revision_id",
]

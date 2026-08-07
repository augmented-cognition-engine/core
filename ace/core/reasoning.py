"""Opaque governed reasoning contracts and replay-first execution service.

Core owns exact record validation, current runtime-use resolution, durable
acceptance, provider execution, attribution receipts, terminal commit, and
replay.  Higher layers own every semantic interpretation of the canonical JSON
carried through this boundary.

Provider execution is at-least-once until the terminal transaction commits.  A
durable accepted attempt without a terminal receipt is intentionally orphaned:
after restart callers must submit a new attempt key instead of asking Core to
guess whether an earlier provider execution occurred.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Literal, Protocol, Self

from pydantic import ConfigDict, Field, TypeAdapter, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
    RuntimeUseResolver,
    capability_state_ref_for_artifact,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1

FROZEN_CONTEXT_ITEM_VERSION = "ace.core.frozen-context-item/v1alpha1"
GOVERNED_REASONING_REQUEST_VERSION = "ace.core.governed-reasoning-request/v1alpha1"
REASONING_EXECUTION_BINDING_VERSION = "ace.core.reasoning-execution-binding/v1alpha1"
GOVERNED_OPERATION_BINDING_VERSION = "ace.core.governed-operation-binding/v1alpha1"
PROVIDER_EXECUTION_REQUEST_VERSION = "ace.core.provider-execution-request/v1alpha1"
PROVIDER_ROUTE_VERSION = "ace.core.provider-route/v1alpha1"
PROVIDER_USAGE_VERSION = "ace.core.provider-usage/v1alpha1"
PROVIDER_STRUCTURED_OUTPUT_VERSION = "ace.core.provider-structured-output/v1alpha1"
STRUCTURED_FINAL_RESULT_VERSION = "ace.core.structured-final-result/v1alpha1"
CONTEXT_BINDING_VERSION = "ace.core.context-binding/v1alpha1"
RECEIPT_REFERENCE_VERSION = "ace.core.receipt-reference/v1alpha1"
REASONING_ACCEPTANCE_RECEIPT_VERSION = "ace.core.reasoning-acceptance-receipt/v1alpha1"
CONTEXT_USE_RECEIPT_VERSION = "ace.core.context-use-receipt/v1alpha1"
REASONING_TERMINAL_RECEIPT_VERSION = "ace.core.reasoning-terminal-receipt/v1alpha1"
GOVERNED_ACTION_AUTHORIZATION_REQUEST_VERSION = "ace.core.governed-action-authorization-request/v1alpha1"
GOVERNED_ACTION_AUTHORIZATION_RECEIPT_VERSION = "ace.core.governed-action-authorization-receipt/v1alpha1"
GOVERNED_ACTION_AUTHORIZATION_PROJECTION_VERSION = "ace.core.governed-action-authorization-projection/v1alpha1"

REASONING_RECORD_SPACE = "governed_reasoning"
REASONING_OPERATION = "reason"
REASONING_CONFIGURATION_STATE_KIND = "reasoning_configuration"
GOVERNED_OPERATION_CONFIGURATION_STATE_KIND = "governed_operation_configuration"
MAX_CONTEXT_ITEMS = 256
MAX_CANONICAL_CHARS = 2_000_000

_JSON_OBJECT = TypeAdapter(dict[str, Any])
_LOAD_FAILED = object()


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


def _bounded(value: str, *, name: str, maximum: int = 240) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _digest(value: str, *, name: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax") from exc
    if value != value.lower():
        raise ValueError(f"{name} must use lowercase sha256:<64-hex> syntax")
    return value


def _canonical_object(value: str, *, name: str) -> str:
    if not value or len(value) > MAX_CANONICAL_CHARS:
        raise ValueError(f"{name} must be bounded canonical JSON")
    try:
        parsed = _JSON_OBJECT.validate_json(value)
        normalized = canonical_json(parsed)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{name} must be one finite canonical JSON object") from exc
    if value != normalized:
        raise ValueError(f"{name} must already use canonical JSON encoding")
    return value


def _derive_identity(instance: _StrictFrozenContract, *, prefix: str, id_field: str, digest_field: str) -> None:
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


class FrozenContextItemV1Alpha1(_StrictFrozenContract):
    """One exact immutable record plus opaque canonical JSON selected by a caller."""

    contract: Literal["ace.core.frozen-context-item/v1alpha1"] = FROZEN_CONTEXT_ITEM_VERSION
    product_id: str
    record_space: str
    record_kind: str
    record_key: str
    storage_id: str
    material_digest: str
    payload_contract: str
    as_of: datetime
    available_at: datetime
    source_instruction_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    content_json: str
    context_id: str | None = None
    context_digest: str | None = None

    @field_validator(
        "product_id",
        "record_key",
        "storage_id",
        "payload_contract",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("record_space", "record_kind")
    @classmethod
    def validate_classifiers(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name, maximum=120)

    @field_validator("material_digest", "context_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("as_of", "available_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("content_json")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _canonical_object(value, name="content_json")

    @field_validator("context_id")
    @classmethod
    def validate_context_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="context_id") if value is not None else None

    @model_validator(mode="after")
    def validate_time_and_identity(self) -> Self:
        if self.available_at < self.as_of:
            raise ValueError("context availability cannot precede its as_of time")
        _derive_identity(
            self,
            prefix="frozen_context",
            id_field="context_id",
            digest_field="context_digest",
        )
        return self


class ContextBindingV1Alpha1(_StrictFrozenContract):
    """Content-free coordinates for one frozen context item."""

    contract: Literal["ace.core.context-binding/v1alpha1"] = CONTEXT_BINDING_VERSION
    context_id: str
    context_digest: str
    storage_id: str
    material_digest: str
    as_of: datetime
    available_at: datetime

    @field_validator("context_id", "storage_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("context_digest", "material_digest")
    @classmethod
    def validate_hashes(cls, value: str, info) -> str:
        return _digest(value, name=info.field_name)

    @field_validator("as_of", "available_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.available_at < self.as_of:
            raise ValueError("context binding availability cannot precede its as_of time")
        return self

    @classmethod
    def from_item(cls, item: FrozenContextItemV1Alpha1) -> ContextBindingV1Alpha1:
        return cls(
            context_id=str(item.context_id),
            context_digest=str(item.context_digest),
            storage_id=item.storage_id,
            material_digest=item.material_digest,
            as_of=item.as_of,
            available_at=item.available_at,
        )


class ReasoningExecutionBindingV1Alpha1(_StrictFrozenContract):
    """Host-owned exact provider selection under one current product-policy head."""

    contract: Literal["ace.core.reasoning-execution-binding/v1alpha1"] = REASONING_EXECUTION_BINDING_VERSION
    product_id: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    configuration_ref: str
    authority: str
    grant_ref: str
    state_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    binding_id: str | None = None
    binding_digest: str | None = None

    @field_validator("product_id", "configuration_ref", "authority", "grant_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("binding_id")
    @classmethod
    def validate_binding_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="binding_id") if value is not None else None

    @field_validator("binding_digest")
    @classmethod
    def validate_binding_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="binding_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.state_head_precondition.product_id != self.product_id:
            raise ValueError("reasoning execution binding crossed exact product scope")
        if (
            self.state_head_precondition.state_kind != REASONING_CONFIGURATION_STATE_KIND
            or self.state_head_precondition.state_id != self.configuration_ref
        ):
            raise ValueError("reasoning execution binding requires its exact configuration-state head")
        if (
            self.artifact.capability != "structured_reasoning"
            or self.artifact.contract != "ace.core.reasoning-provider/v1alpha1"
        ):
            raise ValueError("reasoning execution binding requires the Core structured provider contract")
        _derive_identity(
            self,
            prefix="reasoning_execution_binding",
            id_field="binding_id",
            digest_field="binding_digest",
        )
        return self


class GovernedOperationBindingV1Alpha1(_StrictFrozenContract):
    """Host-owned artifact and authority selection for one opaque operation."""

    contract: Literal["ace.core.governed-operation-binding/v1alpha1"] = GOVERNED_OPERATION_BINDING_VERSION
    product_id: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    configuration_ref: str
    authority: str
    grant_ref: str
    state_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    binding_id: str | None = None
    binding_digest: str | None = None

    @field_validator("product_id", "configuration_ref", "authority", "grant_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("binding_id")
    @classmethod
    def validate_binding_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="binding_id") if value is not None else None

    @field_validator("binding_digest")
    @classmethod
    def validate_binding_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="binding_digest") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if (
            self.state_head_precondition.product_id != self.product_id
            or self.state_head_precondition.state_kind != GOVERNED_OPERATION_CONFIGURATION_STATE_KIND
            or self.state_head_precondition.state_id != self.configuration_ref
        ):
            raise ValueError("governed operation binding requires its exact configuration-state head")
        _derive_identity(
            self,
            prefix="governed_operation_binding",
            id_field="binding_id",
            digest_field="binding_digest",
        )
        return self


class GovernedActionAuthorizationRequestV1Alpha1(_StrictFrozenContract):
    """One domain-neutral actor-scoped authorization for an opaque exact subject."""

    contract: Literal["ace.core.governed-action-authorization-request/v1alpha1"] = (
        GOVERNED_ACTION_AUTHORIZATION_REQUEST_VERSION
    )
    authorization_key: str
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    execution_binding: GovernedOperationBindingV1Alpha1
    operation: str
    subject_ref: str
    subject_digest: str
    requested_at: datetime
    required_state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(
        default_factory=tuple, max_length=62, exclude_if=lambda value: not value
    )
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("authorization_key", "product_id", "subject_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, value: str) -> str:
        if not value or len(value) > 120 or value != value.strip():
            raise ValueError("operation must be a bounded opaque identifier")
        return value

    @field_validator("subject_digest", "request_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("requested_at")
    @classmethod
    def validate_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="request_id") if value is not None else None

    @field_validator("required_state_preconditions")
    @classmethod
    def validate_preconditions(
        cls,
        value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        identities = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError("required state preconditions must name each identity once")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or self.execution_binding.product_id != self.product_id
            or any(item.product_id != self.product_id for item in self.required_state_preconditions)
        ):
            raise ValueError("governed action authorization crossed exact product scope")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("action authorization must be requested inside authentication")
        _derive_identity(
            self,
            prefix="governed_action_authorization_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self


class GovernedReasoningRequestV1Alpha1(_StrictFrozenContract):
    """One exact actor-scoped request over opaque frozen context."""

    contract: Literal["ace.core.governed-reasoning-request/v1alpha1"] = GOVERNED_REASONING_REQUEST_VERSION
    attempt_key: str
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    operation: Literal["reason"] = REASONING_OPERATION
    artifact: CapabilityArtifactIdentityV1Alpha1
    configuration_ref: str
    authority: str
    grant_ref: str
    instruction_json: str
    context_items: tuple[FrozenContextItemV1Alpha1, ...] = Field(
        min_length=1,
        max_length=MAX_CONTEXT_ITEMS,
    )
    cutoff_at: datetime
    requested_at: datetime
    required_state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=62,
        exclude_if=lambda value: not value,
    )
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator(
        "attempt_key",
        "product_id",
        "configuration_ref",
        "authority",
        "grant_ref",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("instruction_json")
    @classmethod
    def validate_instructions(cls, value: str) -> str:
        return _canonical_object(value, name="instruction_json")

    @field_validator("cutoff_at", "requested_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="request_id") if value is not None else None

    @field_validator("request_digest")
    @classmethod
    def validate_request_digest(cls, value: str | None) -> str | None:
        return _digest(value, name="request_digest") if value is not None else None

    @field_validator("context_items")
    @classmethod
    def validate_unique_context(
        cls,
        value: tuple[FrozenContextItemV1Alpha1, ...],
    ) -> tuple[FrozenContextItemV1Alpha1, ...]:
        ids = [item.context_id for item in value]
        storage_ids = [item.storage_id for item in value]
        if len(ids) != len(set(ids)) or len(storage_ids) != len(set(storage_ids)):
            raise ValueError("context items must use unique content and storage identities")
        return tuple(sorted(value, key=lambda item: str(item.context_id)))

    @field_validator("required_state_preconditions")
    @classmethod
    def validate_preconditions(
        cls,
        value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        identities = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError("required state preconditions must name each identity once")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if (
            self.authenticated_context.product_id != self.product_id
            or any(item.product_id != self.product_id for item in self.context_items)
            or any(item.product_id != self.product_id for item in self.required_state_preconditions)
        ):
            raise ValueError("reasoning request crossed exact product scope")
        if self.cutoff_at > self.requested_at:
            raise ValueError("reasoning cutoff cannot follow request time")
        if any(item.as_of > self.cutoff_at or item.available_at > self.cutoff_at for item in self.context_items):
            raise ValueError("every context item must be available by the exact cutoff")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("reasoning request must occur inside the authenticated window")
        _derive_identity(
            self,
            prefix="governed_reasoning_request",
            id_field="request_id",
            digest_field="request_digest",
        )
        return self


class ProviderExecutionRequestV1Alpha1(_StrictFrozenContract):
    """Ephemeral provider input; this full object is never persisted by the service."""

    contract: Literal["ace.core.provider-execution-request/v1alpha1"] = PROVIDER_EXECUTION_REQUEST_VERSION
    product_id: str
    request_id: str
    request_digest: str
    attempt_key: str
    instruction_json: str
    context_items: tuple[FrozenContextItemV1Alpha1, ...] = Field(
        min_length=1,
        max_length=MAX_CONTEXT_ITEMS,
    )
    cutoff_at: datetime
    started_at: datetime

    @field_validator("product_id", "request_id", "attempt_key")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("request_digest")
    @classmethod
    def validate_request_digest(cls, value: str) -> str:
        return _digest(value, name="request_digest")

    @field_validator("instruction_json")
    @classmethod
    def validate_instructions(cls, value: str) -> str:
        return _canonical_object(value, name="instruction_json")

    @field_validator("cutoff_at", "started_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_and_cutoff(self) -> Self:
        if any(item.product_id != self.product_id for item in self.context_items):
            raise ValueError("provider input crossed exact product scope")
        if self.cutoff_at > self.started_at:
            raise ValueError("provider execution cannot start before the exact cutoff")
        return self


class ProviderRouteV1Alpha1(_StrictFrozenContract):
    """Actual bounded provider/model/configuration route used for one execution."""

    contract: Literal["ace.core.provider-route/v1alpha1"] = PROVIDER_ROUTE_VERSION
    provider_id: str
    model_id: str
    model_version: str
    configuration_digest: str

    @field_validator("provider_id", "model_id", "model_version")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name, maximum=120)

    @field_validator("configuration_digest")
    @classmethod
    def validate_configuration_digest(cls, value: str) -> str:
        return _digest(value, name="configuration_digest")


class ProviderUsageV1Alpha1(_StrictFrozenContract):
    """Bounded provider-reported unit and latency facts."""

    contract: Literal["ace.core.provider-usage/v1alpha1"] = PROVIDER_USAGE_VERSION
    input_units: int = Field(ge=0, le=1_000_000_000)
    output_units: int = Field(ge=0, le=1_000_000_000)
    total_units: int = Field(ge=0, le=2_000_000_000)
    duration_ms: int = Field(ge=0, le=86_400_000)

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        if self.total_units != self.input_units + self.output_units:
            raise ValueError("provider total_units must equal input_units plus output_units")
        return self


class ProviderStructuredOutputV1Alpha1(_StrictFrozenContract):
    """Provider-returned canonical JSON plus explicit output-reference attribution."""

    contract: Literal["ace.core.provider-structured-output/v1alpha1"] = PROVIDER_STRUCTURED_OUTPUT_VERSION
    route: ProviderRouteV1Alpha1
    usage: ProviderUsageV1Alpha1
    structured_json: str
    referenced_context_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_CONTEXT_ITEMS)

    @field_validator("structured_json")
    @classmethod
    def validate_structured_json(cls, value: str) -> str:
        return _canonical_object(value, name="structured_json")

    @field_validator("referenced_context_ids")
    @classmethod
    def validate_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_bounded(item, name="referenced_context_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("referenced context identities must be unique")
        return tuple(sorted(validated))


class StructuredFinalResultV1Alpha1(_StrictFrozenContract):
    """Opaque structured final output durably owned by Core."""

    contract: Literal["ace.core.structured-final-result/v1alpha1"] = STRUCTURED_FINAL_RESULT_VERSION
    product_id: str
    attempt_key: str
    request_id: str
    request_digest: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    route: ProviderRouteV1Alpha1
    usage: ProviderUsageV1Alpha1
    structured_json: str
    referenced_context_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_CONTEXT_ITEMS)
    completed_at: datetime
    result_id: str | None = None
    result_digest: str | None = None

    @field_validator("product_id", "attempt_key", "request_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("request_digest", "result_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("structured_json")
    @classmethod
    def validate_structured_json(cls, value: str) -> str:
        return _canonical_object(value, name="structured_json")

    @field_validator("referenced_context_ids")
    @classmethod
    def validate_context_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(_bounded(item, name="referenced_context_id") for item in value)
        if len(validated) != len(set(validated)):
            raise ValueError("referenced context identities must be unique")
        return tuple(sorted(validated))

    @field_validator("completed_at")
    @classmethod
    def validate_completed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="completed_at")

    @field_validator("result_id")
    @classmethod
    def validate_result_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="result_id") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive_identity(
            self,
            prefix="structured_final_result",
            id_field="result_id",
            digest_field="result_digest",
        )
        return self


class ReceiptReferenceV1Alpha1(_StrictFrozenContract):
    """Content-free exact reference to a durable receipt."""

    contract: Literal["ace.core.receipt-reference/v1alpha1"] = RECEIPT_REFERENCE_VERSION
    receipt_id: str
    receipt_digest: str

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str) -> str:
        return _bounded(value, name="receipt_id")

    @field_validator("receipt_digest")
    @classmethod
    def validate_receipt_digest(cls, value: str) -> str:
        return _digest(value, name="receipt_digest")


def _receipt_reference(value: Any) -> ReceiptReferenceV1Alpha1:
    receipt_id = getattr(value, "receipt_id", None)
    receipt_digest = getattr(value, "receipt_digest", None)
    if receipt_id is None or receipt_digest is None:
        raise ValueError("durable receipt is missing its exact identity")
    return ReceiptReferenceV1Alpha1(receipt_id=receipt_id, receipt_digest=receipt_digest)


class _GovernedActionAuthorizationReceiptV1Alpha1(_StrictFrozenContract):
    """Private durable proof of current use for one opaque operation and subject."""

    contract: Literal["ace.core.governed-action-authorization-receipt/v1alpha1"] = (
        GOVERNED_ACTION_AUTHORIZATION_RECEIPT_VERSION
    )
    disposition: Literal["authorized"] = "authorized"
    product_id: str
    authorization_key: str
    authorization_family_key: str
    request_id: str
    request_digest: str
    operation: str
    subject_ref: str
    subject_digest: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    execution_binding: GovernedOperationBindingV1Alpha1
    capability_use: CapabilityUseReceiptV1Alpha1
    authority_use: AuthorityUseReceiptV1Alpha1
    required_state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(default=(), max_length=62)
    state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=2, max_length=64)
    authorized_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id",
        "authorization_key",
        "authorization_family_key",
        "request_id",
        "operation",
        "subject_ref",
    )
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("request_digest", "subject_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("authorized_at")
    @classmethod
    def validate_authorized_at(cls, value: datetime) -> datetime:
        return _aware(value, name="authorized_at")

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="receipt_id") if value is not None else None

    @field_validator("required_state_preconditions", "state_preconditions")
    @classmethod
    def validate_preconditions(
        cls,
        value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        identities = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError("authorization state preconditions must be unique")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        expected_use_heads: dict[tuple[str, str, str], GovernedStateHeadPreconditionV1Alpha1] = {}
        for head in (
            *self.required_state_preconditions,
            self.execution_binding.state_head_precondition,
            self.capability_use.state_head_precondition,
            self.authority_use.state_head_precondition,
        ):
            identity = (head.state_kind, head.product_id, head.state_id)
            prior = expected_use_heads.setdefault(identity, head)
            if prior != head:
                raise ValueError("authorization state preconditions conflict")
        actual_heads = {(item.state_kind, item.product_id, item.state_id): item for item in self.state_preconditions}
        if (
            self.authenticated_context.product_id != self.product_id
            or self.execution_binding.product_id != self.product_id
            or self.capability_use.product_id != self.product_id
            or self.authority_use.product_id != self.product_id
            or self.capability_use.actor_ref != self.authenticated_context.actor_ref
            or self.authority_use.actor_ref != self.authenticated_context.actor_ref
            or self.capability_use.authenticated_context != self.authenticated_context
            or self.authority_use.authenticated_context != self.authenticated_context
            or self.capability_use.use_subject_ref != self.subject_ref
            or self.authority_use.use_subject_ref != self.subject_ref
            or self.capability_use.use_subject_digest != self.subject_digest
            or self.authority_use.use_subject_digest != self.subject_digest
            or self.capability_use.operation != self.operation
            or self.authority_use.operation != self.operation
            or self.capability_use.artifact != self.execution_binding.artifact
            or self.capability_use.configuration_ref != self.execution_binding.configuration_ref
            or self.authority_use.authority != self.execution_binding.authority
            or self.authority_use.grant_ref != self.execution_binding.grant_ref
            or self.capability_use.evaluated_at > self.authorized_at
            or self.authority_use.evaluated_at > self.authorized_at
            or not (
                self.authenticated_context.authenticated_at
                <= self.capability_use.evaluated_at
                <= self.authorized_at
                < self.authenticated_context.expires_at
            )
            or not (
                self.authenticated_context.authenticated_at <= self.authority_use.evaluated_at <= self.authorized_at
            )
            or (self.authority_use.expires_at is not None and self.authorized_at >= self.authority_use.expires_at)
            or any(item.product_id != self.product_id for item in self.required_state_preconditions)
            or any(item.product_id != self.product_id for item in self.state_preconditions)
            or actual_heads != expected_use_heads
        ):
            raise ValueError(
                "authorization receipt crossed exact principal, operation, subject, execution, or use material"
            )
        _derive_identity(
            self,
            prefix="governed_action_authorization",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


def _historical_action_request(
    authorization: _GovernedActionAuthorizationReceiptV1Alpha1,
    *,
    requested_at: datetime,
) -> GovernedActionAuthorizationRequestV1Alpha1:
    """Reconstruct the exact private command identity without trusting a caller key."""

    return GovernedActionAuthorizationRequestV1Alpha1(
        authorization_key=authorization.authorization_family_key,
        product_id=authorization.product_id,
        authenticated_context=authorization.authenticated_context,
        execution_binding=authorization.execution_binding,
        operation=authorization.operation,
        subject_ref=authorization.subject_ref,
        subject_digest=authorization.subject_digest,
        requested_at=requested_at,
        required_state_preconditions=authorization.required_state_preconditions,
        request_id=authorization.request_id,
        request_digest=authorization.request_digest,
    )


class ReasoningAcceptanceReceiptV1Alpha1(_StrictFrozenContract):
    """Durable proof that one exact attempt was accepted before execution."""

    contract: Literal["ace.core.reasoning-acceptance-receipt/v1alpha1"] = REASONING_ACCEPTANCE_RECEIPT_VERSION
    disposition: Literal["accepted"] = "accepted"
    product_id: str
    attempt_key: str
    request_id: str
    request_digest: str
    actor_ref: str
    cutoff_at: datetime
    instruction_digest: str
    context_bindings: tuple[ContextBindingV1Alpha1, ...] = Field(
        min_length=1,
        max_length=MAX_CONTEXT_ITEMS,
    )
    capability_use: ReceiptReferenceV1Alpha1
    authority_use: ReceiptReferenceV1Alpha1
    state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(max_length=64)
    accepted_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "attempt_key", "request_id", "actor_ref")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("request_digest", "instruction_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("cutoff_at", "accepted_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="receipt_id") if value is not None else None

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.cutoff_at > self.accepted_at:
            raise ValueError("acceptance cannot predate the exact cutoff")
        if any(item.available_at > self.cutoff_at for item in self.context_bindings):
            raise ValueError("accepted context must be available by the exact cutoff")
        _derive_identity(
            self,
            prefix="reasoning_acceptance",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


class ContextUseReceiptV1Alpha1(_StrictFrozenContract):
    """Per-context selection, injection, and output-reference attribution."""

    contract: Literal["ace.core.context-use-receipt/v1alpha1"] = CONTEXT_USE_RECEIPT_VERSION
    product_id: str
    request_id: str
    request_digest: str
    result_id: str
    result_digest: str
    context: ContextBindingV1Alpha1
    selected: Literal[True] = True
    injected: Literal[True] = True
    output_referenced: bool
    recorded_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "request_id", "result_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("request_digest", "result_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("recorded_at")
    @classmethod
    def validate_recorded_at(cls, value: datetime) -> datetime:
        return _aware(value, name="recorded_at")

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="receipt_id") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive_identity(
            self,
            prefix="context_use",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


class ReasoningTerminalReceiptV1Alpha1(_StrictFrozenContract):
    """Content-free terminal proof for one exact accepted attempt."""

    contract: Literal["ace.core.reasoning-terminal-receipt/v1alpha1"] = REASONING_TERMINAL_RECEIPT_VERSION
    disposition: Literal["completed"] = "completed"
    product_id: str
    attempt_key: str
    request_id: str
    request_digest: str
    acceptance: ReceiptReferenceV1Alpha1
    result_id: str
    result_digest: str
    route: ProviderRouteV1Alpha1
    usage: ProviderUsageV1Alpha1
    context_uses: tuple[ReceiptReferenceV1Alpha1, ...] = Field(
        min_length=1,
        max_length=MAX_CONTEXT_ITEMS,
    )
    capability_use: ReceiptReferenceV1Alpha1
    authority_use: ReceiptReferenceV1Alpha1
    completed_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id", "attempt_key", "request_id", "result_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("request_digest", "result_digest", "receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return _digest(value, name=info.field_name) if value is not None else None

    @field_validator("completed_at")
    @classmethod
    def validate_completed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="completed_at")

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str | None) -> str | None:
        return _bounded(value, name="receipt_id") if value is not None else None

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        ids = [item.receipt_id for item in self.context_uses]
        if len(ids) != len(set(ids)):
            raise ValueError("terminal context-use references must be unique")
        _derive_identity(
            self,
            prefix="reasoning_terminal",
            id_field="receipt_id",
            digest_field="receipt_digest",
        )
        return self


class ReasoningProvider(Protocol):
    """Host-supplied provider port.  It exposes no tools or actions."""

    @property
    def artifact_identity(self) -> CapabilityArtifactIdentityV1Alpha1: ...

    async def execute(
        self,
        request: ProviderExecutionRequestV1Alpha1,
    ) -> ProviderStructuredOutputV1Alpha1: ...


@dataclass(frozen=True, slots=True)
class GovernedReasoningOutcome:
    """Exact accepted and terminal material returned by execution or replay."""

    acceptance: ReasoningAcceptanceReceiptV1Alpha1
    result: StructuredFinalResultV1Alpha1
    context_uses: tuple[ContextUseReceiptV1Alpha1, ...]
    terminal: ReasoningTerminalReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool


@dataclass(frozen=True, slots=True)
class ReasoningUseAuthorization:
    """Current actor-scoped use attestation, separate from immutable command identity."""

    capability_use: CapabilityUseReceiptV1Alpha1
    authority_use: AuthorityUseReceiptV1Alpha1


@dataclass(frozen=True, slots=True)
class _GovernedActionAuthorizationMaterial:
    authorization: _GovernedActionAuthorizationReceiptV1Alpha1
    capability_use: CapabilityUseReceiptV1Alpha1
    authority_use: AuthorityUseReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool

    @property
    def reference(self) -> ReceiptReferenceV1Alpha1:
        return _receipt_reference(self.authorization)

    def projection(self) -> GovernedActionAuthorizationProjection:
        return GovernedActionAuthorizationProjection(
            authorization_ref=self.reference,
            authorized_at=self.authorization.authorized_at,
            state_preconditions=self.authorization.state_preconditions,
        )


class GovernedActionAuthorizationProjection(_StrictFrozenContract):
    """Safe content-free projection of private action authorization material."""

    contract: Literal["ace.core.governed-action-authorization-projection/v1alpha1"] = (
        GOVERNED_ACTION_AUTHORIZATION_PROJECTION_VERSION
    )
    authorization_ref: ReceiptReferenceV1Alpha1
    authorized_at: datetime
    state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(
        min_length=2,
        max_length=64,
    )

    @field_validator("authorized_at")
    @classmethod
    def validate_authorized_at(cls, value: datetime) -> datetime:
        return _aware(value, name="authorized_at")

    @field_validator("state_preconditions")
    @classmethod
    def validate_preconditions(
        cls,
        value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        identities = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError("authorization projection preconditions must be unique")
        products = {item.product_id for item in value}
        if len(products) != 1:
            raise ValueError("authorization projection preconditions must share one product")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))


class GovernedReasoningError(RuntimeError):
    """Governed execution or replay failed closed."""


class GovernedReasoningReplayConflict(GovernedReasoningError):
    """A stable attempt key already binds different request material."""


class GovernedReasoningOrphanedAttempt(GovernedReasoningError):
    """An accepted attempt lacks a terminal commit and must not be resumed."""


def _record(
    value: Any,
    *,
    product_id: str,
    record_kind: str,
    record_key: str,
    as_of: datetime,
    available_at: datetime,
    processing_order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=REASONING_RECORD_SPACE,
        record_kind=record_kind,
        record_key=record_key,
        payload_contract=value.contract,
        payload=value.model_dump(mode="python"),
        as_of=as_of,
        available_at=available_at,
        processing_order=processing_order,
    )


def _transaction_key(attempt_key: str, stage: str) -> str:
    return f"reasoning_{stage}:{canonical_hash([attempt_key, stage])[:32]}"


def _authorization_transaction_key(authorization_key: str) -> str:
    return f"action_authorization:{canonical_hash([authorization_key, 'authorize'])[:32]}"


def _authorization_use_record_key(
    authorization_key: str,
    *,
    record_kind: Literal["capability_use", "authority_use"],
    receipt_id: str,
) -> str:
    """Scope an otherwise reusable use receipt to one private authorization attempt."""

    digest = canonical_hash([authorization_key, record_kind, receipt_id])
    return f"action_authorization_use:{digest[:32]}"


def _resolved_authorization_key(
    request: GovernedActionAuthorizationRequestV1Alpha1,
    capability: CapabilityUseReceiptV1Alpha1,
    authority: AuthorityUseReceiptV1Alpha1,
) -> str:
    digest = canonical_hash(
        {
            "authorization_family_key": request.authorization_key,
            "request_digest": request.request_digest,
            "authentication_receipt_ref": (request.authenticated_context.authentication_receipt_ref),
            "authentication_receipt_digest": (request.authenticated_context.authentication_receipt_digest),
            "operation_binding_digest": request.execution_binding.binding_digest,
            "operation_binding_head": request.execution_binding.state_head_precondition.model_dump(mode="json"),
            "required_state_preconditions": [
                item.model_dump(mode="json") for item in request.required_state_preconditions
            ],
            "capability_head": capability.state_head_precondition.model_dump(mode="json"),
            "authority_head": authority.state_head_precondition.model_dump(mode="json"),
        }
    )
    return f"resolved_action_authorization:{digest[:32]}"


def _unique_preconditions(
    *groups: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
    by_identity: dict[tuple[str, str, str], GovernedStateHeadPreconditionV1Alpha1] = {}
    for item in (item for group in groups for item in group):
        identity = (item.state_kind, item.product_id, item.state_id)
        prior = by_identity.setdefault(identity, item)
        if prior != item:
            raise GovernedReasoningError("runtime use resolved conflicting exact state heads")
    return tuple(sorted(by_identity.values(), key=lambda item: (item.state_kind, item.product_id, item.state_id)))


class GovernedReasoningService:
    """Replay-first, append-only application service for opaque structured reasoning."""

    def __init__(
        self,
        *,
        store: ImmutableRecordStore,
        runtime_use: RuntimeUseResolver,
        provider: ReasoningProvider,
        clock: Callable[[], datetime],
    ) -> None:
        self.store = store
        self.runtime_use = runtime_use
        self.provider = provider
        self.clock = clock

    @staticmethod
    def _revalidate_request(
        request: GovernedReasoningRequestV1Alpha1,
    ) -> GovernedReasoningRequestV1Alpha1:
        try:
            validated = GovernedReasoningRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except Exception:
            validated = None
        if validated is None:
            raise GovernedReasoningError("reasoning request failed exact revalidation")
        return validated

    def _now(self, *, label: str) -> datetime:
        try:
            return _aware(self.clock(), name=label)
        except Exception:
            raise GovernedReasoningError("service clock must return a timezone-aware value") from None

    @staticmethod
    def _assert_authenticated(
        context: AuthenticatedRuntimeContextV1Alpha1,
        evaluated_at: datetime,
    ) -> None:
        if not context.authenticated_at <= evaluated_at < context.expires_at:
            raise GovernedReasoningError("current authenticated context is absent, expired, or not yet valid")

    async def _validate_context(self, request: GovernedReasoningRequestV1Alpha1) -> None:
        for item in request.context_items:
            try:
                stored = await self.store.load_record(
                    item.storage_id,
                    product_id=request.product_id,
                    record_space=item.record_space,
                    record_kind=item.record_kind,
                )
            except Exception:
                stored = _LOAD_FAILED
            if stored is _LOAD_FAILED:
                raise GovernedReasoningError("selected record load failed closed")
            if stored is None:
                raise GovernedReasoningError("an exact selected record is missing or outside product scope")
            try:
                reference = stored.reference()
                stored_content = canonical_json(_JSON_OBJECT.dump_python(stored.payload, mode="json"))
            except Exception:
                raise GovernedReasoningError("selected record content failed exact revalidation") from None
            if (
                stored.record_key != item.record_key
                or stored.payload_contract != item.payload_contract
                or reference.storage_id != item.storage_id
                or reference.material_hash != item.material_digest
                or stored.as_of != item.as_of
                or stored.available_at != item.available_at
                or stored_content != item.content_json
                or stored.as_of > request.cutoff_at
                or stored.available_at > request.cutoff_at
            ):
                raise GovernedReasoningError(
                    "selected record identity, digest, cutoff, availability, or content is not exact"
                )

    async def _capability_use(
        self,
        request: GovernedReasoningRequestV1Alpha1,
        *,
        evaluated_at: datetime,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1 | None = None,
        execution_binding: ReasoningExecutionBindingV1Alpha1 | None = None,
    ) -> CapabilityUseReceiptV1Alpha1:
        context = authenticated_context or request.authenticated_context
        artifact = request.artifact if execution_binding is None else execution_binding.artifact
        configuration_ref = (
            request.configuration_ref if execution_binding is None else execution_binding.configuration_ref
        )
        state_ref = capability_state_ref_for_artifact(artifact)
        try:
            raw = await self.runtime_use.resolve_capability_use(
                context=context,
                use_subject_ref=str(request.request_id),
                use_subject_digest=str(request.request_digest),
                operation=request.operation,
                artifact=artifact,
                capability_state_ref=state_ref,
                configuration_ref=configuration_ref,
                evaluated_at=evaluated_at,
            )
            receipt = CapabilityUseReceiptV1Alpha1.model_validate(raw.model_dump(mode="python"))
        except Exception:
            receipt = None
        if receipt is None:
            raise GovernedReasoningError("current capability use failed closed")
        if (
            receipt.product_id != request.product_id
            or receipt.actor_ref != context.actor_ref
            or receipt.authenticated_context != context
            or receipt.use_subject_ref != request.request_id
            or receipt.use_subject_digest != request.request_digest
            or receipt.operation != request.operation
            or receipt.artifact != artifact
            or receipt.capability_state_ref != state_ref
            or receipt.configuration_ref != configuration_ref
            or receipt.evaluated_at != evaluated_at
            or receipt.resolved_at != evaluated_at
        ):
            raise GovernedReasoningError("capability use did not resolve the exact actor request and artifact")
        return receipt

    async def _authority_use(
        self,
        request: GovernedReasoningRequestV1Alpha1,
        *,
        evaluated_at: datetime,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1 | None = None,
        execution_binding: ReasoningExecutionBindingV1Alpha1 | None = None,
    ) -> AuthorityUseReceiptV1Alpha1:
        context = authenticated_context or request.authenticated_context
        authority = request.authority if execution_binding is None else execution_binding.authority
        grant_ref = request.grant_ref if execution_binding is None else execution_binding.grant_ref
        try:
            raw = await self.runtime_use.resolve_authority_use(
                context=context,
                use_subject_ref=str(request.request_id),
                use_subject_digest=str(request.request_digest),
                operation=request.operation,
                authority=authority,
                grant_ref=grant_ref,
                evaluated_at=evaluated_at,
            )
            receipt = AuthorityUseReceiptV1Alpha1.model_validate(raw.model_dump(mode="python"))
        except Exception:
            receipt = None
        if receipt is None:
            raise GovernedReasoningError("current authority use failed closed")
        if (
            receipt.product_id != request.product_id
            or receipt.actor_ref != context.actor_ref
            or receipt.authenticated_context != context
            or receipt.use_subject_ref != request.request_id
            or receipt.use_subject_digest != request.request_digest
            or receipt.operation != request.operation
            or receipt.authority != authority
            or receipt.grant_ref != grant_ref
            or receipt.evaluated_at != evaluated_at
            or (receipt.expires_at is not None and receipt.expires_at <= evaluated_at)
        ):
            raise GovernedReasoningError("authority use did not resolve the exact actor request and grant")
        return receipt

    async def _load_record(self, reference, *, kind: str) -> ImmutableRecordV1:
        try:
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=reference.product_id,
                record_space=reference.record_space,
                record_kind=kind,
            )
        except Exception:
            stored = _LOAD_FAILED
        if stored is _LOAD_FAILED:
            raise GovernedReasoningError("durable reasoning record load failed closed")
        if stored is None or stored.reference() != reference:
            raise GovernedReasoningError("durable reasoning transaction references missing or changed material")
        return stored

    async def _load_transaction(
        self,
        *,
        product_id: str,
        attempt_key: str,
        stage: str,
    ) -> AppendOnlyTransactionReceiptV1 | None:
        try:
            receipt = await self.store.load_transaction_receipt(
                product_id=product_id,
                record_space=REASONING_RECORD_SPACE,
                transaction_key=_transaction_key(attempt_key, stage),
            )
        except Exception:
            receipt = _LOAD_FAILED
        if receipt is _LOAD_FAILED:
            raise GovernedReasoningError("durable reasoning transaction load failed closed")
        return receipt

    async def _load_acceptance(
        self,
        *,
        product_id: str,
        attempt_key: str,
    ) -> (
        tuple[
            ReasoningAcceptanceReceiptV1Alpha1,
            CapabilityUseReceiptV1Alpha1,
            AuthorityUseReceiptV1Alpha1,
            AppendOnlyTransactionReceiptV1,
        ]
        | None
    ):
        receipt = await self._load_transaction(
            product_id=product_id,
            attempt_key=attempt_key,
            stage="acceptance",
        )
        if receipt is None:
            return None
        if len(receipt.records) != 3 or tuple(item.record_kind for item in receipt.records) != (
            "capability_use",
            "authority_use",
            "request_acceptance",
        ):
            raise GovernedReasoningError("acceptance transaction has an invalid exact record shape")
        capability_record, authority_record, acceptance_record = [
            await self._load_record(reference, kind=reference.record_kind) for reference in receipt.records
        ]
        try:
            reconstructed = AppendOnlyTransactionRequestV1(
                product_id=product_id,
                record_space=REASONING_RECORD_SPACE,
                transaction_key=_transaction_key(attempt_key, "acceptance"),
                records=(capability_record, authority_record, acceptance_record),
                submitted_at=receipt.committed_at,
                governed_state_preconditions=receipt.governed_state_preconditions,
            )
        except Exception:
            reconstructed = None
        if reconstructed is None or receipt != reconstructed.receipt():
            raise GovernedReasoningError("acceptance transaction request identity failed closed")
        try:
            capability = CapabilityUseReceiptV1Alpha1.model_validate(capability_record.payload)
            authority = AuthorityUseReceiptV1Alpha1.model_validate(authority_record.payload)
            acceptance = ReasoningAcceptanceReceiptV1Alpha1.model_validate(acceptance_record.payload)
        except Exception:
            raise GovernedReasoningError("acceptance transaction failed exact contract replay") from None
        if (
            acceptance.product_id != product_id
            or acceptance.attempt_key != attempt_key
            or capability.receipt_id != acceptance.capability_use.receipt_id
            or capability.receipt_digest != acceptance.capability_use.receipt_digest
            or authority.receipt_id != acceptance.authority_use.receipt_id
            or authority.receipt_digest != acceptance.authority_use.receipt_digest
            or capability.product_id != acceptance.product_id
            or authority.product_id != acceptance.product_id
            or capability.actor_ref != acceptance.actor_ref
            or authority.actor_ref != acceptance.actor_ref
            or capability.authenticated_context != authority.authenticated_context
            or capability.authenticated_context.product_id != acceptance.product_id
            or capability.authenticated_context.actor_ref != acceptance.actor_ref
            or capability.use_subject_ref != acceptance.request_id
            or authority.use_subject_ref != acceptance.request_id
            or capability.use_subject_digest != acceptance.request_digest
            or authority.use_subject_digest != acceptance.request_digest
            or capability.operation != REASONING_OPERATION
            or authority.operation != REASONING_OPERATION
            or capability.evaluated_at != acceptance.accepted_at
            or capability.resolved_at != acceptance.accepted_at
            or authority.evaluated_at != acceptance.accepted_at
            or (authority.expires_at is not None and authority.expires_at <= acceptance.accepted_at)
            or not (
                capability.authenticated_context.authenticated_at
                <= acceptance.accepted_at
                < capability.authenticated_context.expires_at
            )
            or acceptance.cutoff_at > acceptance.accepted_at
            or capability.state_head_precondition not in acceptance.state_preconditions
            or authority.state_head_precondition not in acceptance.state_preconditions
            or receipt.governed_state_preconditions != acceptance.state_preconditions
            or receipt.committed_at != acceptance.accepted_at
            or capability_record.record_key != capability.receipt_id
            or capability_record.payload_contract != capability.contract
            or authority_record.record_key != authority.receipt_id
            or authority_record.payload_contract != authority.contract
            or acceptance_record.record_key != acceptance.receipt_id
            or acceptance_record.payload_contract != acceptance.contract
            or any(
                record.as_of != acceptance.cutoff_at
                for record in (
                    capability_record,
                    authority_record,
                    acceptance_record,
                )
            )
            or any(
                record.available_at != acceptance.accepted_at
                for record in (
                    capability_record,
                    authority_record,
                    acceptance_record,
                )
            )
        ):
            raise GovernedReasoningError("acceptance transaction crossed exact attempt material")
        return acceptance, capability, authority, receipt

    async def _load_terminal(
        self,
        *,
        product_id: str,
        attempt_key: str,
    ) -> GovernedReasoningOutcome | None:
        receipt = await self._load_transaction(
            product_id=product_id,
            attempt_key=attempt_key,
            stage="terminal",
        )
        if receipt is None:
            return None
        accepted = await self._load_acceptance(product_id=product_id, attempt_key=attempt_key)
        if accepted is None:
            raise GovernedReasoningError("terminal transaction is missing durable acceptance")
        acceptance = accepted[0]
        if len(receipt.records) < 3:
            raise GovernedReasoningError("terminal transaction is missing required exact records")
        kinds = tuple(item.record_kind for item in receipt.records)
        if (
            kinds[0] != "structured_result"
            or kinds[-1] != "terminal_receipt"
            or any(kind != "context_use" for kind in kinds[1:-1])
        ):
            raise GovernedReasoningError("terminal transaction has an invalid exact record shape")
        records = [await self._load_record(reference, kind=reference.record_kind) for reference in receipt.records]
        try:
            reconstructed = AppendOnlyTransactionRequestV1(
                product_id=product_id,
                record_space=REASONING_RECORD_SPACE,
                transaction_key=_transaction_key(attempt_key, "terminal"),
                records=tuple(records),
                submitted_at=receipt.committed_at,
                governed_state_preconditions=receipt.governed_state_preconditions,
            )
        except Exception:
            reconstructed = None
        if reconstructed is None or receipt != reconstructed.receipt():
            raise GovernedReasoningError("terminal transaction request identity failed closed")
        try:
            result = StructuredFinalResultV1Alpha1.model_validate(records[0].payload)
            uses = tuple(ContextUseReceiptV1Alpha1.model_validate(item.payload) for item in records[1:-1])
            terminal = ReasoningTerminalReceiptV1Alpha1.model_validate(records[-1].payload)
        except Exception:
            raise GovernedReasoningError("terminal transaction failed exact contract replay") from None
        accepted_capability = accepted[1]
        accepted_authority = accepted[2]
        uses_by_context = {item.context.context_id: item for item in uses}
        accepted_bindings = {item.context_id: item for item in acceptance.context_bindings}
        if (
            terminal.product_id != product_id
            or terminal.attempt_key != attempt_key
            or terminal.request_id != acceptance.request_id
            or terminal.request_digest != acceptance.request_digest
            or terminal.acceptance != _receipt_reference(acceptance)
            or terminal.result_id != result.result_id
            or terminal.result_digest != result.result_digest
            or terminal.route != result.route
            or terminal.usage != result.usage
            or terminal.context_uses != tuple(_receipt_reference(item) for item in uses)
            or terminal.capability_use != _receipt_reference(accepted_capability)
            or terminal.authority_use != _receipt_reference(accepted_authority)
            or result.product_id != acceptance.product_id
            or result.attempt_key != acceptance.attempt_key
            or result.request_id != acceptance.request_id
            or result.request_digest != acceptance.request_digest
            or result.artifact != accepted_capability.artifact
            or result.completed_at != terminal.completed_at
            or terminal.completed_at < acceptance.accepted_at
            or acceptance.cutoff_at > terminal.completed_at
            or not (
                accepted_capability.authenticated_context.authenticated_at
                <= terminal.completed_at
                < accepted_capability.authenticated_context.expires_at
            )
            or (accepted_authority.expires_at is not None and terminal.completed_at >= accepted_authority.expires_at)
            or len(uses) != len(accepted_bindings)
            or len(uses_by_context) != len(uses)
            or set(uses_by_context) != set(accepted_bindings)
            or any(
                use.product_id != acceptance.product_id
                or use.request_id != acceptance.request_id
                or use.request_digest != acceptance.request_digest
                or use.result_id != result.result_id
                or use.result_digest != result.result_digest
                or use.context != accepted_bindings[context_id]
                or use.recorded_at != terminal.completed_at
                for context_id, use in uses_by_context.items()
            )
            or set(result.referenced_context_ids)
            != {context_id for context_id, use in uses_by_context.items() if use.output_referenced}
            or receipt.governed_state_preconditions != acceptance.state_preconditions
            or receipt.committed_at != terminal.completed_at
            or records[0].record_key != result.result_id
            or records[0].payload_contract != result.contract
            or records[-1].record_key != terminal.receipt_id
            or records[-1].payload_contract != terminal.contract
            or any(
                record.record_key != use.receipt_id or record.payload_contract != use.contract
                for record, use in zip(records[1:-1], uses, strict=True)
            )
            or any(record.as_of != acceptance.cutoff_at for record in records)
            or any(record.available_at != terminal.completed_at for record in records)
        ):
            raise GovernedReasoningError("terminal replay crossed exact acceptance, result, or use material")
        return GovernedReasoningOutcome(
            acceptance=acceptance,
            result=result,
            context_uses=uses,
            terminal=terminal,
            transaction_receipt=receipt,
            replayed=True,
        )

    async def _execute_provider(
        self,
        request: GovernedReasoningRequestV1Alpha1,
        *,
        started_at: datetime,
    ) -> ProviderStructuredOutputV1Alpha1:
        try:
            installed = CapabilityArtifactIdentityV1Alpha1.model_validate(
                self.provider.artifact_identity.model_dump(mode="python")
            )
        except Exception:
            raise GovernedReasoningError("provider lacks an exact installed artifact identity") from None
        if installed != request.artifact:
            raise GovernedReasoningError("installed provider does not match the exact authorized artifact")
        execution = ProviderExecutionRequestV1Alpha1(
            product_id=request.product_id,
            request_id=str(request.request_id),
            request_digest=str(request.request_digest),
            attempt_key=request.attempt_key,
            instruction_json=request.instruction_json,
            context_items=request.context_items,
            cutoff_at=request.cutoff_at,
            started_at=started_at,
        )
        try:
            raw = await self.provider.execute(execution)
            output = ProviderStructuredOutputV1Alpha1.model_validate(raw.model_dump(mode="python"))
        except Exception:
            raise GovernedReasoningError("provider structured execution failed closed") from None
        selected_ids = {str(item.context_id) for item in request.context_items}
        unknown = set(output.referenced_context_ids) - selected_ids
        if unknown:
            raise GovernedReasoningError("provider output attributed unknown context identities")
        return output

    @staticmethod
    def _assert_acceptance_matches_request(
        request: GovernedReasoningRequestV1Alpha1,
        accepted: tuple[
            ReasoningAcceptanceReceiptV1Alpha1,
            CapabilityUseReceiptV1Alpha1,
            AuthorityUseReceiptV1Alpha1,
            AppendOnlyTransactionReceiptV1,
        ],
    ) -> None:
        acceptance, capability, authority, _ = accepted
        expected_preconditions = _unique_preconditions(
            request.required_state_preconditions,
            (capability.state_head_precondition,),
            (authority.state_head_precondition,),
        )
        if (
            acceptance.product_id != request.product_id
            or acceptance.attempt_key != request.attempt_key
            or acceptance.request_id != request.request_id
            or acceptance.request_digest != request.request_digest
            or acceptance.actor_ref != request.authenticated_context.actor_ref
            or acceptance.cutoff_at != request.cutoff_at
            or acceptance.instruction_digest != f"sha256:{canonical_hash(request.instruction_json)}"
            or acceptance.context_bindings
            != tuple(ContextBindingV1Alpha1.from_item(item) for item in request.context_items)
            or capability.product_id != request.product_id
            or capability.actor_ref != request.authenticated_context.actor_ref
            or capability.authenticated_context != request.authenticated_context
            or capability.use_subject_ref != request.request_id
            or capability.use_subject_digest != request.request_digest
            or capability.operation != request.operation
            or capability.artifact != request.artifact
            or capability.capability_state_ref != capability_state_ref_for_artifact(request.artifact)
            or capability.configuration_ref != request.configuration_ref
            or authority.product_id != request.product_id
            or authority.actor_ref != request.authenticated_context.actor_ref
            or authority.authenticated_context != request.authenticated_context
            or authority.use_subject_ref != request.request_id
            or authority.use_subject_digest != request.request_digest
            or authority.operation != request.operation
            or authority.authority != request.authority
            or authority.grant_ref != request.grant_ref
            or acceptance.state_preconditions != expected_preconditions
        ):
            raise GovernedReasoningReplayConflict("attempt key acceptance does not match the exact supplied request")

    async def authorize_use(
        self,
        request: GovernedReasoningRequestV1Alpha1,
        *,
        evaluated_at: datetime,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1 | None = None,
        execution_binding: ReasoningExecutionBindingV1Alpha1 | None = None,
    ) -> ReasoningUseAuthorization:
        """Resolve current actor-scoped use without changing immutable command identity."""

        validated = self._revalidate_request(request)
        try:
            context = AuthenticatedRuntimeContextV1Alpha1.model_validate(
                (authenticated_context or validated.authenticated_context).model_dump(mode="python")
            )
            binding = (
                None
                if execution_binding is None
                else ReasoningExecutionBindingV1Alpha1.model_validate(execution_binding.model_dump(mode="python"))
            )
            current_at = _aware(evaluated_at, name="reasoning use evaluation")
        except Exception:
            raise GovernedReasoningError("current reasoning use coordinates failed exact revalidation") from None
        if (
            context.product_id != validated.product_id
            or context.actor_ref != validated.authenticated_context.actor_ref
            or (binding is not None and binding.product_id != validated.product_id)
        ):
            raise GovernedReasoningError("current reasoning use crossed exact product or principal scope")
        self._assert_authenticated(context, current_at)
        capability = await self._capability_use(
            validated,
            evaluated_at=current_at,
            authenticated_context=context,
            execution_binding=binding,
        )
        authority = await self._authority_use(
            validated,
            evaluated_at=current_at,
            authenticated_context=context,
            execution_binding=binding,
        )
        return ReasoningUseAuthorization(
            capability_use=capability,
            authority_use=authority,
        )

    @staticmethod
    def _revalidate_action_request(
        request: GovernedActionAuthorizationRequestV1Alpha1,
    ) -> GovernedActionAuthorizationRequestV1Alpha1:
        try:
            return GovernedActionAuthorizationRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except Exception:
            raise GovernedReasoningError("governed action authorization request failed exact revalidation") from None

    async def _resolve_action_uses(
        self,
        request: GovernedActionAuthorizationRequestV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> tuple[CapabilityUseReceiptV1Alpha1, AuthorityUseReceiptV1Alpha1]:
        context = request.authenticated_context
        binding = request.execution_binding
        capability_state_ref = capability_state_ref_for_artifact(binding.artifact)
        try:
            raw_capability = await self.runtime_use.resolve_capability_use(
                context=context,
                use_subject_ref=request.subject_ref,
                use_subject_digest=request.subject_digest,
                operation=request.operation,
                artifact=binding.artifact,
                capability_state_ref=capability_state_ref,
                configuration_ref=binding.configuration_ref,
                evaluated_at=evaluated_at,
            )
            capability = CapabilityUseReceiptV1Alpha1.model_validate(raw_capability.model_dump(mode="python"))
            raw_authority = await self.runtime_use.resolve_authority_use(
                context=context,
                use_subject_ref=request.subject_ref,
                use_subject_digest=request.subject_digest,
                operation=request.operation,
                authority=binding.authority,
                grant_ref=binding.grant_ref,
                evaluated_at=evaluated_at,
            )
            authority = AuthorityUseReceiptV1Alpha1.model_validate(raw_authority.model_dump(mode="python"))
        except Exception:
            raise GovernedReasoningError("current governed action use failed closed") from None
        if (
            capability.product_id != request.product_id
            or authority.product_id != request.product_id
            or capability.actor_ref != context.actor_ref
            or authority.actor_ref != context.actor_ref
            or capability.authenticated_context != context
            or authority.authenticated_context != context
            or capability.use_subject_ref != request.subject_ref
            or authority.use_subject_ref != request.subject_ref
            or capability.use_subject_digest != request.subject_digest
            or authority.use_subject_digest != request.subject_digest
            or capability.operation != request.operation
            or authority.operation != request.operation
            or capability.artifact != binding.artifact
            or capability.capability_state_ref != capability_state_ref
            or capability.configuration_ref != binding.configuration_ref
            or authority.authority != binding.authority
            or authority.grant_ref != binding.grant_ref
            or capability.evaluated_at != evaluated_at
            or capability.resolved_at != evaluated_at
            or authority.evaluated_at != evaluated_at
            or (authority.expires_at is not None and authority.expires_at <= evaluated_at)
        ):
            raise GovernedReasoningError(
                "governed action use did not bind the exact principal, operation, subject, and execution selection"
            )
        return capability, authority

    async def _load_action_authorization(
        self,
        request: GovernedActionAuthorizationRequestV1Alpha1,
        *,
        authorization_key: str,
    ) -> _GovernedActionAuthorizationMaterial | None:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=request.product_id,
                record_space=REASONING_RECORD_SPACE,
                transaction_key=_authorization_transaction_key(authorization_key),
            )
        except Exception:
            raise GovernedReasoningError("durable action authorization load failed closed") from None
        if transaction is None:
            return None
        if tuple(item.record_kind for item in transaction.records) != (
            "capability_use",
            "authority_use",
            "action_authorization",
        ):
            raise GovernedReasoningError("durable action authorization has an invalid exact record shape")
        records = tuple(
            [
                await self._load_record(transaction.records[0], kind="capability_use"),
                await self._load_record(transaction.records[1], kind="authority_use"),
                await self._load_record(transaction.records[2], kind="action_authorization"),
            ]
        )
        try:
            capability = CapabilityUseReceiptV1Alpha1.model_validate(records[0].payload)
            authority = AuthorityUseReceiptV1Alpha1.model_validate(records[1].payload)
            authorization = _GovernedActionAuthorizationReceiptV1Alpha1.model_validate(records[2].payload)
            historical_request = _historical_action_request(
                authorization,
                requested_at=records[2].as_of,
            )
            reconstructed = AppendOnlyTransactionRequestV1(
                product_id=request.product_id,
                record_space=REASONING_RECORD_SPACE,
                transaction_key=_authorization_transaction_key(authorization_key),
                records=records,
                submitted_at=transaction.committed_at,
                governed_state_preconditions=transaction.governed_state_preconditions,
            )
        except Exception:
            raise GovernedReasoningError("durable action authorization failed exact replay") from None
        expected_preconditions = _unique_preconditions(
            request.required_state_preconditions,
            (request.execution_binding.state_head_precondition,),
            (capability.state_head_precondition,),
            (authority.state_head_precondition,),
        )
        if (
            transaction != reconstructed.receipt()
            or transaction.committed_at != authorization.authorized_at
            or authorization.product_id != request.product_id
            or authorization.authorization_key != authorization_key
            or authorization.authorization_family_key != request.authorization_key
            or historical_request != request
            or authorization.request_id != request.request_id
            or authorization.request_digest != request.request_digest
            or authorization.operation != request.operation
            or authorization.subject_ref != request.subject_ref
            or authorization.subject_digest != request.subject_digest
            or authorization.capability_use != capability
            or authorization.authority_use != authority
            or authorization.authenticated_context != request.authenticated_context
            or authorization.execution_binding != request.execution_binding
            or authorization.required_state_preconditions != request.required_state_preconditions
            or authorization.state_preconditions != expected_preconditions
            or authorization_key != _resolved_authorization_key(request, capability, authority)
            or capability.product_id != request.product_id
            or authority.product_id != request.product_id
            or capability.actor_ref != request.authenticated_context.actor_ref
            or authority.actor_ref != request.authenticated_context.actor_ref
            or capability.authenticated_context != request.authenticated_context
            or authority.authenticated_context != request.authenticated_context
            or capability.use_subject_ref != request.subject_ref
            or authority.use_subject_ref != request.subject_ref
            or capability.use_subject_digest != request.subject_digest
            or authority.use_subject_digest != request.subject_digest
            or capability.operation != request.operation
            or authority.operation != request.operation
            or capability.artifact != request.execution_binding.artifact
            or capability.configuration_ref != request.execution_binding.configuration_ref
            or authority.authority != request.execution_binding.authority
            or authority.grant_ref != request.execution_binding.grant_ref
            or capability.evaluated_at > authorization.authorized_at
            or authority.evaluated_at > authorization.authorized_at
            or not (
                request.authenticated_context.authenticated_at
                <= authorization.authorized_at
                < request.authenticated_context.expires_at
            )
            or (authority.expires_at is not None and authorization.authorized_at >= authority.expires_at)
        ):
            raise GovernedReasoningError("durable action authorization crossed its exact request or use closure")
        return _GovernedActionAuthorizationMaterial(
            authorization=authorization,
            capability_use=capability,
            authority_use=authority,
            transaction_receipt=transaction,
            replayed=True,
        )

    async def authorize_action(
        self,
        request: GovernedActionAuthorizationRequestV1Alpha1,
    ) -> GovernedActionAuthorizationProjection:
        """Resolve and durably receipt one exact opaque operation and subject."""

        validated = self._revalidate_action_request(request)
        resolved_at = self._now(label="governed action resolution")
        if resolved_at < validated.requested_at:
            raise GovernedReasoningError("governed action resolution cannot predate its request")
        self._assert_authenticated(validated.authenticated_context, resolved_at)
        capability, authority = await self._resolve_action_uses(
            validated,
            evaluated_at=resolved_at,
        )
        authorization_key = _resolved_authorization_key(
            validated,
            capability,
            authority,
        )
        replay = await self._load_action_authorization(
            validated,
            authorization_key=authorization_key,
        )
        if replay is not None:
            return replay.projection()
        authorized_at = self._now(label="governed action durable authorization")
        if authorized_at < resolved_at:
            raise GovernedReasoningError("governed action authorization cannot predate its resolution")
        self._assert_authenticated(validated.authenticated_context, authorized_at)
        if authority.expires_at is not None and authorized_at >= authority.expires_at:
            raise GovernedReasoningError("governed action authority expired before durable authorization")
        state_preconditions = _unique_preconditions(
            validated.required_state_preconditions,
            (validated.execution_binding.state_head_precondition,),
            (capability.state_head_precondition,),
            (authority.state_head_precondition,),
        )
        authorization = _GovernedActionAuthorizationReceiptV1Alpha1(
            product_id=validated.product_id,
            authorization_key=authorization_key,
            authorization_family_key=validated.authorization_key,
            request_id=str(validated.request_id),
            request_digest=str(validated.request_digest),
            operation=validated.operation,
            subject_ref=validated.subject_ref,
            subject_digest=validated.subject_digest,
            authenticated_context=validated.authenticated_context,
            execution_binding=validated.execution_binding,
            capability_use=capability,
            authority_use=authority,
            required_state_preconditions=validated.required_state_preconditions,
            state_preconditions=state_preconditions,
            authorized_at=authorized_at,
        )
        values = (
            (
                capability,
                "capability_use",
                _authorization_use_record_key(
                    authorization_key,
                    record_kind="capability_use",
                    receipt_id=str(capability.receipt_id),
                ),
            ),
            (
                authority,
                "authority_use",
                _authorization_use_record_key(
                    authorization_key,
                    record_kind="authority_use",
                    receipt_id=str(authority.receipt_id),
                ),
            ),
            (authorization, "action_authorization", str(authorization.receipt_id)),
        )
        append_request = AppendOnlyTransactionRequestV1(
            product_id=validated.product_id,
            record_space=REASONING_RECORD_SPACE,
            transaction_key=_authorization_transaction_key(authorization_key),
            records=tuple(
                _record(
                    value,
                    product_id=validated.product_id,
                    record_kind=kind,
                    record_key=key,
                    as_of=validated.requested_at,
                    available_at=authorized_at,
                    processing_order=index,
                )
                for index, (value, kind, key) in enumerate(values)
            ),
            submitted_at=authorized_at,
            governed_state_preconditions=state_preconditions,
        )
        try:
            transaction = await self.store.append(append_request)
        except ImmutableRecordReplayConflict:
            replay = await self._load_action_authorization(
                validated,
                authorization_key=authorization_key,
            )
            if replay is not None:
                return replay.projection()
            raise GovernedReasoningError("concurrent action authorization failed exact replay") from None
        except Exception:
            raise GovernedReasoningError("durable action authorization failed closed") from None
        if transaction != append_request.receipt():
            raise GovernedReasoningError("durable action authorization receipt is not exact")
        return _GovernedActionAuthorizationMaterial(
            authorization=authorization,
            capability_use=capability,
            authority_use=authority,
            transaction_receipt=transaction,
            replayed=False,
        ).projection()

    async def verify_action_authorization(
        self,
        request: GovernedActionAuthorizationRequestV1Alpha1,
        *,
        expected: ReceiptReferenceV1Alpha1,
    ) -> GovernedActionAuthorizationProjection:
        """Verify exact historical private authorization without returning content."""

        validated = self._revalidate_action_request(request)
        projection = await self.verify_action_reference(
            product_id=validated.product_id,
            operation=validated.operation,
            subject_ref=validated.subject_ref,
            subject_digest=validated.subject_digest,
            expected=expected,
        )
        try:
            authorization_record = await self.store.load_record(
                immutable_record_storage_id(
                    product_id=validated.product_id,
                    record_space=REASONING_RECORD_SPACE,
                    record_kind="action_authorization",
                    record_key=expected.receipt_id,
                ),
                product_id=validated.product_id,
                record_space=REASONING_RECORD_SPACE,
                record_kind="action_authorization",
            )
            authorization = _GovernedActionAuthorizationReceiptV1Alpha1.model_validate(
                authorization_record.payload if authorization_record is not None else None
            )
        except Exception:
            raise GovernedReasoningError("historical action authorization is missing or cross-wired") from None
        if (
            authorization.authorization_family_key != validated.authorization_key
            or authorization.request_id != validated.request_id
            or authorization.request_digest != validated.request_digest
            or authorization.authenticated_context != validated.authenticated_context
            or authorization.execution_binding != validated.execution_binding
            or authorization.required_state_preconditions != validated.required_state_preconditions
        ):
            raise GovernedReasoningError("historical action authorization is missing or cross-wired")
        return projection

    async def verify_action_reference(
        self,
        *,
        product_id: str,
        operation: str,
        subject_ref: str,
        subject_digest: str,
        expected: ReceiptReferenceV1Alpha1,
    ) -> GovernedActionAuthorizationProjection:
        """Verify a self-contained private action receipt from content-free coordinates."""

        try:
            authorization_record = await self.store.load_record(
                immutable_record_storage_id(
                    product_id=product_id,
                    record_space=REASONING_RECORD_SPACE,
                    record_kind="action_authorization",
                    record_key=expected.receipt_id,
                ),
                product_id=product_id,
                record_space=REASONING_RECORD_SPACE,
                record_kind="action_authorization",
            )
            if authorization_record is None:
                raise GovernedReasoningError("durable action authorization is missing")
            indexed_authorization = _GovernedActionAuthorizationReceiptV1Alpha1.model_validate(
                authorization_record.payload
            )
            if _receipt_reference(indexed_authorization) != expected:
                raise GovernedReasoningError("durable action authorization reference is cross-wired")
            authorization_key = indexed_authorization.authorization_key
            transaction = await self.store.load_transaction_receipt(
                product_id=product_id,
                record_space=REASONING_RECORD_SPACE,
                transaction_key=_authorization_transaction_key(authorization_key),
            )
        except GovernedReasoningError:
            raise
        except Exception:
            raise GovernedReasoningError("durable action authorization load failed closed") from None
        if transaction is None or tuple(item.record_kind for item in transaction.records) != (
            "capability_use",
            "authority_use",
            "action_authorization",
        ):
            raise GovernedReasoningError("durable action authorization is missing or malformed")
        records = (
            await self._load_record(transaction.records[0], kind="capability_use"),
            await self._load_record(transaction.records[1], kind="authority_use"),
            await self._load_record(transaction.records[2], kind="action_authorization"),
        )
        try:
            capability = CapabilityUseReceiptV1Alpha1.model_validate(records[0].payload)
            authority = AuthorityUseReceiptV1Alpha1.model_validate(records[1].payload)
            authorization = _GovernedActionAuthorizationReceiptV1Alpha1.model_validate(records[2].payload)
            historical_request = _historical_action_request(
                authorization,
                requested_at=records[2].as_of,
            )
            reconstructed = AppendOnlyTransactionRequestV1(
                product_id=product_id,
                record_space=REASONING_RECORD_SPACE,
                transaction_key=_authorization_transaction_key(authorization_key),
                records=records,
                submitted_at=transaction.committed_at,
                governed_state_preconditions=transaction.governed_state_preconditions,
            )
        except Exception:
            raise GovernedReasoningError("durable action authorization failed exact replay") from None
        outcome = _GovernedActionAuthorizationMaterial(
            authorization=authorization,
            capability_use=capability,
            authority_use=authority,
            transaction_receipt=transaction,
            replayed=True,
        )
        if (
            transaction != reconstructed.receipt()
            or transaction.committed_at != authorization.authorized_at
            or transaction.governed_state_preconditions != authorization.state_preconditions
            or authorization.capability_use != capability
            or authorization.authority_use != authority
            or authorization.product_id != product_id
            or authorization.authorization_key != authorization_key
            or authorization_key
            != _resolved_authorization_key(
                historical_request,
                capability,
                authority,
            )
            or authorization.operation != operation
            or authorization.subject_ref != subject_ref
            or authorization.subject_digest != subject_digest
            or outcome.reference != expected
            or any(record.as_of != historical_request.requested_at for record in records)
            or any(record.available_at != authorization.authorized_at for record in records)
        ):
            raise GovernedReasoningError("historical action authorization is missing or cross-wired")
        return outcome.projection()

    async def execute(
        self,
        request: GovernedReasoningRequestV1Alpha1,
        *,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1 | None = None,
        delivery_binding: ReasoningExecutionBindingV1Alpha1 | None = None,
    ) -> GovernedReasoningOutcome:
        """Execute once after durable acceptance, or replay one exact terminal result."""

        validated = self._revalidate_request(request)
        replay = await self._load_terminal(
            product_id=validated.product_id,
            attempt_key=validated.attempt_key,
        )
        if replay is not None:
            accepted = await self._load_acceptance(
                product_id=validated.product_id,
                attempt_key=validated.attempt_key,
            )
            if accepted is None:
                raise GovernedReasoningError("terminal replay lost its exact durable acceptance")
            self._assert_acceptance_matches_request(validated, accepted)
            await self._authorize_terminal_replay(
                validated,
                replay,
                delivery_context=delivery_context,
                delivery_binding=delivery_binding,
            )
            return replay
        accepted = await self._load_acceptance(
            product_id=validated.product_id,
            attempt_key=validated.attempt_key,
        )
        if accepted is not None:
            self._assert_acceptance_matches_request(validated, accepted)
            raise GovernedReasoningOrphanedAttempt("accepted attempt has no terminal commit; submit a new attempt key")

        started_at = self._now(label="reasoning start")
        if validated.requested_at > started_at:
            raise GovernedReasoningError("reasoning cannot start before the exact request time")
        self._assert_authenticated(validated.authenticated_context, started_at)
        await self._validate_context(validated)
        capability = await self._capability_use(validated, evaluated_at=started_at)
        authority = await self._authority_use(validated, evaluated_at=started_at)
        initial_preconditions = _unique_preconditions(
            validated.required_state_preconditions,
            (capability.state_head_precondition,),
            (authority.state_head_precondition,),
        )
        acceptance = ReasoningAcceptanceReceiptV1Alpha1(
            product_id=validated.product_id,
            attempt_key=validated.attempt_key,
            request_id=str(validated.request_id),
            request_digest=str(validated.request_digest),
            actor_ref=validated.authenticated_context.actor_ref,
            cutoff_at=validated.cutoff_at,
            instruction_digest=f"sha256:{canonical_hash(validated.instruction_json)}",
            context_bindings=tuple(ContextBindingV1Alpha1.from_item(item) for item in validated.context_items),
            capability_use=_receipt_reference(capability),
            authority_use=_receipt_reference(authority),
            state_preconditions=initial_preconditions,
            accepted_at=started_at,
        )
        acceptance_request = AppendOnlyTransactionRequestV1(
            product_id=validated.product_id,
            record_space=REASONING_RECORD_SPACE,
            transaction_key=_transaction_key(validated.attempt_key, "acceptance"),
            records=(
                _record(
                    capability,
                    product_id=validated.product_id,
                    record_kind="capability_use",
                    record_key=str(capability.receipt_id),
                    as_of=validated.cutoff_at,
                    available_at=started_at,
                    processing_order=0,
                ),
                _record(
                    authority,
                    product_id=validated.product_id,
                    record_kind="authority_use",
                    record_key=str(authority.receipt_id),
                    as_of=validated.cutoff_at,
                    available_at=started_at,
                    processing_order=1,
                ),
                _record(
                    acceptance,
                    product_id=validated.product_id,
                    record_kind="request_acceptance",
                    record_key=str(acceptance.receipt_id),
                    as_of=validated.cutoff_at,
                    available_at=started_at,
                    processing_order=2,
                ),
            ),
            submitted_at=started_at,
            governed_state_preconditions=initial_preconditions,
        )
        try:
            acceptance_transaction = await self.store.append(acceptance_request)
        except ImmutableRecordReplayConflict:
            raise GovernedReasoningReplayConflict("attempt key already binds different acceptance material") from None
        except ImmutableRecordPersistenceError:
            raise GovernedReasoningError("durable reasoning acceptance failed closed") from None
        except Exception:
            raise GovernedReasoningError("durable reasoning acceptance failed closed") from None
        if acceptance_transaction != acceptance_request.receipt():
            raise GovernedReasoningError("acceptance transaction receipt is not exact")

        try:
            completed = await self._complete_accepted(
                request=validated,
                acceptance=acceptance,
                capability=capability,
                authority=authority,
                started_at=started_at,
            )
        except GovernedReasoningOrphanedAttempt:
            raise
        except Exception:
            completed = None
        if completed is None:
            raise GovernedReasoningOrphanedAttempt(
                "accepted attempt did not reach terminal commit; submit a new attempt key"
            )
        return completed

    async def execute_historical(
        self,
        *,
        product_id: str,
        attempt_key: str,
        expected_request_id: str,
        expected_request_digest: str,
        instruction_json: str,
        context_items: tuple[FrozenContextItemV1Alpha1, ...],
        cutoff_at: datetime,
        requested_at: datetime,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1,
        delivery_binding: ReasoningExecutionBindingV1Alpha1,
    ) -> GovernedReasoningOutcome:
        """Reconstruct an exact private historical command, then authorize delivery."""

        accepted = await self._load_acceptance(
            product_id=product_id,
            attempt_key=attempt_key,
        )
        if accepted is None:
            raise GovernedReasoningError("historical reasoning acceptance is missing")
        acceptance, capability, authority, _ = accepted
        use_identities = {
            (
                capability.state_head_precondition.state_kind,
                capability.state_head_precondition.product_id,
                capability.state_head_precondition.state_id,
            ),
            (
                authority.state_head_precondition.state_kind,
                authority.state_head_precondition.product_id,
                authority.state_head_precondition.state_id,
            ),
        }
        retained = tuple(
            item
            for item in acceptance.state_preconditions
            if (item.state_kind, item.product_id, item.state_id) not in use_identities
        )
        try:
            reconstructed = GovernedReasoningRequestV1Alpha1(
                attempt_key=attempt_key,
                product_id=product_id,
                authenticated_context=capability.authenticated_context,
                artifact=capability.artifact,
                configuration_ref=capability.configuration_ref,
                authority=authority.authority,
                grant_ref=authority.grant_ref,
                instruction_json=instruction_json,
                context_items=context_items,
                cutoff_at=cutoff_at,
                requested_at=requested_at,
                required_state_preconditions=retained,
            )
        except Exception:
            raise GovernedReasoningError("historical reasoning request reconstruction failed closed") from None
        if reconstructed.request_id != expected_request_id or reconstructed.request_digest != expected_request_digest:
            raise GovernedReasoningReplayConflict(
                "historical reasoning coordinates do not reconstruct the exact accepted request"
            )
        return await self.execute(
            reconstructed,
            delivery_context=delivery_context,
            delivery_binding=delivery_binding,
        )

    async def _authorize_terminal_replay(
        self,
        request: GovernedReasoningRequestV1Alpha1,
        outcome: GovernedReasoningOutcome,
        *,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1 | None,
        delivery_binding: ReasoningExecutionBindingV1Alpha1 | None,
    ) -> None:
        """Recheck current actor-scoped delivery authority without rewriting history."""

        evaluated_at = self._now(label="reasoning replay delivery")
        if evaluated_at < outcome.terminal.completed_at:
            raise GovernedReasoningError("reasoning replay delivery cannot predate terminal completion")
        await self.authorize_use(
            request,
            evaluated_at=evaluated_at,
            authenticated_context=delivery_context,
            execution_binding=delivery_binding,
        )

    async def _complete_accepted(
        self,
        *,
        request: GovernedReasoningRequestV1Alpha1,
        acceptance: ReasoningAcceptanceReceiptV1Alpha1,
        capability: CapabilityUseReceiptV1Alpha1,
        authority: AuthorityUseReceiptV1Alpha1,
        started_at: datetime,
    ) -> GovernedReasoningOutcome:
        output = await self._execute_provider(request, started_at=started_at)
        rechecked_at = self._now(label="reasoning post-execution recheck")
        if rechecked_at < started_at:
            raise GovernedReasoningError("reasoning recheck cannot precede durable acceptance")
        self._assert_authenticated(request.authenticated_context, rechecked_at)
        post_capability = await self._capability_use(request, evaluated_at=rechecked_at)
        post_authority = await self._authority_use(request, evaluated_at=rechecked_at)
        if (
            post_capability.state_head_precondition != capability.state_head_precondition
            or post_capability.artifact != capability.artifact
            or post_capability.configuration_ref != capability.configuration_ref
        ):
            raise GovernedReasoningError(
                "capability state, artifact, or configuration changed during provider execution"
            )
        if (
            post_authority.state_head_precondition != authority.state_head_precondition
            or post_authority.grant_ref != authority.grant_ref
            or post_authority.grant_hash != authority.grant_hash
            or post_authority.expires_at != authority.expires_at
        ):
            raise GovernedReasoningError(
                "authority grant identity, material, or expiry changed during provider execution"
            )
        completed_at = self._now(label="reasoning terminal commit")
        if completed_at < rechecked_at:
            raise GovernedReasoningError("reasoning terminal commit cannot precede its recheck")
        self._assert_authenticated(request.authenticated_context, completed_at)
        if (authority.expires_at is not None and completed_at >= authority.expires_at) or (
            post_authority.expires_at is not None and completed_at >= post_authority.expires_at
        ):
            raise GovernedReasoningError("authority expired before terminal commit")
        terminal_preconditions = _unique_preconditions(
            request.required_state_preconditions,
            (post_capability.state_head_precondition,),
            (post_authority.state_head_precondition,),
        )
        result = StructuredFinalResultV1Alpha1(
            product_id=request.product_id,
            attempt_key=request.attempt_key,
            request_id=str(request.request_id),
            request_digest=str(request.request_digest),
            artifact=request.artifact,
            route=output.route,
            usage=output.usage,
            structured_json=output.structured_json,
            referenced_context_ids=output.referenced_context_ids,
            completed_at=completed_at,
        )
        referenced = set(result.referenced_context_ids)
        uses = tuple(
            ContextUseReceiptV1Alpha1(
                product_id=request.product_id,
                request_id=str(request.request_id),
                request_digest=str(request.request_digest),
                result_id=str(result.result_id),
                result_digest=str(result.result_digest),
                context=ContextBindingV1Alpha1.from_item(item),
                output_referenced=str(item.context_id) in referenced,
                recorded_at=completed_at,
            )
            for item in request.context_items
        )
        terminal = ReasoningTerminalReceiptV1Alpha1(
            product_id=request.product_id,
            attempt_key=request.attempt_key,
            request_id=str(request.request_id),
            request_digest=str(request.request_digest),
            acceptance=_receipt_reference(acceptance),
            result_id=str(result.result_id),
            result_digest=str(result.result_digest),
            route=result.route,
            usage=result.usage,
            context_uses=tuple(_receipt_reference(item) for item in uses),
            capability_use=_receipt_reference(capability),
            authority_use=_receipt_reference(authority),
            completed_at=completed_at,
        )
        values: tuple[tuple[Any, str, str], ...] = (
            (result, "structured_result", str(result.result_id)),
            *((item, "context_use", str(item.receipt_id)) for item in uses),
            (terminal, "terminal_receipt", str(terminal.receipt_id)),
        )
        terminal_request = AppendOnlyTransactionRequestV1(
            product_id=request.product_id,
            record_space=REASONING_RECORD_SPACE,
            transaction_key=_transaction_key(request.attempt_key, "terminal"),
            records=tuple(
                _record(
                    value,
                    product_id=request.product_id,
                    record_kind=kind,
                    record_key=key,
                    as_of=request.cutoff_at,
                    available_at=completed_at,
                    processing_order=index,
                )
                for index, (value, kind, key) in enumerate(values)
            ),
            submitted_at=completed_at,
            governed_state_preconditions=terminal_preconditions,
        )
        transaction_receipt = await self.store.append(terminal_request)
        if transaction_receipt != terminal_request.receipt():
            raise GovernedReasoningOrphanedAttempt(
                "provider execution completed but terminal receipt was not exact; submit a new attempt key"
            )
        return GovernedReasoningOutcome(
            acceptance=acceptance,
            result=result,
            context_uses=uses,
            terminal=terminal,
            transaction_receipt=transaction_receipt,
            replayed=False,
        )


__all__ = [
    "CONTEXT_BINDING_VERSION",
    "CONTEXT_USE_RECEIPT_VERSION",
    "FROZEN_CONTEXT_ITEM_VERSION",
    "GOVERNED_ACTION_AUTHORIZATION_RECEIPT_VERSION",
    "GOVERNED_ACTION_AUTHORIZATION_PROJECTION_VERSION",
    "GOVERNED_ACTION_AUTHORIZATION_REQUEST_VERSION",
    "GOVERNED_OPERATION_BINDING_VERSION",
    "GOVERNED_REASONING_REQUEST_VERSION",
    "GOVERNED_OPERATION_CONFIGURATION_STATE_KIND",
    "PROVIDER_EXECUTION_REQUEST_VERSION",
    "PROVIDER_ROUTE_VERSION",
    "PROVIDER_STRUCTURED_OUTPUT_VERSION",
    "PROVIDER_USAGE_VERSION",
    "REASONING_ACCEPTANCE_RECEIPT_VERSION",
    "REASONING_CONFIGURATION_STATE_KIND",
    "REASONING_EXECUTION_BINDING_VERSION",
    "REASONING_OPERATION",
    "REASONING_RECORD_SPACE",
    "REASONING_TERMINAL_RECEIPT_VERSION",
    "RECEIPT_REFERENCE_VERSION",
    "STRUCTURED_FINAL_RESULT_VERSION",
    "ContextBindingV1Alpha1",
    "ContextUseReceiptV1Alpha1",
    "FrozenContextItemV1Alpha1",
    "GovernedActionAuthorizationProjection",
    "GovernedActionAuthorizationRequestV1Alpha1",
    "GovernedOperationBindingV1Alpha1",
    "GovernedReasoningError",
    "GovernedReasoningOrphanedAttempt",
    "GovernedReasoningOutcome",
    "GovernedReasoningReplayConflict",
    "GovernedReasoningRequestV1Alpha1",
    "GovernedReasoningService",
    "ProviderExecutionRequestV1Alpha1",
    "ProviderRouteV1Alpha1",
    "ProviderStructuredOutputV1Alpha1",
    "ProviderUsageV1Alpha1",
    "ReasoningAcceptanceReceiptV1Alpha1",
    "ReasoningExecutionBindingV1Alpha1",
    "ReasoningProvider",
    "ReasoningTerminalReceiptV1Alpha1",
    "ReasoningUseAuthorization",
    "ReceiptReferenceV1Alpha1",
    "StructuredFinalResultV1Alpha1",
]

"""Domain-neutral contracts for one governed LIVE source capture and admission."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
)
from ace.core.source import (
    MAX_CAPTURED_PAYLOAD_CHARS,
    validate_exact_https_uri,
    validate_public_ip_literal,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.common import (
    parse_json_strict,
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    SourceMappingReferenceV1Alpha1,
)

LIVE_SOURCE_INGRESS_REQUEST_VERSION = "ace.intelligence.live-source-ingress-request/v1alpha1"
SOURCE_ADAPTER_CAPTURE_REQUEST_VERSION = "ace.intelligence.source-adapter-capture-request/v1alpha1"
CAPTURED_SOURCE_MATERIAL_VERSION = "ace.intelligence.captured-source-material/v1alpha1"
SOURCE_ACQUISITION_RECEIPT_VERSION = "ace.intelligence.source-acquisition-receipt/v1alpha1"
LIVE_SOURCE_ADMISSION_RECEIPT_VERSION = "ace.intelligence.live-source-admission-receipt/v1alpha1"


class LiveSourceIngressRecordKind(StrEnum):
    SOURCE_ACQUISITION = "source_acquisition"
    SOURCE_SNAPSHOT = "source_snapshot"
    OBSERVATION = "observation"
    ENTITY_SNAPSHOT = "entity_snapshot"
    SOURCE_ADMISSION = "source_admission"


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


def _derive(instance: _StrictFrozenContract, *, id_field: str, digest_field: str, prefix: str) -> None:
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


def _reject_fractional_json_numbers(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is float:
            raise ValueError(
                "fractional JSON numeric tokens are not faithful alpha source material; use exact decimal text"
            )
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)


class LiveSourceIngressRequestV1Alpha1(_StrictFrozenContract):
    """Exact idempotency intent for one actor-scoped source capture operation."""

    contract: Literal["ace.intelligence.live-source-ingress-request/v1alpha1"] = LIVE_SOURCE_INGRESS_REQUEST_VERSION
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    idempotency_key: str
    operation: Literal["capture"] = "capture"
    activation_key: str
    mapping_id: str
    source_definition_ref: str
    compiled_pack_id: str
    pack_digest: str
    requested_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("idempotency_key", "source_definition_ref", "compiled_pack_id", "request_id")
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("activation_key", "mapping_id")
    @classmethod
    def validate_identifiers(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("pack_digest", "request_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @model_validator(mode="after")
    def validate_scope_window_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("authenticated context crossed the ingress product scope")
        if not (
            self.authenticated_context.authenticated_at <= self.requested_at < self.authenticated_context.expires_at
        ):
            raise ValueError("ingress request must be created inside the authenticated window")
        expected_pack_id = f"pack_ir:{self.pack_digest.removeprefix('sha256:')[:32]}"
        if self.compiled_pack_id != expected_pack_id:
            raise ValueError("compiled_pack_id and pack_digest must identify one exact Pack IR")
        _derive(self, id_field="request_id", digest_field="request_digest", prefix="live_source_ingress_request")
        return self


class SourceAdapterCaptureRequestV1Alpha1(_StrictFrozenContract):
    """Closed, credential-free request passed to one exact installed adapter."""

    contract: Literal["ace.intelligence.source-adapter-capture-request/v1alpha1"] = (
        SOURCE_ADAPTER_CAPTURE_REQUEST_VERSION
    )
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    use_subject_ref: str
    use_subject_digest: str
    operation: Literal["capture"] = "capture"
    source_definition_ref: str
    source_type_ref: str
    requested_uri: str = Field(min_length=9, max_length=2_048)
    adapter_artifact: CapabilityArtifactIdentityV1Alpha1
    configuration_ref: str
    configuration_digest: str
    started_at: datetime
    max_payload_chars: int = Field(ge=1, le=MAX_CAPTURED_PAYLOAD_CHARS)
    credentials_allowed: Literal[False] = False
    redirects_allowed: Literal[False] = False
    public_network_only: Literal[True] = True
    dns_rebinding_protection_required: Literal[True] = True
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator(
        "use_subject_ref",
        "source_definition_ref",
        "configuration_ref",
        "request_id",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("use_subject_digest", "configuration_digest", "request_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("source_type_ref")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        return validate_reference(value, name="source_type_ref")

    @field_validator("requested_uri")
    @classmethod
    def validate_uri(cls, value: str) -> str:
        return validate_exact_https_uri(value, name="requested_uri")

    @field_validator("started_at")
    @classmethod
    def normalize_started_at(cls, value: datetime) -> datetime:
        return _aware(value, name="started_at")

    @model_validator(mode="after")
    def validate_scope_window_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("authenticated context crossed the adapter-request product scope")
        if not (self.authenticated_context.authenticated_at <= self.started_at < self.authenticated_context.expires_at):
            raise ValueError("adapter request must start inside the authenticated window")
        _derive(self, id_field="request_id", digest_field="request_digest", prefix="source_adapter_capture_request")
        return self


class CapturedSourceMaterialV1Alpha1(_StrictFrozenContract):
    """Inert adapter output for one exact request; it carries no authority."""

    contract: Literal["ace.intelligence.captured-source-material/v1alpha1"] = CAPTURED_SOURCE_MATERIAL_VERSION
    capture_request_ref: str
    capture_request_digest: str
    source_type_ref: str
    requested_uri: str = Field(min_length=9, max_length=2_048)
    effective_uri: str = Field(min_length=9, max_length=2_048)
    redirect_chain: tuple[str, ...] = Field(default_factory=tuple, max_length=0)
    resolved_ip_addresses: tuple[str, ...] = Field(min_length=1, max_length=32)
    dns_rebinding_protection_applied: Literal[True] = True
    captured_payload_json: str = Field(min_length=1, max_length=MAX_CAPTURED_PAYLOAD_CHARS)
    captured_payload_digest: str
    locator: str = Field(min_length=1, max_length=1_000)
    source_published_at: datetime | None = None
    event_effective_at: datetime | None = None
    observed_at: datetime
    captured_at: datetime
    disposition: Literal["captured"] = "captured"
    capture_id: str | None = None
    capture_digest: str | None = None

    @field_validator("capture_request_ref", "capture_id")
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "capture_request_digest",
        "captured_payload_digest",
        "capture_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("source_type_ref")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        return validate_reference(value, name="source_type_ref")

    @field_validator("requested_uri", "effective_uri")
    @classmethod
    def validate_uris(cls, value: str, info) -> str:
        return validate_exact_https_uri(value, name=info.field_name)

    @field_validator("captured_payload_json")
    @classmethod
    def canonicalize_payload(cls, value: str) -> str:
        try:
            parsed = parse_json_strict(value)
            _reject_fractional_json_numbers(parsed)
            normalized = canonical_json(parsed)
            normalized.encode("utf-8")
        except (TypeError, UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError("captured payload must be bounded canonical finite JSON") from exc
        if len(normalized) > MAX_CAPTURED_PAYLOAD_CHARS:
            raise ValueError("captured payload exceeds the canonical size bound")
        return normalized

    @field_validator("locator")
    @classmethod
    def validate_locator(cls, value: str) -> str:
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("locator must contain Unicode scalar values")
        return value

    @field_validator("resolved_ip_addresses")
    @classmethod
    def validate_resolved_addresses(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in value:
            try:
                address = validate_public_ip_literal(raw, name="resolved_ip_addresses")
            except ValueError as exc:
                raise ValueError(
                    "captured source material requires exact globally routable resolved addresses"
                ) from exc
            normalized.append(address)
        if len(normalized) != len(set(normalized)):
            raise ValueError("resolved_ip_addresses must be unique")
        return tuple(sorted(normalized))

    @field_validator("source_published_at", "event_effective_at", "observed_at", "captured_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_exact_capture(self) -> Self:
        if self.effective_uri != self.requested_uri or self.redirect_chain:
            raise ValueError("alpha capture denies redirects and requires exact effective URI equality")
        expected_payload_digest = "sha256:" + hashlib.sha256(self.captured_payload_json.encode("utf-8")).hexdigest()
        if self.captured_payload_digest != expected_payload_digest:
            raise ValueError("captured payload digest does not match canonical payload bytes")
        if self.observed_at > self.captured_at:
            raise ValueError("capture time cannot precede observation time")
        if self.source_published_at is not None and self.source_published_at > self.observed_at:
            raise ValueError("source publication cannot follow observation time")
        if self.event_effective_at is not None and self.event_effective_at > self.observed_at:
            raise ValueError("event effective time cannot follow observation time")
        _derive(self, id_field="capture_id", digest_field="capture_digest", prefix="captured_source_material")
        return self


class SourceAcquisitionReceiptV1Alpha1(_StrictFrozenContract):
    """Successful acquisition proof created before the canonical snapshot."""

    contract: Literal["ace.intelligence.source-acquisition-receipt/v1alpha1"] = SOURCE_ACQUISITION_RECEIPT_VERSION
    disposition: Literal["captured"] = "captured"
    product_id: str
    actor_ref: str
    use_subject_ref: str
    use_subject_digest: str
    operation: Literal["capture"] = "capture"
    source_definition_ref: str
    source_type_ref: str
    source_definition_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    configuration_ref: str
    configuration_digest: str
    requested_uri: str
    effective_uri: str
    adapter_artifact: CapabilityArtifactIdentityV1Alpha1
    capability_use: CapabilityUseReceiptV1Alpha1
    authority_use: AuthorityUseReceiptV1Alpha1
    captured_payload_digest: str
    resolved_ip_addresses: tuple[str, ...] = Field(min_length=1, max_length=32)
    dns_rebinding_protection_applied: Literal[True] = True
    locator: str
    source_published_at: datetime | None = None
    event_effective_at: datetime | None = None
    observed_at: datetime
    captured_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator(
        "actor_ref",
        "use_subject_ref",
        "source_definition_ref",
        "configuration_ref",
        "receipt_id",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "use_subject_digest",
        "configuration_digest",
        "captured_payload_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("source_type_ref")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        return validate_reference(value, name="source_type_ref")

    @field_validator("resolved_ip_addresses")
    @classmethod
    def validate_resolved_addresses(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in value:
            try:
                address = validate_public_ip_literal(raw, name="resolved_ip_addresses")
            except ValueError as exc:
                raise ValueError("acquisition receipt requires exact globally routable resolved addresses") from exc
            normalized.append(address)
        if len(normalized) != len(set(normalized)):
            raise ValueError("resolved_ip_addresses must be unique")
        return tuple(sorted(normalized))

    @field_validator("requested_uri", "effective_uri")
    @classmethod
    def validate_uris(cls, value: str, info) -> str:
        return validate_exact_https_uri(value, name=info.field_name)

    @field_validator("source_published_at", "event_effective_at", "observed_at", "captured_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_exact_use_and_identity(self) -> Self:
        if (
            self.source_definition_head_precondition.product_id != self.product_id
            or self.source_definition_head_precondition.state_kind != "source_definition"
            or self.source_definition_head_precondition.state_id != self.source_definition_ref
        ):
            raise ValueError("acquisition requires the exact named source-definition head")
        expected_scope = (self.product_id, self.actor_ref, self.use_subject_ref, self.use_subject_digest)
        capability_scope = (
            self.capability_use.product_id,
            self.capability_use.actor_ref,
            self.capability_use.use_subject_ref,
            self.capability_use.use_subject_digest,
        )
        authority_scope = (
            self.authority_use.product_id,
            self.authority_use.actor_ref,
            self.authority_use.use_subject_ref,
            self.authority_use.use_subject_digest,
        )
        if capability_scope != expected_scope or authority_scope != expected_scope:
            raise ValueError("runtime-use receipts crossed acquisition actor, product, or subject scope")
        if self.capability_use.operation != self.operation or self.authority_use.operation != self.operation:
            raise ValueError("runtime-use receipts do not authorize the exact capture operation")
        if self.capability_use.artifact != self.adapter_artifact:
            raise ValueError("capability-use receipt does not bind the exact adapter artifact")
        if self.capability_use.configuration_ref != self.configuration_ref:
            raise ValueError("capability-use receipt does not bind the exact configuration")
        if self.requested_uri != self.effective_uri:
            raise ValueError("alpha acquisition requires exact requested and effective URI equality")
        if self.observed_at > self.captured_at:
            raise ValueError("acquisition capture time cannot precede observation time")
        _derive(self, id_field="receipt_id", digest_field="receipt_digest", prefix="source_acquisition_receipt")
        return self


class LiveSourceAdmissionReceiptV1Alpha1(_StrictFrozenContract):
    """Exact five-record LIVE admission proof without an append-receipt cycle."""

    contract: Literal["ace.intelligence.live-source-admission-receipt/v1alpha1"] = LIVE_SOURCE_ADMISSION_RECEIPT_VERSION
    admission_disposition: Literal["committed"] = "committed"
    product_id: str
    actor_ref: str
    use_subject_ref: str
    use_subject_digest: str
    operation: Literal["capture"] = "capture"
    activation_revision: ActivationRevisionReferenceV1Alpha1
    activation_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    source_definition_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    source_mapping: SourceMappingReferenceV1Alpha1
    acquisition_receipt_ref: str
    acquisition_receipt_digest: str
    source_snapshot_ref: str
    source_snapshot_digest: str
    capability_use_receipt_ref: str
    capability_use_receipt_digest: str
    authority_use_receipt_ref: str
    authority_use_receipt_digest: str
    observation_ref: str
    observation_digest: str
    entity_snapshot_ref: str
    entity_snapshot_digest: str
    admitted_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator(
        "actor_ref",
        "use_subject_ref",
        "acquisition_receipt_ref",
        "source_snapshot_ref",
        "capability_use_receipt_ref",
        "authority_use_receipt_ref",
        "observation_ref",
        "entity_snapshot_ref",
        "receipt_id",
    )
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "use_subject_digest",
        "acquisition_receipt_digest",
        "source_snapshot_digest",
        "capability_use_receipt_digest",
        "authority_use_receipt_digest",
        "observation_digest",
        "entity_snapshot_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("admitted_at")
    @classmethod
    def normalize_admitted_at(cls, value: datetime) -> datetime:
        return _aware(value, name="admitted_at")

    @model_validator(mode="after")
    def validate_scope_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("activation revision crossed the admission product scope")
        if self.source_mapping.activation_revision != self.activation_revision:
            raise ValueError("source mapping does not bind the exact admitted activation")
        if (
            self.activation_head_precondition.product_id != self.product_id
            or self.activation_head_precondition.state_kind not in {"domain_activation", "domain_activation_v1alpha1"}
            or self.activation_head_precondition.state_id != self.activation_revision.activation_id
            or self.source_definition_head_precondition.product_id != self.product_id
            or self.source_definition_head_precondition.state_kind != "source_definition"
        ):
            raise ValueError("admission governed heads do not name the exact activation and product")
        _derive(self, id_field="receipt_id", digest_field="receipt_digest", prefix="live_source_admission_receipt")
        return self

    @property
    def live_acquisition(self) -> Literal[True]:
        return True

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


class SourceAdapter(Protocol):
    artifact_identity: CapabilityArtifactIdentityV1Alpha1

    async def capture(
        self,
        request: SourceAdapterCaptureRequestV1Alpha1,
    ) -> CapturedSourceMaterialV1Alpha1: ...


class SourceAdapterRegistry(Protocol):
    def resolve_source_adapter(
        self,
        *,
        artifact: CapabilityArtifactIdentityV1Alpha1,
    ) -> SourceAdapter | None: ...


__all__ = [
    "CAPTURED_SOURCE_MATERIAL_VERSION",
    "LIVE_SOURCE_ADMISSION_RECEIPT_VERSION",
    "LIVE_SOURCE_INGRESS_REQUEST_VERSION",
    "SOURCE_ACQUISITION_RECEIPT_VERSION",
    "SOURCE_ADAPTER_CAPTURE_REQUEST_VERSION",
    "CapturedSourceMaterialV1Alpha1",
    "LiveSourceAdmissionReceiptV1Alpha1",
    "LiveSourceIngressRecordKind",
    "LiveSourceIngressRequestV1Alpha1",
    "SourceAcquisitionReceiptV1Alpha1",
    "SourceAdapter",
    "SourceAdapterCaptureRequestV1Alpha1",
    "SourceAdapterRegistry",
]

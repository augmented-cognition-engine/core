"""Versioned contracts and deterministic identities for observation synthesis outcomes.

The receipt describes one completed processing attempt.  Observation queue state
remains on the observation row; the append-only receipt records what that attempt
actually established.  This keeps a provider call, a business disposition, and a
durable success from being conflated.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SYNTHESIS_OUTCOME_CONTRACT_VERSION = "ace.capture.synthesis-outcome/v1"
SYNTHESIS_PROCESSOR_VERSION = "tp1a-observation-processor/v1"
SYNTHESIS_POLICY_VERSION = "tp1a-synthesis-policy/v1"
SYNTHESIS_SCHEMA_VERSION = "synthesis-outcome-schema/v1"

MAX_REASON_CHARS = 1_000
MAX_ERROR_MESSAGE_CHARS = 500
MAX_REFERENCES = 100

_PRODUCT_ID = re.compile(r"^product:[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_OBSERVATION_ID = re.compile(r"^observation:[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_INSIGHT_ID = re.compile(r"^insight:[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_CONFLICT_ID = re.compile(r"^conflict:[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProcessingState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILED = "retryable_failed"
    DEAD_LETTER = "dead_letter"


class SuccessfulDisposition(StrEnum):
    INSIGHT_CREATED = "insight_created"
    INSIGHT_UPDATED = "insight_updated"
    INSIGHT_MERGED = "insight_merged"
    CONFLICT_PRESERVED = "conflict_preserved"
    SKIPPED = "skipped"


class FailureCategory(StrEnum):
    PROVIDER = "provider"
    PERSISTENCE = "persistence"
    VALIDATION = "validation"
    PROCESSING = "processing"
    UNKNOWN = "unknown"


def canonical_hash(value: Any) -> str:
    """Hash a stable JSON representation without relying on object key order."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_record_id(table: str, material: Any) -> str:
    return f"{table}:{canonical_hash(material)[:32]}"


def build_material_hash(observation: dict[str, Any], *, product_id: str, observation_id: str) -> str:
    """Hash only synthesis-material input, excluding mutable queue bookkeeping."""
    material = {
        "product_id": product_id,
        "observation_id": observation_id,
        "content": str(observation.get("content") or ""),
        "observation_type": str(observation.get("observation_type") or ""),
        "confidence": observation.get("confidence"),
        "discipline_hint": observation.get("discipline_hint"),
        "domain_hint": observation.get("domain_hint"),
        "domain_path": observation.get("domain_path"),
        "source": observation.get("source"),
        "source_memory": str(observation.get("source_memory") or "") or None,
    }
    return canonical_hash(material)


def build_attempt_id(
    *,
    product_id: str,
    observation_id: str,
    attempt_count: int,
    route: str,
    processor_version: str = SYNTHESIS_PROCESSOR_VERSION,
    policy_version: str = SYNTHESIS_POLICY_VERSION,
    schema_version: str = SYNTHESIS_SCHEMA_VERSION,
) -> str:
    """Build the idempotency identity for one numbered attempt.

    The material hash is deliberately not part of this identity.  If the same
    observation/attempt coordinate is replayed with changed material, receipt
    persistence can detect the conflict instead of minting a second history.
    """
    return _stable_record_id(
        "synthesis_attempt",
        {
            "product_id": product_id,
            "observation_id": observation_id,
            "attempt_count": attempt_count,
            "route": route,
            "processor_version": processor_version,
            "policy_version": policy_version,
            "schema_version": schema_version,
        },
    )


def build_receipt_id(*, product_id: str, attempt_id: str) -> str:
    return _stable_record_id("synthesis_outcome_receipt", {"product_id": product_id, "attempt_id": attempt_id})


def build_insight_id(*, product_id: str, attempt_id: str, content: str, ordinal: int) -> str:
    """Build a deterministic insight identity for retry-safe creation."""
    return _stable_record_id(
        "insight",
        {
            "product_id": product_id,
            "attempt_id": attempt_id,
            "content_hash": canonical_hash(content),
            "ordinal": ordinal,
        },
    )


def build_conflict_id(*, product_id: str, attempt_id: str, insight_id: str, ordinal: int) -> str:
    return _stable_record_id(
        "conflict",
        {
            "product_id": product_id,
            "attempt_id": attempt_id,
            "insight_id": insight_id,
            "ordinal": ordinal,
        },
    )


def _normalize_refs(value: Any, *, pattern: re.Pattern[str], name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{name} must be a collection")
    refs = tuple(sorted(set(str(item) for item in value)))
    if len(refs) > MAX_REFERENCES:
        raise ValueError(f"{name} exceeds the {MAX_REFERENCES}-item bound")
    if any(not pattern.fullmatch(item) for item in refs):
        raise ValueError(f"{name} must contain bounded record references")
    return refs


class SynthesisProvenanceV1(FrozenContract):
    route: str = Field(min_length=1, max_length=120)
    source: str | None = Field(default=None, max_length=120)
    session_id: str | None = Field(default=None, max_length=240)

    @field_validator("route")
    @classmethod
    def validate_route(cls, value: str) -> str:
        if not _TOKEN.fullmatch(value):
            raise ValueError("route must be a bounded stable token")
        return value


class SynthesisFailureV1(FrozenContract):
    category: FailureCategory
    code: str = Field(min_length=1, max_length=120)
    error_type: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=MAX_ERROR_MESSAGE_CHARS)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not _TOKEN.fullmatch(value):
            raise ValueError("failure code must be a bounded stable token")
        return value


class ObservationSynthesisOutcomeV1(FrozenContract):
    """The explicit business disposition returned for one observation."""

    observation_id: str
    disposition: SuccessfulDisposition
    created_insight_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    updated_insight_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    merged_insight_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    conflicting_insight_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    conflict_record_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_REFERENCES)
    reason: str | None = Field(default=None, max_length=MAX_REASON_CHARS)

    @field_validator("observation_id")
    @classmethod
    def validate_observation_id(cls, value: str) -> str:
        if not _OBSERVATION_ID.fullmatch(value):
            raise ValueError("observation_id must be an observation record identifier")
        return value

    @field_validator(
        "created_insight_refs",
        "updated_insight_refs",
        "merged_insight_refs",
        "conflicting_insight_refs",
        mode="before",
    )
    @classmethod
    def validate_insight_refs(cls, value: Any, info) -> tuple[str, ...]:
        return _normalize_refs(value, pattern=_INSIGHT_ID, name=info.field_name)

    @field_validator("conflict_record_refs", mode="before")
    @classmethod
    def validate_conflict_refs(cls, value: Any) -> tuple[str, ...]:
        return _normalize_refs(value, pattern=_CONFLICT_ID, name="conflict_record_refs")

    @model_validator(mode="after")
    def validate_disposition_evidence(self) -> Self:
        evidence = {
            SuccessfulDisposition.INSIGHT_CREATED: self.created_insight_refs,
            SuccessfulDisposition.INSIGHT_UPDATED: self.updated_insight_refs,
            SuccessfulDisposition.INSIGHT_MERGED: self.merged_insight_refs,
            SuccessfulDisposition.CONFLICT_PRESERVED: self.conflicting_insight_refs,
        }
        if self.disposition in evidence and not evidence[self.disposition]:
            raise ValueError(f"{self.disposition.value} requires its corresponding insight references")
        if self.disposition is SuccessfulDisposition.CONFLICT_PRESERVED and not self.conflict_record_refs:
            raise ValueError("conflict_preserved requires a durable conflict record reference")
        if self.disposition is SuccessfulDisposition.SKIPPED and not (self.reason or "").strip():
            raise ValueError("skipped requires a non-empty reason")
        if self.disposition is not SuccessfulDisposition.SKIPPED and self.reason is not None:
            raise ValueError("reason is reserved for the skipped disposition")
        selected = [bool(refs) for refs in evidence.values()]
        if sum(selected) > 1:
            raise ValueError("one observation outcome must not claim multiple primary dispositions")
        return self


class SynthesisOutcomeReceiptV1(FrozenContract):
    """Immutable, product-scoped receipt for one observation processing attempt."""

    contract_version: Literal["ace.capture.synthesis-outcome/v1"] = SYNTHESIS_OUTCOME_CONTRACT_VERSION
    receipt_id: str
    product_id: str
    observation_id: str
    attempt_id: str
    attempt_count: int = Field(ge=1)
    processing_state: ProcessingState
    outcome: ObservationSynthesisOutcomeV1 | None = None
    failure: SynthesisFailureV1 | None = None
    retryable: bool
    next_retry_at: datetime | None = None
    processor_version: str = Field(min_length=1, max_length=120)
    policy_version: str = Field(min_length=1, max_length=120)
    schema_version: str = Field(min_length=1, max_length=120)
    material_hash: str
    started_at: datetime
    completed_at: datetime | None = None
    provenance: SynthesisProvenanceV1
    explainable_terminal: bool

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, value: str) -> str:
        if not _PRODUCT_ID.fullmatch(value):
            raise ValueError("product_id must be a product-scoped record identifier")
        return value

    @field_validator("observation_id")
    @classmethod
    def validate_observation_ref(cls, value: str) -> str:
        if not _OBSERVATION_ID.fullmatch(value):
            raise ValueError("observation_id must be an observation record identifier")
        return value

    @field_validator("receipt_id")
    @classmethod
    def validate_receipt_id(cls, value: str) -> str:
        if not value.startswith("synthesis_outcome_receipt:") or not _TOKEN.fullmatch(value):
            raise ValueError("receipt_id must be a synthesis outcome receipt identifier")
        return value

    @field_validator("attempt_id", "processor_version", "policy_version", "schema_version")
    @classmethod
    def validate_tokens(cls, value: str) -> str:
        if not _TOKEN.fullmatch(value):
            raise ValueError("attempt and version fields must be bounded stable tokens")
        return value

    @field_validator("material_hash")
    @classmethod
    def validate_material_hash(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256.fullmatch(normalized):
            raise ValueError("material_hash must be a lowercase SHA-256 digest")
        return normalized

    @field_validator("started_at", "completed_at", "next_retry_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None, info) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError(f"{info.field_name} must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        expected_attempt_id = build_attempt_id(
            product_id=self.product_id,
            observation_id=self.observation_id,
            attempt_count=self.attempt_count,
            route=self.provenance.route,
            processor_version=self.processor_version,
            policy_version=self.policy_version,
            schema_version=self.schema_version,
        )
        if self.attempt_id != expected_attempt_id:
            raise ValueError("attempt_id does not match its deterministic product-scoped identity")
        if self.receipt_id != build_receipt_id(product_id=self.product_id, attempt_id=self.attempt_id):
            raise ValueError("receipt_id does not match its deterministic product-scoped identity")
        if self.outcome is not None and self.outcome.observation_id != self.observation_id:
            raise ValueError("outcome observation_id must match the receipt")
        is_terminal = self.processing_state in {
            ProcessingState.SUCCEEDED,
            ProcessingState.RETRYABLE_FAILED,
            ProcessingState.DEAD_LETTER,
        }
        if self.explainable_terminal is not is_terminal:
            raise ValueError("explainable_terminal must reflect the processing state")
        if is_terminal and self.completed_at is None:
            raise ValueError("completed attempts require completed_at")
        if not is_terminal and self.completed_at is not None:
            raise ValueError("non-terminal states must not claim completion")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if self.processing_state is ProcessingState.SUCCEEDED:
            if self.outcome is None or self.failure is not None or self.retryable:
                raise ValueError("succeeded requires an outcome, no failure, and retryable=false")
            if self.next_retry_at is not None:
                raise ValueError("succeeded must not schedule a retry")
        elif self.processing_state is ProcessingState.RETRYABLE_FAILED:
            if self.failure is None or self.outcome is not None or not self.retryable:
                raise ValueError("retryable_failed requires a failure and retryable=true")
            if self.next_retry_at is None:
                raise ValueError("retryable_failed requires next_retry_at")
        elif self.processing_state is ProcessingState.DEAD_LETTER:
            if self.failure is None or self.outcome is not None or self.retryable:
                raise ValueError("dead_letter requires a failure and retryable=false")
            if self.next_retry_at is not None:
                raise ValueError("dead_letter must not schedule a retry")
        else:
            if self.outcome is not None or self.failure is not None or self.retryable or self.next_retry_at is not None:
                raise ValueError("pending/processing receipts cannot claim an outcome, failure, or retry")
        return self


def receipt_hash(receipt: SynthesisOutcomeReceiptV1) -> str:
    return canonical_hash(receipt)

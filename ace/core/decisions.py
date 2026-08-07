"""Domain-neutral governed Decision and Outcome contracts.

Core owns exact subjects, named principals, action/no-action separation,
authorization receipts, temporal ordering, and immutable identities.  The
contracts deliberately do not know whether the reviewed subject is a Brief,
forecast, recommendation, or any other higher-layer object.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.core.reasoning import GovernedActionAuthorizationProjection
from ace.core.records import ImmutableRecordReferenceV1
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1

DECISION_INTENT_VERSION = "ace.core.decision-intent/v1alpha1"
DECISION_VERSION = "ace.core.decision/v1alpha1"
OUTCOME_INTENT_VERSION = "ace.core.outcome-intent/v1alpha1"
OUTCOME_VERSION = "ace.core.outcome/v1alpha1"


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


class DecisionDisposition(StrEnum):
    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"


class DecisionActionDisposition(StrEnum):
    NO_ACTION = "no_action"
    AUTHORIZE_ACTION = "authorize_action"


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _bounded(value: str, *, name: str, maximum: int = 240) -> str:
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _canonical_value_json(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 100_000:
        raise ValueError(f"{name} must be bounded canonical JSON text")
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
        normalized = canonical_json(parsed)
    except (json.JSONDecodeError, RecursionError, TypeError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite JSON with unique object keys") from exc
    if normalized != value:
        raise ValueError(f"{name} must already use canonical JSON encoding")
    return value


def _derive_identity(
    instance: _StrictFrozenContract,
    *,
    prefix: str,
    id_field: str,
    digest_field: str,
) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class DecisionIntentV1Alpha1(_StrictFrozenContract):
    """One named principal's exact disposition of an opaque immutable subject."""

    contract: Literal["ace.core.decision-intent/v1alpha1"] = DECISION_INTENT_VERSION
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    subject: ImmutableRecordReferenceV1
    actor_role_ref: str
    decision_type: str
    disposition: DecisionDisposition
    action_disposition: DecisionActionDisposition
    action_type: str | None = None
    rationale: str = Field(min_length=1, max_length=10_000)
    decided_at: datetime
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("product_id", "actor_role_ref", "decision_type", "action_type")
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return _bounded(value, name=info.field_name) if value is not None else None

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _bounded(value, name="rationale", maximum=10_000)

    @field_validator("decided_at")
    @classmethod
    def normalize_decided_at(cls, value: datetime) -> datetime:
        return _aware(value, name="decided_at")

    @model_validator(mode="after")
    def validate_scope_time_action_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id or self.subject.product_id != self.product_id:
            raise ValueError("decision intent crossed exact product scope")
        if self.subject.available_at > self.decided_at:
            raise ValueError("decision subject was unavailable when the decision was made")
        if not (self.authenticated_context.authenticated_at <= self.decided_at < self.authenticated_context.expires_at):
            raise ValueError("decision must occur inside the authenticated window")
        if self.action_disposition is DecisionActionDisposition.NO_ACTION:
            if self.action_type is not None:
                raise ValueError("explicit no-action cannot name an action type")
        elif self.action_type is None:
            raise ValueError("authorized action requires an explicit action type")
        _derive_identity(
            self,
            prefix="decision_intent",
            id_field="intent_id",
            digest_field="intent_digest",
        )
        return self


class DecisionV1Alpha1(_StrictFrozenContract):
    """An exact Decision intent paired with Core's durable authorization proof."""

    contract: Literal["ace.core.decision/v1alpha1"] = DECISION_VERSION
    intent: DecisionIntentV1Alpha1
    authorization: GovernedActionAuthorizationProjection
    decision_id: str | None = None
    decision_digest: str | None = None

    @model_validator(mode="after")
    def validate_authorization_and_identity(self) -> Self:
        if self.authorization.authorized_at < self.intent.decided_at:
            raise ValueError("decision authorization cannot predate the decision")
        if any(item.product_id != self.intent.product_id for item in self.authorization.state_preconditions):
            raise ValueError("decision authorization crossed exact product scope")
        _derive_identity(
            self,
            prefix="decision",
            id_field="decision_id",
            digest_field="decision_digest",
        )
        return self


class OutcomeIntentV1Alpha1(_StrictFrozenContract):
    """One later measurement or qualitative result for an exact Decision record."""

    contract: Literal["ace.core.outcome-intent/v1alpha1"] = OUTCOME_INTENT_VERSION
    product_id: str
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    decision: ImmutableRecordReferenceV1
    outcome_type: str
    measure_id: str
    value_json: str
    observed_at: datetime
    recorded_at: datetime
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("product_id", "outcome_type", "measure_id")
    @classmethod
    def validate_references(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("value_json")
    @classmethod
    def validate_value_json(cls, value: str) -> str:
        return _canonical_value_json(value, name="value_json")

    @field_validator("observed_at", "recorded_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if self.authenticated_context.product_id != self.product_id or self.decision.product_id != self.product_id:
            raise ValueError("outcome intent crossed exact product scope")
        if self.decision.record_kind != "decision":
            raise ValueError("outcome must reference one exact Core Decision record")
        if self.decision.available_at > self.observed_at:
            raise ValueError("outcome cannot predate Decision availability")
        if self.recorded_at < self.observed_at:
            raise ValueError("outcome recording cannot predate observation")
        if not (
            self.authenticated_context.authenticated_at <= self.recorded_at < self.authenticated_context.expires_at
        ):
            raise ValueError("outcome must be recorded inside the authenticated window")
        _derive_identity(
            self,
            prefix="outcome_intent",
            id_field="intent_id",
            digest_field="intent_digest",
        )
        return self


class OutcomeV1Alpha1(_StrictFrozenContract):
    """An exact Outcome intent paired with Core's durable authorization proof."""

    contract: Literal["ace.core.outcome/v1alpha1"] = OUTCOME_VERSION
    intent: OutcomeIntentV1Alpha1
    authorization: GovernedActionAuthorizationProjection
    outcome_id: str | None = None
    outcome_digest: str | None = None

    @model_validator(mode="after")
    def validate_authorization_and_identity(self) -> Self:
        if self.authorization.authorized_at < self.intent.recorded_at:
            raise ValueError("outcome authorization cannot predate recording")
        if any(item.product_id != self.intent.product_id for item in self.authorization.state_preconditions):
            raise ValueError("outcome authorization crossed exact product scope")
        _derive_identity(
            self,
            prefix="outcome",
            id_field="outcome_id",
            digest_field="outcome_digest",
        )
        return self


__all__ = [
    "DECISION_INTENT_VERSION",
    "DECISION_VERSION",
    "OUTCOME_INTENT_VERSION",
    "OUTCOME_VERSION",
    "DecisionActionDisposition",
    "DecisionDisposition",
    "DecisionIntentV1Alpha1",
    "DecisionV1Alpha1",
    "OutcomeIntentV1Alpha1",
    "OutcomeV1Alpha1",
]

"""Declarative feedback policy and PREPARED governed-feedback contracts.

The Domain Pack declares eligibility and bounded categorical adjustments.
Intelligence may interpret those declarations into a proposal.  The proposal is
not effective policy and can never grant LIVE authority; Core separately
governs any prepared policy-state revision.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictFloat, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.decisions import DecisionActionDisposition, DecisionDisposition
from ace.core.reasoning import GovernedActionAuthorizationProjection
from ace.core.records import ImmutableRecordReferenceV1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    parse_json_strict,
    sorted_unique,
    validate_digest,
    validate_product_id,
    validate_reference,
    validate_slug,
)
from ace.intelligence.contracts.resource_plane import IntelligenceResourceReferenceV1Alpha1
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    IntelligenceResourceMode,
)

DECISION_OUTCOMES_MODULE_VERSION = "ace.intelligence.decision-outcomes/v1alpha1"
FEEDBACK_PROPOSAL_INTENT_VERSION = "ace.intelligence.feedback-proposal-intent/v1alpha1"
FEEDBACK_PROPOSAL_VERSION = "ace.intelligence.feedback-proposal/v1alpha1"
FEEDBACK_POLICY_STATE_VERSION = "ace.intelligence.feedback-policy-state/v1alpha1"
OUTCOME_PROVENANCE_RETURN_VERSION = "ace.intelligence.outcome-provenance-return/v1alpha1"


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


def _finite(value: Any, *, name: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite float without coercion")
    return value


def _canonical_json_text(value: str, *, name: str) -> str:
    from ace.core.contracts import canonical_json

    try:
        normalized = canonical_json(parse_json_strict(value))
    except (RecursionError, TypeError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{name} must be bounded finite JSON with unique keys") from exc
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


class OutcomeAdjustmentV1(_StrictFrozenContract):
    outcome_value_json: str = Field(min_length=1, max_length=10_000)
    delta: StrictFloat = Field(ge=-1.0, le=1.0)

    @field_validator("outcome_value_json")
    @classmethod
    def validate_value(cls, value: str) -> str:
        return _canonical_json_text(value, name="outcome_value_json")

    @field_validator("delta", mode="before")
    @classmethod
    def validate_delta(cls, value: Any) -> float:
        return _finite(value, name="delta")


class FeedbackPolicyV1(_StrictFrozenContract):
    """One inert eligibility rule and bounded categorical adjustment table."""

    policy_id: str
    persona_id: str
    routing_rule_id: str
    decision_type: str
    eligible_decision_dispositions: tuple[DecisionDisposition, ...] = Field(
        min_length=1,
        max_length=8,
    )
    eligible_action_dispositions: tuple[DecisionActionDisposition, ...] = Field(
        min_length=1,
        max_length=8,
    )
    outcome_type: str
    measure_id: str
    initial_value: StrictFloat = Field(ge=0.0, le=1.0)
    minimum_value: StrictFloat = Field(ge=0.0, le=1.0)
    maximum_value: StrictFloat = Field(ge=0.0, le=1.0)
    adjustments: tuple[OutcomeAdjustmentV1, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator(
        "policy_id",
        "persona_id",
        "routing_rule_id",
        "decision_type",
        "outcome_type",
        "measure_id",
    )
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("initial_value", "minimum_value", "maximum_value", mode="before")
    @classmethod
    def validate_values(cls, value: Any, info) -> float:
        return _finite(value, name=info.field_name)

    @field_validator("eligible_decision_dispositions", mode="before")
    @classmethod
    def preserve_decision_dispositions(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("eligible_decision_dispositions must be an ordered collection")
        try:
            return tuple(item if isinstance(item, DecisionDisposition) else DecisionDisposition(item) for item in value)
        except (TypeError, ValueError) as exc:
            raise ValueError("eligible_decision_dispositions contain an unknown value") from exc

    @field_validator("eligible_decision_dispositions")
    @classmethod
    def normalize_decision_dispositions(
        cls,
        value: tuple[DecisionDisposition, ...],
    ) -> tuple[DecisionDisposition, ...]:
        if len(value) != len(set(value)):
            raise ValueError("eligible decision dispositions must be unique")
        return tuple(sorted(value, key=str))

    @field_validator("eligible_action_dispositions", mode="before")
    @classmethod
    def preserve_action_dispositions(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("eligible_action_dispositions must be an ordered collection")
        try:
            return tuple(
                item if isinstance(item, DecisionActionDisposition) else DecisionActionDisposition(item)
                for item in value
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("eligible_action_dispositions contain an unknown value") from exc

    @field_validator("eligible_action_dispositions")
    @classmethod
    def normalize_action_dispositions(
        cls,
        value: tuple[DecisionActionDisposition, ...],
    ) -> tuple[DecisionActionDisposition, ...]:
        if len(value) != len(set(value)):
            raise ValueError("eligible action dispositions must be unique")
        return tuple(sorted(value, key=str))

    @field_validator("adjustments")
    @classmethod
    def normalize_adjustments(
        cls,
        value: tuple[OutcomeAdjustmentV1, ...],
    ) -> tuple[OutcomeAdjustmentV1, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.outcome_value_json,
            label="outcome adjustments",
        )

    @field_validator("adjustments", mode="before")
    @classmethod
    def preserve_adjustments(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("adjustments must be an ordered collection")
        return tuple(value)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.minimum_value > self.maximum_value:
            raise ValueError("minimum_value cannot exceed maximum_value")
        if not self.minimum_value <= self.initial_value <= self.maximum_value:
            raise ValueError("initial_value must fall inside policy bounds")
        return self

    @property
    def policy_digest(self) -> str:
        return f"sha256:{canonical_hash(self.model_dump(mode='json'))}"


class DecisionOutcomesModuleV1(_StrictFrozenContract):
    contract: Literal["ace.intelligence.decision-outcomes/v1alpha1"] = DECISION_OUTCOMES_MODULE_VERSION
    module_id: str
    feedback_policies: tuple[FeedbackPolicyV1, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("feedback_policies")
    @classmethod
    def normalize_policies(
        cls,
        value: tuple[FeedbackPolicyV1, ...],
    ) -> tuple[FeedbackPolicyV1, ...]:
        return sorted_unique(value, key=lambda item: item.policy_id, label="feedback policies")

    @field_validator("feedback_policies", mode="before")
    @classmethod
    def preserve_policies(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("feedback_policies must be an ordered collection")
        return tuple(value)


class FeedbackProposalIntentV1Alpha1(_StrictFrozenContract):
    """Exact non-effective proposal material before Core authorization."""

    contract: Literal["ace.intelligence.feedback-proposal-intent/v1alpha1"] = FEEDBACK_PROPOSAL_INTENT_VERSION
    product_id: str
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    live_effect: Literal[False] = False
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    policy_id: str
    policy_digest: str
    decision: ImmutableRecordReferenceV1
    outcome: ImmutableRecordReferenceV1
    prior_state_revision_id: str | None = None
    prior_value: StrictFloat = Field(ge=0.0, le=1.0)
    outcome_value_json: str
    adjustment: StrictFloat = Field(ge=-1.0, le=1.0)
    proposed_value: StrictFloat = Field(ge=0.0, le=1.0)
    proposed_at: datetime
    intent_id: str | None = None
    intent_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("policy_id")
    @classmethod
    def validate_policy_id(cls, value: str) -> str:
        return validate_slug(value, name="policy_id")

    @field_validator("policy_digest", "intent_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("prior_state_revision_id")
    @classmethod
    def validate_prior_revision(cls, value: str | None) -> str | None:
        return validate_reference(value, name="prior_state_revision_id") if value is not None else None

    @field_validator("prior_value", "adjustment", "proposed_value", mode="before")
    @classmethod
    def validate_numeric_values(cls, value: Any, info) -> float:
        return _finite(value, name=info.field_name)

    @field_validator("outcome_value_json")
    @classmethod
    def validate_outcome_value(cls, value: str) -> str:
        return _canonical_json_text(value, name="outcome_value_json")

    @field_validator("proposed_at")
    @classmethod
    def normalize_proposed_at(cls, value: datetime) -> datetime:
        return _aware(value, name="proposed_at")

    @model_validator(mode="after")
    def validate_scope_time_and_identity(self) -> Self:
        if (
            self.activation_revision.product_id != self.product_id
            or self.decision.product_id != self.product_id
            or self.outcome.product_id != self.product_id
        ):
            raise ValueError("feedback proposal crossed exact product scope")
        if self.decision.record_space != "prepared" or self.decision.record_kind != "decision":
            raise ValueError("feedback proposal requires one exact PREPARED Decision")
        if self.outcome.record_space != "prepared" or self.outcome.record_kind != "outcome":
            raise ValueError("feedback proposal requires one exact PREPARED Outcome")
        if self.decision.available_at > self.outcome.as_of:
            raise ValueError("feedback Outcome cannot predate its Decision")
        if self.outcome.available_at > self.proposed_at:
            raise ValueError("feedback proposal cannot predate Outcome availability")
        _derive_identity(
            self,
            prefix="feedback_proposal_intent",
            id_field="intent_id",
            digest_field="intent_digest",
        )
        return self


class FeedbackProposalV1Alpha1(_StrictFrozenContract):
    """An exact proposal intent paired with Core's durable authorization proof."""

    contract: Literal["ace.intelligence.feedback-proposal/v1alpha1"] = FEEDBACK_PROPOSAL_VERSION
    intent: FeedbackProposalIntentV1Alpha1
    authorization: GovernedActionAuthorizationProjection
    proposal_id: str | None = None
    proposal_digest: str | None = None

    @field_validator("proposal_digest")
    @classmethod
    def validate_proposal_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @model_validator(mode="after")
    def validate_authorization_and_identity(self) -> Self:
        if self.authorization.authorized_at < self.intent.proposed_at:
            raise ValueError("feedback proposal authorization cannot predate proposal time")
        if any(item.product_id != self.intent.product_id for item in self.authorization.state_preconditions):
            raise ValueError("feedback proposal authorization crossed exact product scope")
        _derive_identity(
            self,
            prefix="feedback_proposal",
            id_field="proposal_id",
            digest_field="proposal_digest",
        )
        return self


class OutcomeProvenanceReturnV1Alpha1(_StrictFrozenContract):
    """Attributed return of the exact Intelligence used by one recorded Outcome.

    This is a companion receipt for the existing Core Outcome. It records no
    outbound delivery, acknowledgement, ranking, recalculation, or trust effect.
    """

    contract: Literal["ace.intelligence.outcome-provenance-return/v1alpha1"] = OUTCOME_PROVENANCE_RETURN_VERSION
    product_id: str
    actor_ref: str
    decision: ImmutableRecordReferenceV1
    outcome: ImmutableRecordReferenceV1
    consumed_intelligence: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(
        min_length=1,
        max_length=256,
    )
    returned_at: datetime
    return_id: str | None = None
    return_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("actor_ref")
    @classmethod
    def validate_actor_ref(cls, value: str) -> str:
        return validate_reference(value, name="actor_ref")

    @field_validator("return_digest")
    @classmethod
    def validate_return_digest(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("returned_at")
    @classmethod
    def normalize_returned_at(cls, value: datetime) -> datetime:
        return _aware(value, name="returned_at")

    @field_validator("consumed_intelligence")
    @classmethod
    def normalize_consumed_intelligence(
        cls,
        value: tuple[IntelligenceResourceReferenceV1Alpha1, ...],
    ) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
        keys = tuple(
            (item.resource_kind.value, item.resource_id, item.revision, item.resource_digest) for item in value
        )
        if len(keys) != len(set(keys)):
            raise ValueError("consumed Intelligence references must be unique")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.resource_kind.value,
                    item.resource_id,
                    item.revision,
                    item.resource_digest,
                ),
            )
        )

    @model_validator(mode="after")
    def validate_exact_return_and_identity(self) -> Self:
        if (
            self.decision.product_id != self.product_id
            or self.outcome.product_id != self.product_id
            or any(item.product_id != self.product_id for item in self.consumed_intelligence)
        ):
            raise ValueError("Outcome provenance return crossed exact product scope")
        if self.decision.record_space != "prepared" or self.decision.record_kind != "decision":
            raise ValueError("Outcome provenance return requires one exact PREPARED Decision")
        if self.outcome.record_space != "prepared" or self.outcome.record_kind != "outcome":
            raise ValueError("Outcome provenance return requires one exact PREPARED Outcome")
        if self.decision.available_at > self.outcome.as_of:
            raise ValueError("Outcome provenance return cannot predate Decision availability")
        if self.outcome.available_at > self.returned_at:
            raise ValueError("provenance return cannot predate Outcome availability")
        if any(
            item.as_of > self.decision.as_of or item.available_at > self.decision.as_of
            for item in self.consumed_intelligence
        ):
            raise ValueError("consumed Intelligence was unavailable when the Decision was made")
        _derive_identity(
            self,
            prefix="outcome_provenance_return",
            id_field="return_id",
            digest_field="return_digest",
        )
        return self


class FeedbackPolicyStateV1Alpha1(_StrictFrozenContract):
    """One Core-governed PREPARED policy value derived from an approved proposal."""

    contract: Literal["ace.intelligence.feedback-policy-state/v1alpha1"] = FEEDBACK_POLICY_STATE_VERSION
    product_id: str
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED
    live_effect: Literal[False] = False
    activation_revision: ActivationRevisionReferenceV1Alpha1
    pack: CompiledPackRefV1
    policy_id: str
    policy_digest: str
    sequence: int = Field(ge=1)
    prior_revision_id: str | None = None
    value: StrictFloat = Field(ge=0.0, le=1.0)
    source_proposal: ImmutableRecordReferenceV1
    effective_at: datetime
    state_id: str | None = None
    revision_id: str | None = None
    revision_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_product_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("policy_id")
    @classmethod
    def validate_policy_id(cls, value: str) -> str:
        return validate_slug(value, name="policy_id")

    @field_validator("policy_digest", "revision_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("prior_revision_id", "state_id", "revision_id")
    @classmethod
    def validate_references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: Any) -> float:
        return _finite(value, name="value")

    @field_validator("effective_at")
    @classmethod
    def normalize_effective_at(cls, value: datetime) -> datetime:
        return _aware(value, name="effective_at")

    @model_validator(mode="after")
    def validate_scope_lineage_and_identity(self) -> Self:
        if self.activation_revision.product_id != self.product_id or self.source_proposal.product_id != self.product_id:
            raise ValueError("feedback policy state crossed exact product scope")
        if self.source_proposal.record_space != "prepared" or self.source_proposal.record_kind != "feedback_proposal":
            raise ValueError("feedback state requires one exact PREPARED proposal")
        if self.source_proposal.available_at > self.effective_at:
            raise ValueError("feedback state cannot predate proposal availability")
        if self.sequence == 1 and self.prior_revision_id is not None:
            raise ValueError("first feedback state cannot name a prior revision")
        if self.sequence > 1 and self.prior_revision_id is None:
            raise ValueError("later feedback state requires a prior revision")

        expected_state_id = f"feedback_policy:{canonical_hash([self.product_id, self.policy_id])[:32]}"
        material = self.model_dump(
            mode="json",
            exclude={"state_id", "revision_id", "revision_digest"},
        )
        digest = canonical_hash(material)
        expected_revision_id = f"feedback_policy_revision:{digest[:32]}"
        expected_revision_digest = f"sha256:{digest}"
        if self.state_id is not None and self.state_id != expected_state_id:
            raise ValueError("feedback state_id does not match product and policy")
        if self.revision_id is not None and self.revision_id != expected_revision_id:
            raise ValueError("feedback revision_id does not match exact state material")
        if self.revision_digest is not None and self.revision_digest != expected_revision_digest:
            raise ValueError("feedback revision_digest does not match exact state material")
        object.__setattr__(self, "state_id", expected_state_id)
        object.__setattr__(self, "revision_id", expected_revision_id)
        object.__setattr__(self, "revision_digest", expected_revision_digest)
        return self


__all__ = [
    "DECISION_OUTCOMES_MODULE_VERSION",
    "FEEDBACK_POLICY_STATE_VERSION",
    "FEEDBACK_PROPOSAL_INTENT_VERSION",
    "FEEDBACK_PROPOSAL_VERSION",
    "OUTCOME_PROVENANCE_RETURN_VERSION",
    "DecisionOutcomesModuleV1",
    "FeedbackPolicyStateV1Alpha1",
    "FeedbackPolicyV1",
    "FeedbackProposalIntentV1Alpha1",
    "FeedbackProposalV1Alpha1",
    "OutcomeAdjustmentV1",
    "OutcomeProvenanceReturnV1Alpha1",
]

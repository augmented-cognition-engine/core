"""Declarative, domain-neutral detector configuration contracts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

from ace.core.contracts import FrozenContract
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    normalized_strings,
    sorted_unique,
    validate_slug,
)

DETECTION_MODULE_VERSION = "ace.intelligence.detection/v1alpha1"
DETECTION_MODULE_V1ALPHA2_VERSION = "ace.intelligence.detection/v1alpha2"
DETECTION_MODULE_V1ALPHA3_VERSION = "ace.intelligence.detection/v1alpha3"
MAX_TRANSITION_VALUE_CHARS = 500


class NumericDeltaMetric(StrEnum):
    """Supported domain-neutral comparisons for the alpha numeric detector."""

    ABSOLUTE_CHANGE = "absolute_change"
    PERCENT_CHANGE = "percent_change"


class DeltaDirection(StrEnum):
    """Direction filters applied after a numeric delta is computed."""

    ANY = "any"
    INCREASE = "increase"
    DECREASE = "decrease"


class NumericDeltaRuleV1(FrozenContract):
    """A declarative request to compare one numeric attribute with its prior value.

    The rule names domain types but contains no implementation. Intelligence owns the
    ``numeric_delta`` strategy; a pack supplies the watched attribute and materiality policy.
    """

    detector_id: str
    entity_type_id: str
    attribute_id: str
    baseline: Literal["prior_snapshot"] = "prior_snapshot"
    context_attribute_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    metric: NumericDeltaMetric
    threshold: StrictInt | StrictFloat = Field(gt=0)
    direction: DeltaDirection = DeltaDirection.ANY
    shift_type: str
    signal_type: str

    @field_validator(
        "detector_id",
        "entity_type_id",
        "attribute_id",
        "shift_type",
        "signal_type",
    )
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("context_attribute_ids", mode="before")
    @classmethod
    def normalize_context_attribute_ids(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="context attribute ID")
            for item in normalized_strings(value, label="context attribute IDs")
        )

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, value: int | float) -> int | float:
        if isinstance(value, bool):
            raise ValueError("numeric delta threshold must be a finite number")
        if isinstance(value, int) and abs(value) > 2**53 - 1:
            raise ValueError("integer thresholds must stay within the exact IEEE-754 range")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("numeric delta threshold must be a finite number")
        return value

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.attribute_id in self.context_attribute_ids:
            raise ValueError("the watched attribute cannot also be a comparison context attribute")
        if len(self.context_attribute_ids) != len(set(self.context_attribute_ids)):
            raise ValueError("context attribute IDs must be unique")
        object.__setattr__(self, "context_attribute_ids", tuple(sorted(self.context_attribute_ids)))
        return self


class DetectionModuleV1(FrozenContract):
    """One immutable module of declarative detector rules."""

    contract: Literal["ace.intelligence.detection/v1alpha1"] = DETECTION_MODULE_VERSION
    module_id: str
    numeric_delta_rules: tuple[NumericDeltaRuleV1, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("numeric_delta_rules", mode="before")
    @classmethod
    def preserve_strict_collection(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("numeric_delta_rules must be a collection")
        return value

    @field_validator("numeric_delta_rules")
    @classmethod
    def normalize_rules(
        cls,
        value: tuple[NumericDeltaRuleV1, ...],
    ) -> tuple[NumericDeltaRuleV1, ...]:
        return sorted_unique(value, key=lambda item: item.detector_id, label="numeric delta rules")


class CategoricalTransitionV1(FrozenContract):
    """One exact declared value transition; the values are inert pack vocabulary."""

    from_value: StrictStr = Field(min_length=1, max_length=MAX_TRANSITION_VALUE_CHARS)
    to_value: StrictStr = Field(min_length=1, max_length=MAX_TRANSITION_VALUE_CHARS)

    @model_validator(mode="after")
    def validate_transition(self) -> Self:
        if self.from_value == self.to_value:
            raise ValueError("a categorical transition cannot map a value onto itself")
        return self


class CategoricalTransitionRuleV1(FrozenContract):
    """A declarative request to compare one categorical attribute with its prior value.

    The rule names domain types and exact configured transitions but contains no
    implementation. Intelligence owns the ``categorical_transition`` strategy; a pack
    supplies the watched attribute and the transitions it considers material.
    """

    detector_id: str
    entity_type_id: str
    attribute_id: str
    baseline: Literal["prior_snapshot"] = "prior_snapshot"
    context_attribute_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    transitions: tuple[CategoricalTransitionV1, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )
    shift_type: str
    signal_type: str

    @field_validator(
        "detector_id",
        "entity_type_id",
        "attribute_id",
        "shift_type",
        "signal_type",
    )
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("context_attribute_ids", mode="before")
    @classmethod
    def normalize_context_attribute_ids(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="context attribute ID")
            for item in normalized_strings(value, label="context attribute IDs")
        )

    @field_validator("transitions", mode="before")
    @classmethod
    def preserve_strict_transitions(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError("transitions must be a collection")
        return value

    @field_validator("transitions")
    @classmethod
    def normalize_transitions(
        cls,
        value: tuple[CategoricalTransitionV1, ...],
    ) -> tuple[CategoricalTransitionV1, ...]:
        return sorted_unique(
            value,
            key=lambda item: (item.from_value, item.to_value),
            label="categorical transitions",
        )

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.attribute_id in self.context_attribute_ids:
            raise ValueError("the watched attribute cannot also be a comparison context attribute")
        if len(self.context_attribute_ids) != len(set(self.context_attribute_ids)):
            raise ValueError("context attribute IDs must be unique")
        object.__setattr__(self, "context_attribute_ids", tuple(sorted(self.context_attribute_ids)))
        return self


class ContentRevisionRuleV1(FrozenContract):
    """A declarative request to watch one text attribute for any exact change.

    The rule names domain types but contains no implementation. Intelligence owns
    the ``content_revision`` strategy; a pack supplies the watched attribute and
    the vocabulary its Shift and Signal carry.

    There is deliberately no threshold and no transition table. A document's text
    cannot be enumerated the way a lifecycle stage can, and a rule that guessed
    which edits "count" would either fire on every re-read or silently swallow a
    real revision. Equality is the whole materiality test.
    """

    detector_id: str
    entity_type_id: str
    attribute_id: str
    baseline: Literal["prior_snapshot"] = "prior_snapshot"
    context_attribute_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    shift_type: str
    signal_type: str

    @field_validator(
        "detector_id",
        "entity_type_id",
        "attribute_id",
        "shift_type",
        "signal_type",
    )
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("context_attribute_ids", mode="before")
    @classmethod
    def normalize_context_attribute_ids(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="context attribute ID")
            for item in normalized_strings(value, label="context attribute IDs")
        )

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.attribute_id in self.context_attribute_ids:
            raise ValueError("the watched attribute cannot also be a comparison context attribute")
        if len(self.context_attribute_ids) != len(set(self.context_attribute_ids)):
            raise ValueError("context attribute IDs must be unique")
        object.__setattr__(self, "context_attribute_ids", tuple(sorted(self.context_attribute_ids)))
        return self


class DetectionModuleV1Alpha3(FrozenContract):
    """One immutable module of numeric, categorical, and content-revision rules.

    Published module contracts are immutable, so this ships alongside
    ``v1alpha1``/``v1alpha2`` rather than widening either.
    """

    contract: Literal["ace.intelligence.detection/v1alpha3"] = DETECTION_MODULE_V1ALPHA3_VERSION
    module_id: str
    numeric_delta_rules: tuple[NumericDeltaRuleV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_DECLARATIONS,
    )
    categorical_transition_rules: tuple[CategoricalTransitionRuleV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_DECLARATIONS,
    )
    content_revision_rules: tuple[ContentRevisionRuleV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator(
        "numeric_delta_rules",
        "categorical_transition_rules",
        "content_revision_rules",
        mode="before",
    )
    @classmethod
    def preserve_strict_collection(cls, value: Any, info) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{info.field_name} must be a collection")
        return value

    @field_validator("numeric_delta_rules")
    @classmethod
    def normalize_numeric_rules(
        cls,
        value: tuple[NumericDeltaRuleV1, ...],
    ) -> tuple[NumericDeltaRuleV1, ...]:
        return sorted_unique(value, key=lambda item: item.detector_id, label="numeric delta rules")

    @field_validator("categorical_transition_rules")
    @classmethod
    def normalize_categorical_rules(
        cls,
        value: tuple[CategoricalTransitionRuleV1, ...],
    ) -> tuple[CategoricalTransitionRuleV1, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.detector_id,
            label="categorical transition rules",
        )

    @field_validator("content_revision_rules")
    @classmethod
    def normalize_content_rules(
        cls,
        value: tuple[ContentRevisionRuleV1, ...],
    ) -> tuple[ContentRevisionRuleV1, ...]:
        return sorted_unique(value, key=lambda item: item.detector_id, label="content revision rules")

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        families = (self.numeric_delta_rules, self.categorical_transition_rules, self.content_revision_rules)
        if not any(families):
            raise ValueError("a detection module must declare at least one detector rule")
        detector_ids = [item.detector_id for family in families for item in family]
        if len(detector_ids) != len(set(detector_ids)):
            raise ValueError("detector IDs must be unique across detector rule families")
        return self


class DetectionModuleV1Alpha2(FrozenContract):
    """One immutable module of declarative numeric and categorical detector rules."""

    contract: Literal["ace.intelligence.detection/v1alpha2"] = DETECTION_MODULE_V1ALPHA2_VERSION
    module_id: str
    numeric_delta_rules: tuple[NumericDeltaRuleV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_DECLARATIONS,
    )
    categorical_transition_rules: tuple[CategoricalTransitionRuleV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("numeric_delta_rules", "categorical_transition_rules", mode="before")
    @classmethod
    def preserve_strict_collection(cls, value: Any, info) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{info.field_name} must be a collection")
        return value

    @field_validator("numeric_delta_rules")
    @classmethod
    def normalize_numeric_rules(
        cls,
        value: tuple[NumericDeltaRuleV1, ...],
    ) -> tuple[NumericDeltaRuleV1, ...]:
        return sorted_unique(value, key=lambda item: item.detector_id, label="numeric delta rules")

    @field_validator("categorical_transition_rules")
    @classmethod
    def normalize_categorical_rules(
        cls,
        value: tuple[CategoricalTransitionRuleV1, ...],
    ) -> tuple[CategoricalTransitionRuleV1, ...]:
        return sorted_unique(
            value,
            key=lambda item: item.detector_id,
            label="categorical transition rules",
        )

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        if not self.numeric_delta_rules and not self.categorical_transition_rules:
            raise ValueError("a detection module must declare at least one detector rule")
        detector_ids = [item.detector_id for item in self.numeric_delta_rules] + [
            item.detector_id for item in self.categorical_transition_rules
        ]
        if len(detector_ids) != len(set(detector_ids)):
            raise ValueError("detector IDs must be unique across detector rule families")
        return self

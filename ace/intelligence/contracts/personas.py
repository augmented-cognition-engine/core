"""Declarative persona archetypes and attention-routing policy."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import Field, StrictFloat, field_validator

from ace.core.contracts import FrozenContract
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    normalized_strings,
    sorted_unique,
    validate_slug,
)

PERSONAS_MODULE_VERSION = "ace.intelligence.personas/v1alpha1"


class PersonaArchetypeV1(FrozenContract):
    persona_id: str
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1_000)

    @field_validator("persona_id")
    @classmethod
    def validate_persona_id(cls, value: str) -> str:
        return validate_slug(value, name="persona_id")


class SignalRoutingRuleV1(FrozenContract):
    routing_rule_id: str
    signal_type: str
    persona_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    minimum_confidence: StrictFloat = Field(ge=0.0, le=1.0)
    brief_template_id: str | None = None

    @field_validator("routing_rule_id", "signal_type", "brief_template_id")
    @classmethod
    def validate_ids(cls, value: str | None, info) -> str | None:
        return validate_slug(value, name=info.field_name) if value is not None else None

    @field_validator("persona_ids", mode="before")
    @classmethod
    def normalize_personas(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="persona_id")
            for item in normalized_strings(value, label="persona IDs", maximum=64)
        )

    @field_validator("minimum_confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float:
        if type(value) is not float or not math.isfinite(value):
            raise ValueError("minimum_confidence must be a finite float without coercion")
        return value


class PersonasModuleV1(FrozenContract):
    contract: Literal["ace.intelligence.personas/v1alpha1"] = PERSONAS_MODULE_VERSION
    module_id: str
    personas: tuple[PersonaArchetypeV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    signal_routing_rules: tuple[SignalRoutingRuleV1, ...] = Field(
        min_length=1,
        max_length=MAX_DECLARATIONS,
    )

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("personas")
    @classmethod
    def normalize_personas(
        cls,
        value: tuple[PersonaArchetypeV1, ...],
    ) -> tuple[PersonaArchetypeV1, ...]:
        return sorted_unique(value, key=lambda item: item.persona_id, label="personas")

    @field_validator("signal_routing_rules")
    @classmethod
    def normalize_routes(
        cls,
        value: tuple[SignalRoutingRuleV1, ...],
    ) -> tuple[SignalRoutingRuleV1, ...]:
        return sorted_unique(value, key=lambda item: item.routing_rule_id, label="signal routing rules")

"""Declarative initial-corpus orientation policy for one first Brief.

An orientation policy names the exact Brief template and personas a Domain Pack
selects for its first Brief over an already admitted corpus. It carries no
change detector, no Signal-routing rule, and no synthetic change vocabulary:
the initial-corpus first Brief is an orientation over admitted material at one
exact time, not a change event. Personas may be declared here so a Pack that
ships no Signal-routing policy yet can still name who reads the first Brief.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from ace.core.contracts import FrozenContract
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    normalized_strings,
    sorted_unique,
    validate_slug,
)
from ace.intelligence.contracts.personas import PersonaArchetypeV1

ORIENTATION_MODULE_VERSION = "ace.intelligence.orientation/v1alpha1"


class InitialOrientationPolicyV1(FrozenContract):
    """One exact template-and-persona selection for the initial-corpus first Brief."""

    policy_id: str
    brief_template_id: str
    persona_ids: tuple[str, ...] = Field(min_length=1, max_length=64)

    @field_validator("policy_id", "brief_template_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("persona_ids", mode="before")
    @classmethod
    def normalize_personas(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="persona_id")
            for item in normalized_strings(value, label="persona IDs", maximum=64)
        )


class OrientationModuleV1(FrozenContract):
    """One immutable module of initial-corpus orientation policy.

    Personas are declared inline so orientation never forces a Pack to declare
    Signal-routing policy; a Pack that already ships a personas module may
    reference those personas instead of redeclaring them here.
    """

    contract: Literal["ace.intelligence.orientation/v1alpha1"] = ORIENTATION_MODULE_VERSION
    module_id: str
    personas: tuple[PersonaArchetypeV1, ...] = Field(
        default_factory=tuple,
        max_length=MAX_DECLARATIONS,
    )
    initial_orientation_policies: tuple[InitialOrientationPolicyV1, ...] = Field(
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

    @field_validator("initial_orientation_policies")
    @classmethod
    def normalize_policies(
        cls,
        value: tuple[InitialOrientationPolicyV1, ...],
    ) -> tuple[InitialOrientationPolicyV1, ...]:
        return sorted_unique(value, key=lambda item: item.policy_id, label="initial orientation policies")


__all__ = [
    "ORIENTATION_MODULE_VERSION",
    "InitialOrientationPolicyV1",
    "OrientationModuleV1",
]

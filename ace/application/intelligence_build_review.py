"""Activation-neutral presentation of one exact Intelligence build proposal.

The projection is derived from inert installed material and reviewed source
selections.  It contains no approval, grant, provider binding, activation
revision, or executable instruction.  Atrium can therefore review the exact
proposal without treating UI rendering as authority.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    IntelligenceBuildEffect,
)
from ace.application.recorded_source_selection import (
    RecordedSourceSelectionReferenceV1Alpha1,
    RecordedSourceSelectionV1Alpha1,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import validate_digest, validate_reference, validate_slug
from ace.intelligence.contracts.detection import (
    DETECTION_MODULE_V1ALPHA2_VERSION,
    DETECTION_MODULE_VERSION,
    CategoricalTransitionRuleV1,
    DetectionModuleV1,
    DetectionModuleV1Alpha2,
    NumericDeltaRuleV1,
)
from ace.intelligence.contracts.intelligence_builder_presentation import (
    IntelligenceOnboardingProfileV1Alpha1,
)
from ace.intelligence.contracts.pack import (
    ONTOLOGY_MODULE_VERSION,
    CompiledDomainPackV1,
    OntologyModuleV1,
)

INTELLIGENCE_BUILD_REVIEW_PROJECTION_VERSION = "ace.application.intelligence-build-review-projection/v1alpha1"


class IntelligenceBuildReviewSourceV1Alpha1(FrozenContract):
    selection: RecordedSourceSelectionReferenceV1Alpha1
    label: str = Field(min_length=1, max_length=240)
    evidence_role: str
    source_uri: str = Field(min_length=3, max_length=2_048)
    source_definition_ref: str
    entity_type_id: str
    entity_ref: str
    observed_at: datetime

    @field_validator("evidence_role", "entity_type_id")
    @classmethod
    def _slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("source_definition_ref", "entity_ref")
    @classmethod
    def _references(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)


class IntelligenceBuildReviewConceptV1Alpha1(FrozenContract):
    entity_type_id: str
    entity_ref: str
    display_name: str = Field(min_length=1, max_length=240)
    source_selections: tuple[RecordedSourceSelectionReferenceV1Alpha1, ...] = Field(
        min_length=1,
        max_length=64,
    )

    @field_validator("entity_type_id")
    @classmethod
    def _slug(cls, value: str) -> str:
        return validate_slug(value, name="entity_type_id")

    @field_validator("entity_ref")
    @classmethod
    def _reference(cls, value: str) -> str:
        return validate_reference(value, name="entity_ref")

    @field_validator("source_selections")
    @classmethod
    def _unique_sources(
        cls,
        value: tuple[RecordedSourceSelectionReferenceV1Alpha1, ...],
    ) -> tuple[RecordedSourceSelectionReferenceV1Alpha1, ...]:
        if len(value) != len(set(value)):
            raise ValueError("concept source selections must be unique")
        return tuple(sorted(value, key=lambda item: (item.source_group_id, item.selection_id)))


class IntelligenceBuildReviewWatchV1Alpha1(FrozenContract):
    detector_id: str
    detector_family: Literal["numeric_delta", "categorical_transition"]
    entity_type_id: str
    entity_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    attribute_id: str
    change_rule: str = Field(min_length=1, max_length=1_000)
    shift_type: str
    signal_type: str
    cadence_id: str
    cadence_label: str = Field(min_length=1, max_length=160)

    @field_validator(
        "detector_id",
        "entity_type_id",
        "attribute_id",
        "shift_type",
        "signal_type",
        "cadence_id",
    )
    @classmethod
    def _slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("entity_refs")
    @classmethod
    def _entity_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(validate_reference(item, name="entity_ref") for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("watch entity references must be unique")
        return normalized


class IntelligenceBuildReviewEffectV1Alpha1(FrozenContract):
    effect: IntelligenceBuildEffect
    label: str = Field(min_length=1, max_length=160)
    what: str = Field(min_length=1, max_length=1_000)
    why: str = Field(min_length=1, max_length=1_000)
    how: str = Field(min_length=1, max_length=1_000)
    when: str = Field(min_length=1, max_length=1_000)
    unknowns: tuple[str, ...] = Field(min_length=1, max_length=16)


class IntelligenceBuildReviewProjectionV1Alpha1(FrozenContract):
    """Content-addressed, activation-neutral material shown during review."""

    contract: Literal["ace.application.intelligence-build-review-projection/v1alpha1"] = (
        INTELLIGENCE_BUILD_REVIEW_PROJECTION_VERSION
    )
    request_id: str
    request_digest: str
    profile_id: str
    profile_digest: str
    pack_reference: CompiledPackRefV1
    subject: str = Field(min_length=8, max_length=2_000)
    outcome_id: str
    outcome_label: str = Field(min_length=1, max_length=160)
    sources: tuple[IntelligenceBuildReviewSourceV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )
    concepts: tuple[IntelligenceBuildReviewConceptV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )
    watches: tuple[IntelligenceBuildReviewWatchV1Alpha1, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )
    cadence_id: str
    cadence_label: str = Field(min_length=1, max_length=160)
    cadence_description: str = Field(min_length=1, max_length=1_000)
    effects: tuple[IntelligenceBuildReviewEffectV1Alpha1, ...] = Field(
        min_length=4,
        max_length=4,
    )
    projection_id: str | None = None
    projection_digest: str | None = None

    @field_validator("request_id", "profile_id", "projection_id")
    @classmethod
    def _references(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("request_digest", "profile_digest", "projection_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("outcome_id", "cadence_id")
    @classmethod
    def _slugs(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("sources")
    @classmethod
    def _unique_sources(
        cls,
        value: tuple[IntelligenceBuildReviewSourceV1Alpha1, ...],
    ) -> tuple[IntelligenceBuildReviewSourceV1Alpha1, ...]:
        keys = [item.selection.selection_id for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("review sources must be unique")
        return tuple(sorted(value, key=lambda item: item.selection.selection_id))

    @field_validator("concepts")
    @classmethod
    def _unique_concepts(
        cls,
        value: tuple[IntelligenceBuildReviewConceptV1Alpha1, ...],
    ) -> tuple[IntelligenceBuildReviewConceptV1Alpha1, ...]:
        keys = [(item.entity_type_id, item.entity_ref) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("review concepts must be unique")
        return tuple(sorted(value, key=lambda item: (item.entity_type_id, item.entity_ref)))

    @field_validator("watches")
    @classmethod
    def _unique_watches(
        cls,
        value: tuple[IntelligenceBuildReviewWatchV1Alpha1, ...],
    ) -> tuple[IntelligenceBuildReviewWatchV1Alpha1, ...]:
        keys = [item.detector_id for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("review watches must be unique")
        return tuple(sorted(value, key=lambda item: item.detector_id))

    @field_validator("effects")
    @classmethod
    def _exact_effects(
        cls,
        value: tuple[IntelligenceBuildReviewEffectV1Alpha1, ...],
    ) -> tuple[IntelligenceBuildReviewEffectV1Alpha1, ...]:
        if tuple(item.effect for item in value) != REQUIRED_INTELLIGENCE_BUILD_EFFECTS:
            raise ValueError("review effects must preserve the bounded onboarding sequence")
        return value

    @model_validator(mode="after")
    def _identity(self) -> Self:
        selection_refs = {item.selection for item in self.sources}
        if any(not set(item.source_selections).issubset(selection_refs) for item in self.concepts):
            raise ValueError("review concept crossed exact source selections")
        concept_refs = {(item.entity_type_id, item.entity_ref) for item in self.concepts}
        if any(
            (watch.entity_type_id, entity_ref) not in concept_refs
            for watch in self.watches
            for entity_ref in watch.entity_refs
        ):
            raise ValueError("review watch crossed exact reviewed concepts")
        material = self.model_dump(mode="json", exclude={"projection_id", "projection_digest"})
        digest = canonical_hash(material)
        expected_id = f"intelligence_build_review:{digest[:32]}"
        expected_digest = f"sha256:{digest}"
        if self.projection_id not in {None, expected_id}:
            raise ValueError("review projection ID does not match exact material")
        if self.projection_digest not in {None, expected_digest}:
            raise ValueError("review projection digest does not match exact material")
        object.__setattr__(self, "projection_id", expected_id)
        object.__setattr__(self, "projection_digest", expected_digest)
        return self


def _typed_modules(pack: CompiledDomainPackV1) -> tuple[dict[str, str], dict[str, object]]:
    entity_labels: dict[str, str] = {}
    detectors: dict[str, object] = {}
    for module in pack.modules:
        if module.contract == ONTOLOGY_MODULE_VERSION:
            ontology = OntologyModuleV1.model_validate_json(module.canonical_payload)
            for entity in ontology.entity_types:
                entity_labels[entity.entity_type_id] = entity.display_name or entity.entity_type_id
        elif module.contract == DETECTION_MODULE_VERSION:
            detection = DetectionModuleV1.model_validate_json(module.canonical_payload)
            detectors.update((item.detector_id, item) for item in detection.numeric_delta_rules)
        elif module.contract == DETECTION_MODULE_V1ALPHA2_VERSION:
            detection = DetectionModuleV1Alpha2.model_validate_json(module.canonical_payload)
            detectors.update((item.detector_id, item) for item in detection.numeric_delta_rules)
            detectors.update((item.detector_id, item) for item in detection.categorical_transition_rules)
    return entity_labels, detectors


def _change_rule(rule: NumericDeltaRuleV1 | CategoricalTransitionRuleV1) -> tuple[str, str]:
    if isinstance(rule, NumericDeltaRuleV1):
        metric = rule.metric.value.replace("_", " ")
        direction = rule.direction.value.replace("_", " ")
        return "numeric_delta", f"{metric} threshold {rule.threshold:g}; direction {direction}"
    transitions = "; ".join(f"{item.from_value} → {item.to_value}" for item in rule.transitions)
    return "categorical_transition", f"Declared transitions: {transitions}"


def _effect_reviews(
    *,
    source_count: int,
    concept_count: int,
    watch_count: int,
    cadence_label: str,
    outcome_description: str,
) -> tuple[IntelligenceBuildReviewEffectV1Alpha1, ...]:
    material: dict[IntelligenceBuildEffect, tuple[str, str, str, str, str, tuple[str, ...]]] = {
        "connect_sources": (
            "Review exact evidence",
            f"{source_count} exact recorded source selection(s) are proposed.",
            outcome_description,
            "ACE would admit only the reviewed selection identities after separate approval and authority checks.",
            "Not connected now; any admission would occur after a deliberate activation decision.",
            ("Runtime availability, later corrections, and credential requirements remain unverified.",),
        ),
        "map_concepts": (
            "Map the starting concepts",
            f"{concept_count} exact entity reference(s) are proposed as the starting concept map.",
            outcome_description,
            "ACE would preserve each entity type, reference, and source-selection lineage.",
            "Not mapped now; mapping would follow admitted evidence and separate authority checks.",
            ("Aliases, duplicates, and relationships may require later review.",),
        ),
        "activate_watch": (
            "Configure the starting watches",
            f"{watch_count} declared detector rule(s) are proposed at the {cadence_label} cadence.",
            outcome_description,
            "ACE would use only the exact Pack detector IDs and reviewed entity references shown here.",
            "Not watching now; scheduling would begin only after deliberate activation.",
            ("No baseline, first evaluation, or alert has been produced yet.",),
        ),
        "create_first_brief": (
            "Assemble the first cited Brief",
            "One cited Brief is proposed as the first reviewable intelligence output.",
            outcome_description,
            "ACE would synthesize only after sources, concepts, and watches have governed durable lineage.",
            "Not generated now; the Brief would follow admitted evidence and a material detected change.",
            ("No claims, conclusions, or recommendations have been generated yet.",),
        ),
    }
    return tuple(
        IntelligenceBuildReviewEffectV1Alpha1(
            effect=effect,
            label=material[effect][0],
            what=material[effect][1],
            why=material[effect][2],
            how=material[effect][3],
            when=material[effect][4],
            unknowns=material[effect][5],
        )
        for effect in REQUIRED_INTELLIGENCE_BUILD_EFFECTS
    )


def project_intelligence_build_review(
    *,
    request_id: str,
    request_digest: str,
    subject: str,
    outcome_id: str,
    cadence_id: str,
    profile: IntelligenceOnboardingProfileV1Alpha1,
    pack_reference: CompiledPackRefV1,
    pack: CompiledDomainPackV1,
    selections: tuple[RecordedSourceSelectionV1Alpha1, ...],
) -> IntelligenceBuildReviewProjectionV1Alpha1:
    """Derive exact review material without consulting activation bindings."""

    if profile.profile_digest is None:
        raise ValueError("review projection requires the exact installed profile digest")
    outcome = next((item for item in profile.outcomes if item.outcome_id == outcome_id), None)
    cadence = next((item for item in profile.cadences if item.cadence_id == cadence_id), None)
    if outcome is None or cadence is None:
        raise ValueError("review projection crossed the installed profile selection")
    groups = {item.source_group_id: item for item in profile.source_groups}
    entity_labels, detectors = _typed_modules(pack)
    sources = tuple(
        IntelligenceBuildReviewSourceV1Alpha1(
            selection=item.reference(),
            label=groups[item.source_group_id].label,
            evidence_role=groups[item.source_group_id].evidence_role,
            source_uri=item.source_uri,
            source_definition_ref=item.source_definition_ref,
            entity_type_id=item.entity_type_id,
            entity_ref=item.entity_ref,
            observed_at=item.observed_at,
        )
        for item in selections
    )
    concept_material: dict[
        tuple[str, str],
        list[RecordedSourceSelectionReferenceV1Alpha1],
    ] = {}
    for item in selections:
        concept_material.setdefault((item.entity_type_id, item.entity_ref), []).append(item.reference())
    concepts = tuple(
        IntelligenceBuildReviewConceptV1Alpha1(
            entity_type_id=entity_type_id,
            entity_ref=entity_ref,
            display_name=entity_labels.get(entity_type_id, entity_type_id),
            source_selections=tuple(references),
        )
        for (entity_type_id, entity_ref), references in concept_material.items()
    )
    concepts_by_type: dict[str, tuple[str, ...]] = {}
    for concept in concepts:
        concepts_by_type[concept.entity_type_id] = tuple(
            item.entity_ref for item in concepts if item.entity_type_id == concept.entity_type_id
        )
    watches: list[IntelligenceBuildReviewWatchV1Alpha1] = []
    for detector_id in outcome.recommended_watch_ids:
        rule = detectors.get(detector_id)
        if not isinstance(rule, (NumericDeltaRuleV1, CategoricalTransitionRuleV1)):
            raise ValueError("recommended watch is not declared by the exact installed Pack")
        entity_refs = concepts_by_type.get(rule.entity_type_id, ())
        if not entity_refs:
            raise ValueError("recommended watch has no exact reviewed entity reference")
        detector_family, change_rule = _change_rule(rule)
        watches.append(
            IntelligenceBuildReviewWatchV1Alpha1(
                detector_id=rule.detector_id,
                detector_family=detector_family,
                entity_type_id=rule.entity_type_id,
                entity_refs=entity_refs,
                attribute_id=rule.attribute_id,
                change_rule=change_rule,
                shift_type=rule.shift_type,
                signal_type=rule.signal_type,
                cadence_id=cadence.cadence_id,
                cadence_label=cadence.label,
            )
        )
    return IntelligenceBuildReviewProjectionV1Alpha1(
        request_id=request_id,
        request_digest=request_digest,
        profile_id=profile.profile_id,
        profile_digest=profile.profile_digest,
        pack_reference=pack_reference,
        subject=subject,
        outcome_id=outcome.outcome_id,
        outcome_label=outcome.label,
        sources=sources,
        concepts=concepts,
        watches=tuple(watches),
        cadence_id=cadence.cadence_id,
        cadence_label=cadence.label,
        cadence_description=cadence.description,
        effects=_effect_reviews(
            source_count=len(sources),
            concept_count=len(concepts),
            watch_count=len(watches),
            cadence_label=cadence.label,
            outcome_description=outcome.description,
        ),
    )


__all__ = [
    "INTELLIGENCE_BUILD_REVIEW_PROJECTION_VERSION",
    "IntelligenceBuildReviewConceptV1Alpha1",
    "IntelligenceBuildReviewEffectV1Alpha1",
    "IntelligenceBuildReviewProjectionV1Alpha1",
    "IntelligenceBuildReviewSourceV1Alpha1",
    "IntelligenceBuildReviewWatchV1Alpha1",
    "project_intelligence_build_review",
]

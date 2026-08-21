"""Prepared-only runtime binding for exact compiled Domain Pack policy.

This module deliberately does not activate, persist, or authorize a pack.  It
binds a locally prepared active revision to the exact Pack IR it names so pure
Intelligence interpreters cannot accept detached or cross-pack policy objects.
Durable and live execution must first resolve the revision through Core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ace.core.contracts import canonical_hash
from ace.intelligence.contracts.activation import (
    ActivationState,
    CompiledPackRefV1,
    DomainActivationRevisionV1,
)
from ace.intelligence.contracts.detection import (
    DETECTION_MODULE_V1ALPHA2_VERSION,
    DETECTION_MODULE_VERSION,
    CategoricalTransitionRuleV1,
    DetectionModuleV1,
    DetectionModuleV1Alpha2,
    NumericDeltaRuleV1,
)
from ace.intelligence.contracts.epistemic import (
    EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION,
    EPISTEMIC_STATUS_MODULE_VERSION,
    EpistemicStatusModuleV1,
    EpistemicStatusModuleV1Alpha2,
    EpistemicStatusSetV1,
    EpistemicStatusSetV1Alpha2,
)
from ace.intelligence.contracts.feedback import (
    DECISION_OUTCOMES_MODULE_VERSION,
    DecisionOutcomesModuleV1,
    FeedbackPolicyV1,
)
from ace.intelligence.contracts.orientation import (
    ORIENTATION_MODULE_VERSION,
    InitialOrientationPolicyV1,
    OrientationModuleV1,
)
from ace.intelligence.contracts.pack import (
    ONTOLOGY_MODULE_VERSION,
    CompiledDomainPackV1,
    EntityTypeDeclarationV1,
    OntologyModuleV1,
)
from ace.intelligence.contracts.personas import (
    PERSONAS_MODULE_VERSION,
    PersonaArchetypeV1,
    PersonasModuleV1,
)
from ace.intelligence.contracts.resources import ActivationRevisionReferenceV1Alpha1
from ace.intelligence.contracts.source_mapping import (
    SOURCE_MAPPING_MODULE_VERSION,
    SourceMappingModuleV1,
    SourceMappingRuleV1,
)
from ace.intelligence.contracts.synthesis import (
    SYNTHESIS_MODULE_V1ALPHA2_VERSION,
    SYNTHESIS_MODULE_VERSION,
    BriefTemplateV1,
    BriefTemplateV1Alpha2,
    SynthesisModuleV1,
    SynthesisModuleV1Alpha2,
)


class PreparedActivationBindingError(ValueError):
    """A prepared revision and compiled Pack IR do not form one exact binding."""


class CompiledPackArtifactResolver(Protocol):
    """Load one exact immutable Pack IR artifact by content coordinates."""

    async def load_exact(
        self,
        *,
        reference: CompiledPackRefV1,
    ) -> CompiledDomainPackV1 | None: ...


@dataclass(frozen=True, slots=True)
class PreparedActivationBinding:
    """Validated prepared-only Pack IR plus its exact activation revision."""

    pack: CompiledDomainPackV1
    revision: DomainActivationRevisionV1
    reference: ActivationRevisionReferenceV1Alpha1


@dataclass(frozen=True, slots=True)
class ResolvedSourceMappingPolicy:
    """One exact source-mapping rule and its activation-bound compiled module."""

    module_id: str
    module_digest: str
    rule: SourceMappingRuleV1


@dataclass(frozen=True, slots=True)
class ResolvedBriefSynthesisPolicy:
    """One exact module-bound template and its routed persona declarations."""

    module_id: str
    module_digest: str
    template: BriefTemplateV1 | BriefTemplateV1Alpha2
    template_digest: str
    personas: tuple[PersonaArchetypeV1, ...]


@dataclass(frozen=True, slots=True)
class ResolvedInitialOrientationPolicy:
    """One exact orientation policy and its fully resolved synthesis selection."""

    module_id: str
    module_digest: str
    policy: InitialOrientationPolicyV1
    policy_digest: str
    synthesis: ResolvedBriefSynthesisPolicy


@dataclass(frozen=True, slots=True)
class ResolvedEpistemicStatusPolicy:
    """One exact module-bound status vocabulary governing one Brief template."""

    module_id: str
    module_digest: str
    module_contract: str
    status_set: EpistemicStatusSetV1 | EpistemicStatusSetV1Alpha2
    status_set_digest: str
    template_id: str

    @property
    def requires_derivation_families(self) -> bool:
        """Whether any declared status demands more than one derived family."""

        return any(getattr(item, "min_distinct_derivation_families", 1) > 1 for item in self.status_set.statuses)


@dataclass(frozen=True, slots=True)
class ResolvedFeedbackPolicy:
    """One exact feedback policy and its activation-bound compiled module."""

    module_id: str
    module_digest: str
    policy: FeedbackPolicyV1


def _revalidate_pack(pack: CompiledDomainPackV1) -> CompiledDomainPackV1:
    try:
        return CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PreparedActivationBindingError("compiled pack failed exact revalidation") from exc


def _revalidate_revision(revision: DomainActivationRevisionV1) -> DomainActivationRevisionV1:
    try:
        return DomainActivationRevisionV1.model_validate(revision.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PreparedActivationBindingError("activation revision failed exact revalidation") from exc


def _pack_reference(pack: CompiledDomainPackV1) -> CompiledPackRefV1:
    if pack.compiled_pack_id is None or pack.pack_digest is None:
        raise PreparedActivationBindingError("compiled pack is missing its derived identity")
    return CompiledPackRefV1(
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
    )


def _revision_reference(revision: DomainActivationRevisionV1) -> ActivationRevisionReferenceV1Alpha1:
    if revision.activation_id is None or revision.revision_id is None or revision.revision_hash is None:
        raise PreparedActivationBindingError("activation revision is missing its derived identity")
    return ActivationRevisionReferenceV1Alpha1(
        product_id=revision.spec.product_id,
        activation_key=revision.spec.activation_key,
        activation_id=revision.activation_id,
        revision=revision.revision,
        revision_id=revision.revision_id,
        revision_digest=f"sha256:{revision.revision_hash}",
    )


def bind_prepared_activation(
    *,
    pack: CompiledDomainPackV1,
    revision: DomainActivationRevisionV1,
) -> PreparedActivationBinding:
    """Bind a locally prepared active revision to its exact compiled Pack IR.

    ``ActivationState.ACTIVE`` here is prepared desired state.  This function
    does not prove that Core committed the revision and therefore never grants
    live execution authority.
    """

    validated_pack = _revalidate_pack(pack)
    validated_revision = _revalidate_revision(revision)
    if validated_revision.state is not ActivationState.ACTIVE:
        raise PreparedActivationBindingError("prepared runtime binding requires an active revision")
    expected_pack = _pack_reference(validated_pack)
    if validated_revision.spec.pack != expected_pack:
        raise PreparedActivationBindingError("activation revision does not name the exact supplied compiled pack")
    overlay = validated_revision.spec.overlay
    if (
        overlay.pack_id != expected_pack.pack_id
        or overlay.pack_version != expected_pack.pack_version
        or overlay.pack_digest != expected_pack.pack_digest
    ):
        raise PreparedActivationBindingError("activation overlay does not target the exact supplied compiled pack")
    return PreparedActivationBinding(
        pack=validated_pack,
        revision=validated_revision,
        reference=_revision_reference(validated_revision),
    )


def validate_prepared_activation_binding(
    binding: PreparedActivationBinding,
) -> PreparedActivationBinding:
    """Rebuild a binding so copied or stale model identities fail closed."""

    if not isinstance(binding, PreparedActivationBinding):
        raise PreparedActivationBindingError("a prepared activation binding is required")
    validated = bind_prepared_activation(pack=binding.pack, revision=binding.revision)
    if binding.reference != validated.reference:
        raise PreparedActivationBindingError("binding reference does not match its activation revision")
    return validated


_DETECTION_MODELS = {
    DETECTION_MODULE_VERSION: DetectionModuleV1,
    DETECTION_MODULE_V1ALPHA2_VERSION: DetectionModuleV1Alpha2,
}


def _detection_modules(
    validated: PreparedActivationBinding,
) -> tuple[DetectionModuleV1 | DetectionModuleV1Alpha2, ...]:
    return tuple(
        _DETECTION_MODELS[module_ir.contract].model_validate_json(module_ir.canonical_payload)
        for module_ir in validated.pack.modules
        if module_ir.contract in _DETECTION_MODELS
    )


def resolve_numeric_delta_rule(
    binding: PreparedActivationBinding,
    *,
    detector_id: str,
) -> NumericDeltaRuleV1:
    """Resolve one detector only from the exact bound Pack IR."""

    validated = validate_prepared_activation_binding(binding)
    matches: list[NumericDeltaRuleV1] = []
    for module in _detection_modules(validated):
        matches.extend(rule for rule in module.numeric_delta_rules if rule.detector_id == detector_id)
    if len(matches) != 1:
        raise PreparedActivationBindingError(
            f"detector {detector_id!r} must resolve exactly once in the bound compiled pack"
        )
    return matches[0]


def resolve_categorical_transition_rule(
    binding: PreparedActivationBinding,
    *,
    detector_id: str,
) -> CategoricalTransitionRuleV1:
    """Resolve one categorical detector only from the exact bound Pack IR."""

    validated = validate_prepared_activation_binding(binding)
    matches: list[CategoricalTransitionRuleV1] = []
    for module in _detection_modules(validated):
        matches.extend(
            rule for rule in getattr(module, "categorical_transition_rules", ()) if rule.detector_id == detector_id
        )
    if len(matches) != 1:
        raise PreparedActivationBindingError(
            f"detector {detector_id!r} must resolve exactly once in the bound compiled pack"
        )
    return matches[0]


def resolve_detector_rule(
    binding: PreparedActivationBinding,
    *,
    detector_id: str,
) -> NumericDeltaRuleV1 | CategoricalTransitionRuleV1:
    """Resolve one detector of any declared family only from the exact bound Pack IR."""

    validated = validate_prepared_activation_binding(binding)
    matches: list[NumericDeltaRuleV1 | CategoricalTransitionRuleV1] = []
    for module in _detection_modules(validated):
        matches.extend(rule for rule in module.numeric_delta_rules if rule.detector_id == detector_id)
        matches.extend(
            rule for rule in getattr(module, "categorical_transition_rules", ()) if rule.detector_id == detector_id
        )
    if len(matches) != 1:
        raise PreparedActivationBindingError(
            f"detector {detector_id!r} must resolve exactly once in the bound compiled pack"
        )
    return matches[0]


def resolve_entity_type_declaration(
    binding: PreparedActivationBinding,
    *,
    entity_type_id: str,
) -> EntityTypeDeclarationV1:
    """Resolve one entity schema only from the exact bound Pack IR."""

    validated = validate_prepared_activation_binding(binding)
    matches: list[EntityTypeDeclarationV1] = []
    for module_ir in validated.pack.modules:
        if module_ir.contract != ONTOLOGY_MODULE_VERSION:
            continue
        module = OntologyModuleV1.model_validate_json(module_ir.canonical_payload)
        matches.extend(entity for entity in module.entity_types if entity.entity_type_id == entity_type_id)
    if len(matches) != 1:
        raise PreparedActivationBindingError(
            f"entity type {entity_type_id!r} must resolve exactly once in the bound compiled pack"
        )
    return matches[0]


def resolve_persona_modules(
    binding: PreparedActivationBinding,
) -> tuple[PersonasModuleV1, ...]:
    """Resolve all persona policy only from the exact bound Pack IR."""

    validated = validate_prepared_activation_binding(binding)
    return tuple(
        PersonasModuleV1.model_validate_json(module_ir.canonical_payload)
        for module_ir in validated.pack.modules
        if module_ir.contract == PERSONAS_MODULE_VERSION
    )


def resolve_source_mapping_rule(
    binding: PreparedActivationBinding,
    *,
    mapping_id: str,
) -> SourceMappingRuleV1:
    """Resolve one mapping only from the exact activation-bound compiled Pack IR."""

    return resolve_source_mapping_policy(binding, mapping_id=mapping_id).rule


def resolve_source_mapping_policy(
    binding: PreparedActivationBinding,
    *,
    mapping_id: str,
) -> ResolvedSourceMappingPolicy:
    """Resolve one rule together with the exact compiled module that owns it."""

    validated = validate_prepared_activation_binding(binding)
    matches: list[ResolvedSourceMappingPolicy] = []
    for module_ir in validated.pack.modules:
        if module_ir.contract != SOURCE_MAPPING_MODULE_VERSION:
            continue
        module = SourceMappingModuleV1.model_validate_json(module_ir.canonical_payload)
        matches.extend(
            ResolvedSourceMappingPolicy(
                module_id=module_ir.module_id,
                module_digest=module_ir.module_digest,
                rule=mapping,
            )
            for mapping in module.mappings
            if mapping.mapping_id == mapping_id
        )
    if len(matches) != 1:
        raise PreparedActivationBindingError(
            f"source mapping {mapping_id!r} must resolve exactly once in the bound compiled pack"
        )
    return matches[0]


def resolve_feedback_policy(
    binding: PreparedActivationBinding,
    *,
    policy_id: str,
) -> ResolvedFeedbackPolicy:
    """Resolve one inert feedback policy only from exact bound Pack IR."""

    validated = validate_prepared_activation_binding(binding)
    matches: list[ResolvedFeedbackPolicy] = []
    for module_ir in validated.pack.modules:
        if module_ir.contract != DECISION_OUTCOMES_MODULE_VERSION:
            continue
        module = DecisionOutcomesModuleV1.model_validate_json(module_ir.canonical_payload)
        matches.extend(
            ResolvedFeedbackPolicy(
                module_id=module_ir.module_id,
                module_digest=module_ir.module_digest,
                policy=policy,
            )
            for policy in module.feedback_policies
            if policy.policy_id == policy_id
        )
    if len(matches) != 1:
        raise PreparedActivationBindingError(
            f"feedback policy {policy_id!r} must resolve exactly once in the bound compiled pack"
        )
    return matches[0]


def resolve_epistemic_status_policy(
    binding: PreparedActivationBinding,
    *,
    template_id: str,
) -> ResolvedEpistemicStatusPolicy:
    """Resolve the one status vocabulary governing a template, or fail closed.

    A Domain Pack that declares no epistemic-status module for a template simply
    does not get status-aware synthesis; it does not silently get an empty or
    permissive vocabulary. Market therefore keeps working untouched while World
    opts in declaratively.
    """

    validated = validate_prepared_activation_binding(binding)
    models = {
        EPISTEMIC_STATUS_MODULE_VERSION: EpistemicStatusModuleV1,
        EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION: EpistemicStatusModuleV1Alpha2,
    }
    matches: list[ResolvedEpistemicStatusPolicy] = []
    for module_ir in validated.pack.modules:
        model = models.get(module_ir.contract)
        if model is None:
            continue
        module = model.model_validate_json(module_ir.canonical_payload)
        matches.extend(
            ResolvedEpistemicStatusPolicy(
                module_id=module_ir.module_id,
                module_digest=module_ir.module_digest,
                module_contract=module_ir.contract,
                status_set=status_set,
                status_set_digest=f"sha256:{canonical_hash(status_set.model_dump(mode='json'))}",
                template_id=template_id,
            )
            for status_set in module.status_sets
            if template_id in status_set.brief_template_ids
        )
    if len(matches) != 1:
        raise PreparedActivationBindingError(
            f"Brief template {template_id!r} must be governed by exactly one declared "
            "epistemic status set in the bound compiled pack"
        )
    return matches[0]


def resolve_brief_synthesis_policy(
    binding: PreparedActivationBinding,
    *,
    template_id: str,
    persona_ids: tuple[str, ...],
) -> ResolvedBriefSynthesisPolicy:
    """Resolve exactly one template and every routed persona from bound Pack IR."""

    validated = validate_prepared_activation_binding(binding)
    template_matches: list[tuple[str, str, BriefTemplateV1 | BriefTemplateV1Alpha2]] = []
    synthesis_models = {
        SYNTHESIS_MODULE_VERSION: SynthesisModuleV1,
        SYNTHESIS_MODULE_V1ALPHA2_VERSION: SynthesisModuleV1Alpha2,
    }
    for module_ir in validated.pack.modules:
        model = synthesis_models.get(module_ir.contract)
        if model is None:
            continue
        module = model.model_validate_json(module_ir.canonical_payload)
        template_matches.extend(
            (module_ir.module_id, module_ir.module_digest, template)
            for template in module.brief_templates
            if template.template_id == template_id
        )
    if len(template_matches) != 1:
        raise PreparedActivationBindingError(
            f"Brief template {template_id!r} must resolve exactly once in the bound compiled pack"
        )

    if not persona_ids or len(persona_ids) != len(set(persona_ids)):
        raise PreparedActivationBindingError("Brief synthesis requires unique routed persona identities")
    persona_matches: dict[str, list[PersonaArchetypeV1]] = {item: [] for item in persona_ids}
    for module in resolve_persona_modules(validated):
        for persona in module.personas:
            if persona.persona_id in persona_matches:
                persona_matches[persona.persona_id].append(persona)
    unresolved = sorted(persona_id for persona_id, matches in persona_matches.items() if len(matches) != 1)
    if unresolved:
        raise PreparedActivationBindingError(
            f"routed personas must each resolve exactly once in the bound compiled pack: {unresolved}"
        )
    module_id, module_digest, template = template_matches[0]
    return ResolvedBriefSynthesisPolicy(
        module_id=module_id,
        module_digest=module_digest,
        template=template,
        template_digest=f"sha256:{canonical_hash(template.model_dump(mode='json'))}",
        personas=tuple(persona_matches[item][0] for item in sorted(persona_matches)),
    )


def _orientation_modules(
    validated: PreparedActivationBinding,
) -> tuple[tuple[str, str, OrientationModuleV1], ...]:
    return tuple(
        (
            module_ir.module_id,
            module_ir.module_digest,
            OrientationModuleV1.model_validate_json(module_ir.canonical_payload),
        )
        for module_ir in validated.pack.modules
        if module_ir.contract == ORIENTATION_MODULE_VERSION
    )


def resolve_initial_orientation_policy(
    binding: PreparedActivationBinding,
    *,
    policy_id: str,
) -> ResolvedInitialOrientationPolicy:
    """Resolve one orientation policy, its template, and its personas from bound Pack IR.

    Personas may live in personas modules or be declared inline by orientation
    modules; each routed persona must resolve exactly once across both, so an
    orientation Pack never needs Signal-routing policy to name its readers.
    """

    validated = validate_prepared_activation_binding(binding)
    policy_matches: list[tuple[str, str, InitialOrientationPolicyV1]] = []
    for module_id, module_digest, module in _orientation_modules(validated):
        policy_matches.extend(
            (module_id, module_digest, policy)
            for policy in module.initial_orientation_policies
            if policy.policy_id == policy_id
        )
    if len(policy_matches) != 1:
        raise PreparedActivationBindingError(
            f"initial orientation policy {policy_id!r} must resolve exactly once in the bound compiled pack"
        )
    module_id, module_digest, policy = policy_matches[0]

    template_matches: list[tuple[str, str, BriefTemplateV1 | BriefTemplateV1Alpha2]] = []
    synthesis_models = {
        SYNTHESIS_MODULE_VERSION: SynthesisModuleV1,
        SYNTHESIS_MODULE_V1ALPHA2_VERSION: SynthesisModuleV1Alpha2,
    }
    for module_ir in validated.pack.modules:
        model = synthesis_models.get(module_ir.contract)
        if model is None:
            continue
        module = model.model_validate_json(module_ir.canonical_payload)
        template_matches.extend(
            (module_ir.module_id, module_ir.module_digest, template)
            for template in module.brief_templates
            if template.template_id == policy.brief_template_id
        )
    if len(template_matches) != 1:
        raise PreparedActivationBindingError(
            f"Brief template {policy.brief_template_id!r} must resolve exactly once in the bound compiled pack"
        )

    persona_matches: dict[str, list[PersonaArchetypeV1]] = {item: [] for item in policy.persona_ids}
    for module in resolve_persona_modules(validated):
        for persona in module.personas:
            if persona.persona_id in persona_matches:
                persona_matches[persona.persona_id].append(persona)
    for _, _, orientation_module in _orientation_modules(validated):
        for persona in orientation_module.personas:
            if persona.persona_id in persona_matches:
                persona_matches[persona.persona_id].append(persona)
    unresolved = sorted(persona_id for persona_id, matches in persona_matches.items() if len(matches) != 1)
    if unresolved:
        raise PreparedActivationBindingError(
            f"orientation personas must each resolve exactly once in the bound compiled pack: {unresolved}"
        )

    template_module_id, template_module_digest, template = template_matches[0]
    return ResolvedInitialOrientationPolicy(
        module_id=module_id,
        module_digest=module_digest,
        policy=policy,
        policy_digest=f"sha256:{canonical_hash(policy.model_dump(mode='json'))}",
        synthesis=ResolvedBriefSynthesisPolicy(
            module_id=template_module_id,
            module_digest=template_module_digest,
            template=template,
            template_digest=f"sha256:{canonical_hash(template.model_dump(mode='json'))}",
            personas=tuple(persona_matches[item][0] for item in sorted(persona_matches)),
        ),
    )

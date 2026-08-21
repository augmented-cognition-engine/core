"""Production selected-provider adapters for the Intelligence Builder strategy ports.

ACE 1.2 PI13 WS3: adapt the already-selected local structured provider to the
existing ``ConceptModelStrategy``, ``IntelligenceModelStrategy``, and
``BriefingStrategy`` ports (``ace.application.ontology_agent``,
``ace.application.intelligence_agent``, ``ace.application.briefing_agent``).
Each adapter makes exactly one structured provider call per stage and then
constructs the exact existing proposal/preview contract with every protected,
server-owned binding supplied by the host -- never by the provider. Citation
selections are normalized: the provider names an exact source sample/field or
observation/field or approved statement/citation, and the host reconstructs
the exact citation record from the trusted material it was given. No action,
connector, authority, scheduling, or delivery effect is performed here.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from pydantic import ValidationError

from ace.application.briefing_agent_contracts import (
    BriefingDerivationV1,
    BriefingItemV1,
    FirstBriefingPreviewV1,
)
from ace.application.intelligence_agent_contracts import (
    AudienceProposalV1,
    AuthorizedObservationSetV1,
    BaselineProposalV1,
    DetectorProposalV1,
    EpistemicStatementV1,
    IntelligenceCitationV1,
    IntelligenceConflictV1,
    IntelligenceModelDispositionV1,
    IntelligenceModelProposalV1,
    MaterialityRuleV1,
    ProposedCadence,
    RoutingCadenceProposalV1,
    SuppressionGroupingRuleV1,
    WatchTargetKind,
    WatchTargetV1,
)
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    SourceProfileProposalV1,
)
from ace.application.ontology_agent_contracts import (
    ConceptCitationV1,
    ConceptConflictV1,
    ConceptEntityTypeV1,
    ConceptModelDispositionV1,
    ConceptModelProposalV1,
    ConceptRelationshipTypeV1,
    ConceptTerminologyV1,
    OrganizationTerminologyV1,
)
from ace.core.contracts import canonical_json
from core.engine.core.llm import get_llm
from core.engine.core.provider_runtime import complete_structured_provider_call

_NO_ACTION_RULES = (
    "Author only the exact listed fields; the host rejects any other field.",
    "Never author session, correlation, goal, product, source-profile, concept-model, "
    "intelligence-model, disposition, or observation-set identifiers, digests, revision, "
    "lineage, approval references, or timestamps; the host derives every one of them.",
    "No action, connector, authority, scheduling, or delivery effect is permitted.",
)

# Explicit, bounded safe ceiling on the canonical prompt: the host fails closed before the
# provider call rather than ever sending an unbounded prompt to a selected provider.
_MAX_PROMPT_BYTES = 200_000


def _inline_model_schema(model_cls: type) -> dict[str, Any]:
    """Return ``model_cls``'s exact JSON Schema with every ``$ref`` definition inlined."""

    schema = model_cls.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                resolved = dict(resolve(defs[name]))
                resolved.update({key: resolve(value) for key, value in node.items() if key != "$ref"})
                return resolved
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def _array_schema(
    item_schema: dict[str, Any], *, min_items: int | None = None, max_items: int | None = None
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": item_schema}
    if min_items is not None:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


_STRING_SCHEMA: dict[str, Any] = {"type": "string"}
_CONFIDENCE_SCHEMA: dict[str, Any] = {"type": "number", "minimum": 0.0, "maximum": 1.0}


def _string_array_schema(*, min_items: int | None = None, max_items: int | None = None) -> dict[str, Any]:
    return _array_schema(_STRING_SCHEMA, min_items=min_items, max_items=max_items)


def _citation_selection_schema(*, id_field: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["citation_id", id_field, "field_path"],
        "properties": {
            "citation_id": {"type": "string"},
            id_field: {"type": "string"},
            "field_path": {"type": "string"},
        },
    }


class SelectedBuilderStrategyError(RuntimeError):
    """A selected-provider Builder strategy adapter failed before a safe result."""


class SelectedBuilderStrategyUnavailable(SelectedBuilderStrategyError):
    """No eligible selected provider could complete the exact structured call."""


class SelectedBuilderStrategyConflict(SelectedBuilderStrategyError):
    """Provider output violated the exact bounded schema or attribution rules."""


def _resolve_provider(
    provider: object | None,
    provider_factory: Callable[[], object],
) -> object:
    if provider is not None:
        candidate = provider
    else:
        try:
            candidate = provider_factory()
        except Exception as exc:
            raise SelectedBuilderStrategyUnavailable("no eligible selected provider is available") from exc
    if candidate is None or not callable(getattr(candidate, "complete_json", None)):
        raise SelectedBuilderStrategyUnavailable("the selected provider does not support structured JSON completion")
    return candidate


async def _call_provider(
    provider: object,
    *,
    stage: str,
    trusted_context: dict[str, Any],
    output_contract: dict[str, Any],
    model: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    prompt = canonical_json(
        {
            "attribution_rules": _NO_ACTION_RULES,
            "output_contract": output_contract,
            "stage": stage,
            "trusted_context": trusted_context,
        }
    )
    if len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
        raise SelectedBuilderStrategyUnavailable(f"canonical prompt for {stage} exceeded the bounded safe size")
    try:
        call = await complete_structured_provider_call(
            provider,
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        raise SelectedBuilderStrategyUnavailable(f"selected structured provider call failed for {stage}") from exc
    try:
        material = json.loads(call.structured_json)
    except (TypeError, ValueError) as exc:
        raise SelectedBuilderStrategyConflict(f"selected provider output for {stage} was not valid JSON") from exc
    if not isinstance(material, dict):
        raise SelectedBuilderStrategyConflict(f"selected provider output for {stage} must be one JSON object")
    return material


def _reject_unknown_keys(material: dict[str, Any], allowed: set[str], *, stage: str) -> None:
    extra = set(material) - allowed
    if extra:
        raise SelectedBuilderStrategyConflict(
            f"selected provider output for {stage} named unsupported fields: {sorted(extra)}"
        )


def _build_models(
    raw: Any,
    model_cls: type,
    *,
    label: str,
    required: bool = True,
) -> tuple[Any, ...]:
    if raw is None:
        if required:
            raise SelectedBuilderStrategyConflict(f"provider output is missing required field '{label}'")
        return ()
    if not isinstance(raw, list):
        raise SelectedBuilderStrategyConflict(f"'{label}' must be a JSON array")
    try:
        return tuple(model_cls.model_validate(item, strict=False) for item in raw)
    except (TypeError, ValidationError, AttributeError) as exc:
        raise SelectedBuilderStrategyConflict(f"'{label}' failed exact structured validation") from exc


def _string_tuple(raw: Any, *, label: str, required: bool = True) -> tuple[str, ...]:
    if raw is None:
        if required:
            raise SelectedBuilderStrategyConflict(f"provider output is missing required field '{label}'")
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise SelectedBuilderStrategyConflict(f"'{label}' must be a JSON array of strings")
    return tuple(raw)


def _confidence(raw: Any) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not (0.0 <= float(raw) <= 1.0):
        raise SelectedBuilderStrategyConflict("'confidence' must be a bounded number between 0.0 and 1.0")
    return float(raw)


def _citation_selections(raw: Any, *, required_keys: set[str]) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        raise SelectedBuilderStrategyConflict("provider must select at least one citation")
    selections: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != required_keys:
            raise SelectedBuilderStrategyConflict(f"citation selection must name exactly {sorted(required_keys)}")
        if any(not isinstance(value, str) for value in entry.values()):
            raise SelectedBuilderStrategyConflict("citation selection fields must be strings")
        citation_id = entry["citation_id"]
        if citation_id in seen:
            raise SelectedBuilderStrategyConflict("duplicate citation selection")
        seen.add(citation_id)
        selections.append(dict(entry))
    return selections


def _reconstruct_concept_citations(
    raw: Any,
    *,
    source_profile: SourceProfileProposalV1,
) -> tuple[ConceptCitationV1, ...]:
    selections = _citation_selections(raw, required_keys={"citation_id", "source_sample_id", "field_path"})
    samples = {str(sample.sample_id): sample for sample in source_profile.samples}
    citations: list[ConceptCitationV1] = []
    for entry in selections:
        sample = samples.get(entry["source_sample_id"])
        if sample is None:
            raise SelectedBuilderStrategyConflict("citation selection names an unknown source sample")
        fields = {item.field_path for item in sample.fields}
        if entry["field_path"] not in fields:
            raise SelectedBuilderStrategyConflict("citation selection names an unknown source-sample field")
        try:
            citations.append(
                ConceptCitationV1(
                    citation_id=entry["citation_id"],
                    source_profile_proposal_id=str(source_profile.proposal_id),
                    source_profile_proposal_digest=str(source_profile.proposal_digest),
                    source_sample_id=str(sample.sample_id),
                    source_sample_digest=str(sample.sample_digest),
                    source_ref=sample.source_ref,
                    field_path=entry["field_path"],
                    evidence_digest=sample.evidence_digest,
                )
            )
        except ValidationError as exc:
            raise SelectedBuilderStrategyConflict("citation selection failed exact citation validation") from exc
    return tuple(citations)


def _reconstruct_intelligence_citations(
    raw: Any,
    *,
    observations: AuthorizedObservationSetV1,
) -> tuple[IntelligenceCitationV1, ...]:
    selections = _citation_selections(raw, required_keys={"citation_id", "observation_id", "field_path"})
    observed = {str(item.observation_id): item for item in observations.observations}
    citations: list[IntelligenceCitationV1] = []
    for entry in selections:
        observation = observed.get(entry["observation_id"])
        if observation is None:
            raise SelectedBuilderStrategyConflict("citation selection names an unknown admitted observation")
        attributes = observation.attributes.parsed_value()
        if not isinstance(attributes, dict) or entry["field_path"].removeprefix("/") not in attributes:
            raise SelectedBuilderStrategyConflict("citation selection names an unknown observation field")
        try:
            citations.append(
                IntelligenceCitationV1(
                    citation_id=entry["citation_id"],
                    observation_id=str(observation.observation_id),
                    observation_digest=str(observation.observation_digest),
                    source_ref=observation.source_ref,
                    evidence_digest=observation.evidence_digest,
                    field_path=entry["field_path"],
                )
            )
        except ValidationError as exc:
            raise SelectedBuilderStrategyConflict("citation selection failed exact citation validation") from exc
    return tuple(citations)


def _validate_watch_targets(
    watch_targets: tuple[WatchTargetV1, ...],
    *,
    concept_model: ConceptModelProposalV1,
) -> None:
    entity_types = {item.type_id: item for item in concept_model.entity_types}
    relationship_ids = {item.type_id for item in concept_model.relationship_types}
    for target in watch_targets:
        entity = entity_types.get(target.entity_type_id)
        if entity is None:
            raise SelectedBuilderStrategyConflict("watch target names an undeclared entity type")
        if target.target_kind is WatchTargetKind.ATTRIBUTE:
            if target.member_id not in {item.attribute_id for item in entity.attributes}:
                raise SelectedBuilderStrategyConflict("watch target names an undeclared entity attribute")
        elif target.member_id not in relationship_ids:
            raise SelectedBuilderStrategyConflict("watch target names an undeclared relationship type")


class SelectedConceptModelStrategy:
    """Adapt the selected local provider to the ``ConceptModelStrategy`` port."""

    _ALLOWED_FIELDS = {
        "citations",
        "entity_types",
        "relationship_types",
        "terminology",
        "exclusions",
        "conflicts",
        "unknowns",
        "confidence",
    }

    def __init__(
        self,
        *,
        provider: object | None = None,
        provider_factory: Callable[[], object] = get_llm,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.provider_factory = provider_factory
        self.model = model
        self.max_tokens = max_tokens

    async def propose(
        self,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        source_profile: SourceProfileProposalV1,
        user_intent: str,
        organization_terminology: tuple[OrganizationTerminologyV1, ...],
        created_at: datetime,
    ) -> ConceptModelProposalV1:
        provider = _resolve_provider(self.provider, self.provider_factory)
        trusted_context = {
            "goal_ref": session.goal_ref,
            "organization_terminology": [item.model_dump(mode="json") for item in organization_terminology],
            "source_profile": source_profile.model_dump(mode="json"),
            "user_intent": user_intent,
        }
        output_contract = {
            "type": "object",
            "additionalProperties": False,
            "required": ["citations", "entity_types", "exclusions", "confidence"],
            "properties": {
                "citations": _array_schema(
                    _citation_selection_schema(id_field="source_sample_id"), min_items=1, max_items=256
                ),
                "confidence": _CONFIDENCE_SCHEMA,
                "conflicts": _array_schema(_inline_model_schema(ConceptConflictV1), max_items=128),
                "entity_types": _array_schema(_inline_model_schema(ConceptEntityTypeV1), min_items=1, max_items=128),
                "exclusions": _string_array_schema(min_items=1, max_items=128),
                "relationship_types": _array_schema(_inline_model_schema(ConceptRelationshipTypeV1), max_items=128),
                "terminology": _array_schema(_inline_model_schema(ConceptTerminologyV1), max_items=128),
                "unknowns": _string_array_schema(max_items=128),
            },
        }
        material = await _call_provider(
            provider,
            stage="concept_model_proposal",
            trusted_context=trusted_context,
            output_contract=output_contract,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        _reject_unknown_keys(material, self._ALLOWED_FIELDS, stage="concept_model_proposal")
        citations = _reconstruct_concept_citations(material.get("citations"), source_profile=source_profile)
        try:
            return ConceptModelProposalV1(
                session_id=session.session_id,
                correlation_id=session.correlation_id,
                goal_ref=session.goal_ref,
                user_intent=user_intent,
                source_profile_proposal_id=str(source_profile.proposal_id),
                source_profile_proposal_digest=str(source_profile.proposal_digest),
                revision=1,
                citations=citations,
                entity_types=_build_models(material.get("entity_types"), ConceptEntityTypeV1, label="entity_types"),
                relationship_types=_build_models(
                    material.get("relationship_types"),
                    ConceptRelationshipTypeV1,
                    label="relationship_types",
                    required=False,
                ),
                terminology=_build_models(
                    material.get("terminology"), ConceptTerminologyV1, label="terminology", required=False
                ),
                exclusions=_string_tuple(material.get("exclusions"), label="exclusions"),
                conflicts=_build_models(
                    material.get("conflicts"), ConceptConflictV1, label="conflicts", required=False
                ),
                unknowns=_string_tuple(material.get("unknowns"), label="unknowns", required=False),
                confidence=_confidence(material.get("confidence")),
                created_at=created_at,
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise SelectedBuilderStrategyConflict(
                "provider output failed exact concept-model proposal validation"
            ) from exc


class SelectedIntelligenceModelStrategy:
    """Adapt the selected local provider to the ``IntelligenceModelStrategy`` port."""

    _ALLOWED_FIELDS = {
        "citations",
        "watch_targets",
        "baselines",
        "detectors",
        "materiality_rules",
        "audiences",
        "routes",
        "suppression_grouping_rules",
        "epistemic_statements",
        "conflicts",
        "unknowns",
        "exclusions",
        "confidence",
    }

    def __init__(
        self,
        *,
        provider: object | None = None,
        provider_factory: Callable[[], object] = get_llm,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.provider_factory = provider_factory
        self.model = model
        self.max_tokens = max_tokens

    async def propose(
        self,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        observations: AuthorizedObservationSetV1,
        user_intent: str,
        audience_constraints: tuple[str, ...],
        cadence_constraints: tuple[ProposedCadence, ...],
        created_at: datetime,
    ) -> IntelligenceModelProposalV1:
        provider = _resolve_provider(self.provider, self.provider_factory)
        trusted_context = {
            "audience_constraints": list(audience_constraints),
            "cadence_constraints": [item.value for item in cadence_constraints],
            "concept_model": concept_model.model_dump(mode="json"),
            "goal_ref": session.goal_ref,
            "observations": observations.model_dump(mode="json"),
            "user_intent": user_intent,
        }
        output_contract = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "citations",
                "watch_targets",
                "baselines",
                "detectors",
                "materiality_rules",
                "audiences",
                "routes",
                "suppression_grouping_rules",
                "epistemic_statements",
                "unknowns",
                "exclusions",
                "confidence",
            ],
            "properties": {
                "audiences": _array_schema(_inline_model_schema(AudienceProposalV1), min_items=1, max_items=64),
                "baselines": _array_schema(_inline_model_schema(BaselineProposalV1), min_items=1, max_items=128),
                "citations": _array_schema(
                    _citation_selection_schema(id_field="observation_id"), min_items=1, max_items=256
                ),
                "confidence": _CONFIDENCE_SCHEMA,
                "conflicts": _array_schema(_inline_model_schema(IntelligenceConflictV1), max_items=128),
                "detectors": _array_schema(_inline_model_schema(DetectorProposalV1), min_items=1, max_items=128),
                "epistemic_statements": _array_schema(
                    _inline_model_schema(EpistemicStatementV1), min_items=1, max_items=256
                ),
                "exclusions": _string_array_schema(min_items=1, max_items=128),
                "materiality_rules": _array_schema(_inline_model_schema(MaterialityRuleV1), min_items=1, max_items=128),
                "routes": _array_schema(_inline_model_schema(RoutingCadenceProposalV1), min_items=1, max_items=128),
                "suppression_grouping_rules": _array_schema(
                    _inline_model_schema(SuppressionGroupingRuleV1), min_items=1, max_items=128
                ),
                "unknowns": _string_array_schema(min_items=1, max_items=128),
                "watch_targets": _array_schema(_inline_model_schema(WatchTargetV1), min_items=1, max_items=128),
            },
        }
        material = await _call_provider(
            provider,
            stage="intelligence_model_proposal",
            trusted_context=trusted_context,
            output_contract=output_contract,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        _reject_unknown_keys(material, self._ALLOWED_FIELDS, stage="intelligence_model_proposal")
        citations = _reconstruct_intelligence_citations(material.get("citations"), observations=observations)
        watch_targets = _build_models(material.get("watch_targets"), WatchTargetV1, label="watch_targets")
        _validate_watch_targets(watch_targets, concept_model=concept_model)
        try:
            return IntelligenceModelProposalV1(
                session_id=session.session_id,
                correlation_id=session.correlation_id,
                goal_ref=session.goal_ref,
                user_intent=user_intent,
                concept_model_proposal_id=str(concept_model.proposal_id),
                concept_model_proposal_digest=str(concept_model.proposal_digest),
                concept_model_disposition_id=str(concept_disposition.disposition_id),
                concept_model_disposition_digest=str(concept_disposition.disposition_digest),
                observation_set_id=str(observations.observation_set_id),
                observation_set_digest=str(observations.observation_set_digest),
                audience_constraints=audience_constraints,
                cadence_constraints=cadence_constraints,
                revision=1,
                citations=citations,
                watch_targets=watch_targets,
                baselines=_build_models(material.get("baselines"), BaselineProposalV1, label="baselines"),
                detectors=_build_models(material.get("detectors"), DetectorProposalV1, label="detectors"),
                materiality_rules=_build_models(
                    material.get("materiality_rules"), MaterialityRuleV1, label="materiality_rules"
                ),
                audiences=_build_models(material.get("audiences"), AudienceProposalV1, label="audiences"),
                routes=_build_models(material.get("routes"), RoutingCadenceProposalV1, label="routes"),
                suppression_grouping_rules=_build_models(
                    material.get("suppression_grouping_rules"),
                    SuppressionGroupingRuleV1,
                    label="suppression_grouping_rules",
                ),
                epistemic_statements=_build_models(
                    material.get("epistemic_statements"), EpistemicStatementV1, label="epistemic_statements"
                ),
                conflicts=_build_models(
                    material.get("conflicts"), IntelligenceConflictV1, label="conflicts", required=False
                ),
                unknowns=_string_tuple(material.get("unknowns"), label="unknowns"),
                exclusions=_string_tuple(material.get("exclusions"), label="exclusions"),
                confidence=_confidence(material.get("confidence")),
                created_at=created_at,
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise SelectedBuilderStrategyConflict(
                "provider output failed exact intelligence-model proposal validation"
            ) from exc


class SelectedBriefingStrategy:
    """Adapt the selected local provider to the ``BriefingStrategy`` port."""

    _ALLOWED_FIELDS = {"title", "executive_summary", "items", "freshness_statement"}
    _NO_MATERIAL_SHIFTS_FIELDS = {"no_material_shifts"}

    def __init__(
        self,
        *,
        provider: object | None = None,
        provider_factory: Callable[[], object] = get_llm,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.provider_factory = provider_factory
        self.model = model
        self.max_tokens = max_tokens

    async def synthesize(
        self,
        *,
        session: IntelligenceBuilderSessionRevisionV1,
        concept_model: ConceptModelProposalV1,
        concept_disposition: ConceptModelDispositionV1,
        intelligence_model: IntelligenceModelProposalV1,
        intelligence_disposition: IntelligenceModelDispositionV1,
        observations: AuthorizedObservationSetV1,
        generated_at: datetime,
    ) -> FirstBriefingPreviewV1 | None:
        provider = _resolve_provider(self.provider, self.provider_factory)
        trusted_context = {
            "goal_ref": session.goal_ref,
            "intelligence_model": intelligence_model.model_dump(mode="json"),
            "observations": observations.model_dump(mode="json"),
        }
        output_contract = {
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "executive_summary", "items", "freshness_statement"],
                    "properties": {
                        "executive_summary": {"type": "string", "minLength": 1, "maxLength": 8_000},
                        "freshness_statement": {"type": "string", "minLength": 1, "maxLength": 1_000},
                        "items": _array_schema(_inline_model_schema(BriefingItemV1), min_items=1, max_items=128),
                        "title": {"type": "string", "minLength": 1, "maxLength": 300},
                    },
                },
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["no_material_shifts"],
                    "properties": {"no_material_shifts": {"const": True}},
                },
            ]
        }
        material = await _call_provider(
            provider,
            stage="first_briefing_preview",
            trusted_context=trusted_context,
            output_contract=output_contract,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        if set(material) == self._NO_MATERIAL_SHIFTS_FIELDS:
            if material["no_material_shifts"] is not True:
                raise SelectedBuilderStrategyConflict("'no_material_shifts' must be exactly true when present alone")
            return None
        _reject_unknown_keys(material, self._ALLOWED_FIELDS, stage="first_briefing_preview")
        raw_items = material.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise SelectedBuilderStrategyConflict("first-Brief output requires at least one item")
        items: list[BriefingItemV1] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise SelectedBuilderStrategyConflict("Brief item must be one JSON object")
            try:
                items.append(BriefingItemV1.model_validate(raw_item, strict=False))
            except (TypeError, ValidationError) as exc:
                raise SelectedBuilderStrategyConflict("Brief item failed exact structured validation") from exc
        statements = {item.statement_id: item for item in intelligence_model.epistemic_statements}
        citation_index = {item.citation_id: item for item in intelligence_model.citations}
        used_citation_ids: set[str] = set()
        for item in items:
            bound_statements = []
            for statement_id in item.statement_ids:
                statement = statements.get(statement_id)
                if statement is None:
                    raise SelectedBuilderStrategyConflict("Brief item names an undeclared epistemic statement")
                bound_statements.append(statement)
            if item.epistemic_classification not in {statement.classification for statement in bound_statements}:
                raise SelectedBuilderStrategyConflict(
                    "Brief item epistemic classification does not match its bound statement"
                )
            for citation_id in (*item.citation_ids, *item.counterevidence_citation_ids):
                if citation_id not in citation_index:
                    raise SelectedBuilderStrategyConflict("Brief item names an undeclared intelligence citation")
                used_citation_ids.add(citation_id)
        citations = tuple(citation_index[citation_id] for citation_id in sorted(used_citation_ids))
        derivation = BriefingDerivationV1(
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            concept_model_proposal_id=str(concept_model.proposal_id),
            concept_model_proposal_digest=str(concept_model.proposal_digest),
            concept_model_disposition_id=str(concept_disposition.disposition_id),
            concept_model_disposition_digest=str(concept_disposition.disposition_digest),
            intelligence_model_proposal_id=str(intelligence_model.proposal_id),
            intelligence_model_proposal_digest=str(intelligence_model.proposal_digest),
            intelligence_model_disposition_id=str(intelligence_disposition.disposition_id),
            intelligence_model_disposition_digest=str(intelligence_disposition.disposition_digest),
            observation_set_id=str(observations.observation_set_id),
            observation_set_digest=str(observations.observation_set_digest),
        )
        as_of = max(item.as_of for item in observations.observations)
        try:
            return FirstBriefingPreviewV1(
                derivation=derivation,
                title=material["title"],
                executive_summary=material["executive_summary"],
                items=tuple(items),
                citations=citations,
                as_of=as_of,
                freshness_statement=material["freshness_statement"],
                generated_at=generated_at,
            )
        except (ValidationError, TypeError, ValueError, KeyError) as exc:
            raise SelectedBuilderStrategyConflict(
                "provider output failed exact first-Brief proposal validation"
            ) from exc


__all__ = [
    "SelectedBriefingStrategy",
    "SelectedBuilderStrategyConflict",
    "SelectedBuilderStrategyError",
    "SelectedBuilderStrategyUnavailable",
    "SelectedConceptModelStrategy",
    "SelectedIntelligenceModelStrategy",
]

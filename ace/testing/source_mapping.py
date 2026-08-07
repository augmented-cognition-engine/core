"""Packaged conformance seam for pure PREPARED source mappings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ace.core.source import CanonicalSourceSnapshotV1Alpha1
from ace.intelligence.contracts.resources import (
    IntelligenceResourceMode,
    LineageRelation,
    LineageResourceKind,
)
from ace.intelligence.contracts.source_mapping import ResolvedSubjectBindingV1Alpha1
from ace.intelligence.packs.runtime import PreparedActivationBinding
from ace.intelligence.source_mapping import interpret_prepared_source_mapping


@dataclass(frozen=True, slots=True)
class SourceMappingConformanceResult:
    """Stable identities and normalized attributes produced by one conformance run."""

    result_mode: IntelligenceResourceMode
    observation_mode: IntelligenceResourceMode
    entity_snapshot_mode: IntelligenceResourceMode
    live_authority: bool
    live_acquisition: bool
    observation_id: str
    observation_digest: str
    entity_snapshot_id: str
    entity_snapshot_digest: str
    attributes_json: str
    lineage_kind: LineageResourceKind
    lineage_relation: LineageRelation
    lineage_resource_id: str
    lineage_resource_digest: str
    lineage_resource_as_of: datetime
    lineage_resource_available_at: datetime


def exercise_prepared_source_mapping(
    *,
    binding: PreparedActivationBinding,
    mapping_id: str,
    source_snapshot: CanonicalSourceSnapshotV1Alpha1,
    subject_binding: ResolvedSubjectBindingV1Alpha1,
) -> SourceMappingConformanceResult:
    """Run the public interpreter and verify its exact one-edge PREPARED result shape."""

    result = interpret_prepared_source_mapping(
        binding=binding,
        mapping_id=mapping_id,
        source_snapshot=source_snapshot,
        subject_binding=subject_binding,
    )
    lineage = result.entity_snapshot.lineage
    if (
        result.mode is not IntelligenceResourceMode.PREPARED
        or result.observation.mode is not IntelligenceResourceMode.PREPARED
        or result.entity_snapshot.mode is not IntelligenceResourceMode.PREPARED
    ):
        raise AssertionError("source mapping conformance accepts only PREPARED resources")
    if result.live_authority is not False or result.live_acquisition is not False:
        raise AssertionError("PREPARED source mapping cannot assert live authority or acquisition")
    if len(lineage) != 1:
        raise AssertionError("source mapping result does not have one exact Observation lineage edge")
    if (
        result.observation.resource_id is None
        or result.observation.resource_digest is None
        or result.entity_snapshot.resource_id is None
        or result.entity_snapshot.resource_digest is None
    ):
        raise AssertionError("source mapping result is missing a derived content identity")
    edge = lineage[0]
    if (
        edge.resource_kind is not LineageResourceKind.OBSERVATION
        or edge.relation is not LineageRelation.DERIVED_FROM
        or edge.resource_id != result.observation.resource_id
        or edge.resource_digest != result.observation.resource_digest
        or edge.resource_as_of != result.observation.as_of
        or edge.resource_available_at != result.observation.ingested_at
    ):
        raise AssertionError("source mapping result does not have one exact Observation lineage edge")
    return SourceMappingConformanceResult(
        result_mode=result.mode,
        observation_mode=result.observation.mode,
        entity_snapshot_mode=result.entity_snapshot.mode,
        live_authority=result.live_authority,
        live_acquisition=result.live_acquisition,
        observation_id=result.observation.resource_id,
        observation_digest=result.observation.resource_digest,
        entity_snapshot_id=result.entity_snapshot.resource_id,
        entity_snapshot_digest=result.entity_snapshot.resource_digest,
        attributes_json=result.entity_snapshot.attributes.value_json,
        lineage_kind=edge.resource_kind,
        lineage_relation=edge.relation,
        lineage_resource_id=edge.resource_id,
        lineage_resource_digest=edge.resource_digest,
        lineage_resource_as_of=edge.resource_as_of,
        lineage_resource_available_at=edge.resource_available_at,
    )


__all__ = ["SourceMappingConformanceResult", "exercise_prepared_source_mapping"]

"""Small OLC-style, fixture-backed reference adapter for the TP2 boundary.

This adapter demonstrates domain extraction mapping only.  It does not persist,
choose product scope, or mint identity itself; the Core ingestion service
validates the returned proposals and derives authoritative record IDs.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Iterable, Mapping

from core.engine.grounded_state import (
    BoundedBatchManifestV1,
    EvidenceKind,
    GroundedEvidenceRecordV1,
    canonical_hash,
)


class OLCStyleReferenceAdapter:
    """Map a bounded public-safe extraction slice into provider-neutral proposals."""

    adapter_id = "olc-style-reference"
    adapter_version = "v1"
    primary_model_calls = 0

    @staticmethod
    def _common(record: GroundedEvidenceRecordV1, *, input_key: str) -> dict[str, Any]:
        extraction = record.extraction.model_dump(mode="json", exclude_none=True) if record.extraction else None
        source_span = (
            record.extraction.source_span
            if record.extraction and record.extraction.source_span
            else f"fixture-record:{input_key}"
        )
        return {
            "source_external_id": record.source_id,
            "source_version": record.source_version,
            "publisher_id": record.source_id,
            "local_reference": f"tp0-fixture:{input_key}",
            "temporal": record.temporal.model_dump(mode="json"),
            "published_at": record.published_at.isoformat() if record.published_at else None,
            "ingested_at": record.ingested_at.isoformat(),
            "extracted_at": record.extracted_at.isoformat() if record.extracted_at else None,
            "extraction": extraction,
            "source_span": source_span if extraction else None,
            "degraded_reasons": (),
        }

    @staticmethod
    def _entity_local_id(entity_ref: str) -> str:
        return f"local:canonical-{entity_ref.replace(':', '-')}"

    def map_evidence(self, *, input_key: str, evidence: GroundedEvidenceRecordV1) -> dict[str, Any]:
        common = self._common(evidence, input_key=input_key)
        source_hash = canonical_hash(
            {
                "source_external_id": evidence.source_id,
                "source_version": evidence.source_version,
            }
        )
        records: list[dict[str, Any]] = [
            {
                "kind": "source",
                **common,
                "external_id": evidence.source_id,
                "local_id": f"source-document-{evidence.source_id.replace(':', '-')}",
                "content_hash": source_hash,
                "source_kind": "olc-style-fixture",
                "title": evidence.source_id,
                "content": None,
                "temporal": {"precision": "unknown"},
                "extracted_at": None,
                "extraction": None,
                "source_span": None,
            }
        ]

        entity_locals: list[str] = []
        for entity_ref in evidence.entity_refs:
            local_id = self._entity_local_id(entity_ref)
            entity_locals.append(local_id)
            records.append(
                {
                    "kind": "entity",
                    "external_id": entity_ref,
                    "source_external_id": "olc-style-entity-resolution",
                    "source_version": self.adapter_version,
                    "local_id": local_id,
                    "publisher_id": self.adapter_id,
                    "local_reference": "olc-style:entity-resolution",
                    "temporal": {"precision": "unknown"},
                    "published_at": None,
                    "ingested_at": evidence.ingested_at.isoformat(),
                    "extracted_at": None,
                    "extraction": None,
                    "source_span": None,
                    "degraded_reasons": (),
                    "canonical_name": entity_ref.partition(":")[2].replace("-", " ").title(),
                    "entity_type": "organization",
                    "attributes": {},
                }
            )

        record_local_id = f"local:evidence-{input_key}"
        if evidence.kind is EvidenceKind.EVENT:
            records.append(
                {
                    "kind": "event",
                    **common,
                    "external_id": evidence.external_id,
                    "local_id": record_local_id,
                    "content_hash": evidence.content_hash,
                    "event_type": "source_event",
                    "description": evidence.content,
                    # Core reconstructs version/correction lineage from the stable
                    # source coordinate.  TP0's legacy evidence IDs are not reused.
                    "supersedes": (),
                }
            )
            for index, entity_local_id in enumerate(entity_locals):
                raw_surface = evidence.raw_mentions[index] if index < len(evidence.raw_mentions) else None
                records.append(
                    {
                        "kind": "event_participant",
                        **common,
                        "external_id": f"{evidence.external_id}:participant:{index}",
                        "local_id": f"local:participant-{input_key}-{index}",
                        "event_local_id": record_local_id,
                        "entity_local_id": entity_local_id,
                        "role": "participant",
                        "raw_surface_form": raw_surface,
                    }
                )
                records.append(
                    {
                        "kind": "relation",
                        **common,
                        "external_id": f"{evidence.external_id}:participates-in:{index}",
                        "local_id": f"local:participation-{input_key}-{index}",
                        "relation": "participates_in",
                        "subject_local_id": entity_local_id,
                        "object_local_id": record_local_id,
                        "basis": "The source extraction names the entity as an event participant.",
                    }
                )
        else:
            records.append(
                {
                    "kind": "claim",
                    **common,
                    "external_id": evidence.external_id,
                    "local_id": record_local_id,
                    "content_hash": evidence.content_hash,
                    "claim_text": evidence.content,
                    "entity_local_ids": tuple(entity_locals),
                    "confidence": evidence.confidence,
                    "supersedes": (),
                }
            )
            for index, entity_local_id in enumerate(entity_locals):
                records.append(
                    {
                        "kind": "relation",
                        **common,
                        "external_id": f"{evidence.external_id}:mentions:{index}",
                        "local_id": f"local:mention-{input_key}-{index}",
                        "relation": "mentions",
                        "subject_local_id": record_local_id,
                        "object_local_id": entity_local_id,
                        "basis": "The source-attributed claim retains the canonical entity reference.",
                    }
                )

        if len(entity_locals) == 1:
            mention_bindings = [(mention, entity_locals[0]) for mention in evidence.raw_mentions]
        elif len(entity_locals) == len(evidence.raw_mentions):
            mention_bindings = list(zip(evidence.raw_mentions, entity_locals, strict=True))
        else:
            mention_bindings = []
        for index, (mention, entity_local_id) in enumerate(mention_bindings):
            records.append(
                {
                    "kind": "alias",
                    **common,
                    "external_id": f"{evidence.external_id}:alias:{index}",
                    "local_id": f"local:alias-{input_key}-{index}",
                    "raw_surface_form": mention,
                    "entity_local_id": entity_local_id,
                }
            )

        if evidence.raw_mentions and not mention_bindings:
            input_hash = canonical_hash({"external_id": evidence.external_id, "raw_mentions": evidence.raw_mentions})
            records.append(
                {
                    "kind": "extraction_failure",
                    **common,
                    "external_id": f"{evidence.external_id}:entity-resolution-failure",
                    "local_id": f"local:failure-{input_key}",
                    "content_hash": input_hash,
                    "input_hash": input_hash,
                    "failure_code": "ambiguous_entity_resolution",
                    "failure_message": "Raw mentions could not be bound one-to-one to canonical entity proposals.",
                    "retryable": False,
                    "degraded_reasons": ("ambiguous_entity_resolution",),
                }
            )
        return {"item_key": input_key, "records": records}

    def map_failure(
        self,
        *,
        input_key: str,
        source_external_id: str,
        source_version: str,
        ingested_at: datetime,
        failure_code: str,
        message: str,
    ) -> dict[str, Any]:
        input_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        return {
            "item_key": input_key,
            "records": [
                {
                    "kind": "extraction_failure",
                    "external_id": input_key,
                    "source_external_id": source_external_id,
                    "source_version": source_version,
                    "local_id": f"local:failure-{input_key}",
                    "content_hash": input_hash,
                    "publisher_id": source_external_id,
                    "local_reference": f"olc-style:failed-input:{input_key}",
                    "temporal": {"precision": "unknown"},
                    "published_at": None,
                    "ingested_at": ingested_at.isoformat(),
                    "extracted_at": None,
                    "extraction": None,
                    "source_span": None,
                    "degraded_reasons": (failure_code,),
                    "failure_code": failure_code,
                    "failure_message": message,
                    "input_hash": input_hash,
                    "retryable": False,
                }
            ],
        }

    def build_manifest(
        self,
        *,
        product_id: str,
        manifest_external_id: str,
        extraction_run_id: str,
        submitted_at: datetime,
        records: Iterable[Mapping[str, Any]],
    ) -> BoundedBatchManifestV1:
        items: list[dict[str, Any]] = []
        for raw in records:
            input_key = str(raw["input_key"])
            evidence = GroundedEvidenceRecordV1.model_validate(raw["record"])
            items.append(self.map_evidence(input_key=input_key, evidence=evidence))
        return BoundedBatchManifestV1(
            product_id=product_id,
            manifest_external_id=manifest_external_id,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            extraction_run_id=extraction_run_id,
            submitted_at=submitted_at,
            items=tuple(items),
        )

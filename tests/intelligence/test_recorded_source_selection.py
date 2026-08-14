from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.recorded_source_selection import RecordedSourceSelectionV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)


def _pack(seed: str = "a") -> CompiledPackRefV1:
    digest = seed * 64
    return CompiledPackRefV1(
        pack_id="world_intelligence_ai_v1",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{digest[:32]}",
        pack_digest=f"sha256:{digest}",
    )


def _selection(**updates) -> RecordedSourceSelectionV1Alpha1:
    material = {
        "product_id": "product:personal-intelligence",
        "pack": _pack(),
        "source_group_id": "official_records",
        "mapping_id": "ai_policy_record_snapshot",
        "subject_binding_id": "published_ai_policy_record",
        "entity_type_id": "ai_policy_record",
        "entity_ref": "entity:ai-policy",
        "source_definition_ref": "source_definition:ai-policy-eo-14409",
        "source_type_ref": "source:official-record/v1",
        "source_uri": "https://example.invalid/official/eo-14409",
        "captured_payload_digest": "sha256:" + "c" * 64,
        "source_published_at": NOW - timedelta(hours=2),
        "event_effective_at": NOW - timedelta(hours=1),
        "observed_at": NOW,
        "locator": "document:eo-14409",
    }
    material.update(updates)
    return RecordedSourceSelectionV1Alpha1(**material)


@pytest.mark.parametrize(
    "updates",
    [
        {"product_id": "product:other"},
        {"pack": _pack("b")},
        {"mapping_id": "ai_policy_implementation_snapshot"},
        {"subject_binding_id": "other_subject"},
        {"entity_type_id": "ai_implementation_record"},
        {"entity_ref": "entity:other-ai-policy"},
        {"source_definition_ref": "source_definition:other"},
        {"source_type_ref": "source:other/v1"},
        {"source_uri": "https://example.invalid/official/other"},
        {"captured_payload_digest": "sha256:" + "d" * 64},
        {"source_published_at": NOW - timedelta(hours=3)},
        {"event_effective_at": NOW - timedelta(minutes=30)},
        {"observed_at": NOW + timedelta(minutes=1)},
        {"locator": "document:other"},
    ],
)
def test_every_reviewed_source_coordinate_changes_selection_identity(updates) -> None:
    baseline = _selection()
    changed = _selection(**updates)

    assert changed.selection_id != baseline.selection_id
    assert changed.selection_digest != baseline.selection_digest


def test_selection_rejects_forged_identity_and_invalid_time_order() -> None:
    baseline = _selection()
    material = baseline.model_dump(mode="python", exclude={"selection_id", "selection_digest"})

    with pytest.raises(ValueError, match="selection_id"):
        RecordedSourceSelectionV1Alpha1(**material, selection_id="recorded_source_selection:forged")
    with pytest.raises(ValueError, match="cannot follow observed_at"):
        _selection(event_effective_at=NOW + timedelta(seconds=1))

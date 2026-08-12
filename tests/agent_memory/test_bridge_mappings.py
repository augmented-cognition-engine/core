from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from ace.application.domain_activation_plan_contracts import (
    ActivationRuntimeState,
    DomainActivationCommitReferenceV1Alpha2,
)
from ace.core.agent_memory import (
    ByteRangeSpanV1Alpha1,
    HistoricalLineageReferenceV1Alpha1,
    SourceProvenanceV1Alpha1,
    UnavailableSourceSpanV1Alpha1,
    UnavailableSpanReason,
)
from ace.core.agent_memory_bridges import provenance_from_canonical_source_snapshot
from ace.core.contracts import canonical_hash
from ace.core.source import CanonicalSourceSnapshotV1Alpha1, SourceAcquisitionMode

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 11, 23, 0, tzinfo=UTC)
PAYLOAD = '{"captured_scope":"product:foreign","value":"bounded"}'


def _snapshot() -> CanonicalSourceSnapshotV1Alpha1:
    return CanonicalSourceSnapshotV1Alpha1(
        source_definition_ref="source:briefing-feed",
        source_type_ref="synthetic.fixture",
        source_uri="fixture://agent-memory/briefing-feed",
        captured_payload_json=PAYLOAD,
        captured_payload_digest=f"sha256:{hashlib.sha256(PAYLOAD.encode()).hexdigest()}",
        source_published_at=NOW - timedelta(minutes=10),
        event_effective_at=NOW - timedelta(minutes=15),
        observed_at=NOW - timedelta(minutes=5),
        ingested_at=NOW,
        locator="legacy free-form locator is not canonical exactness",
        acquisition_mode=SourceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:source-acquisition",
        acquisition_receipt_digest="sha256:" + "a" * 64,
    )


def test_canonical_source_bridge_preserves_identity_digest_and_exact_span_only() -> None:
    snapshot = _snapshot()
    provenance = provenance_from_canonical_source_snapshot(
        snapshot,
        span=ByteRangeSpanV1Alpha1(
            source_version_id=snapshot.source_snapshot_ref,
            start_byte=0,
            end_byte=24,
        ),
        capture_method_ref="source.canonical-snapshot",
    )

    assert provenance.source_id == snapshot.source_definition_ref
    assert provenance.source_version_id == snapshot.source_snapshot_ref
    assert provenance.content_digest == snapshot.captured_payload_digest
    assert provenance.acquisition_receipt_ref == snapshot.acquisition_receipt_ref
    assert provenance.derived_from == (snapshot.source_snapshot_ref,)
    assert "payload" not in type(provenance).model_fields
    assert "captured_scope" not in provenance.model_dump_json()
    assert "legacy free-form locator" not in provenance.model_dump_json()


def test_canonical_source_bridge_preserves_unavailable_locator_without_invention() -> None:
    snapshot = _snapshot()
    provenance = provenance_from_canonical_source_snapshot(
        snapshot,
        span=UnavailableSourceSpanV1Alpha1(
            source_version_id=snapshot.source_snapshot_ref,
            reason=UnavailableSpanReason.ADAPTER_UNSUPPORTED,
            detail="the compatibility source supplied no canonical byte, region, or pointer locator",
        ),
        capture_method_ref="source.canonical-snapshot",
    )

    assert provenance.span.kind == "unavailable"
    assert provenance.span.reason is UnavailableSpanReason.ADAPTER_UNSUPPORTED


def test_canonical_source_bridge_rejects_a_span_from_another_version() -> None:
    with pytest.raises(ValueError, match="exact canonical source snapshot"):
        provenance_from_canonical_source_snapshot(
            _snapshot(),
            span=ByteRangeSpanV1Alpha1(
                source_version_id="source_snapshot:foreign",
                start_byte=0,
                end_byte=10,
            ),
            capture_method_ref="source.canonical-snapshot",
        )


def test_activation_commit_reference_is_optional_exact_historical_lineage_never_authority() -> None:
    activation = DomainActivationCommitReferenceV1Alpha2(
        product_id="product:agent-memory-lineage",
        activation_key="market-briefing",
        activation_id="domain_activation:market-briefing",
        state=ActivationRuntimeState.ACTIVE,
        plan_id="domain_activation_plan:market-briefing-v1",
        plan_digest="sha256:" + "b" * 64,
        revision=1,
        revision_id="domain_activation_revision:market-briefing-v1",
        revision_digest="sha256:" + "c" * 64,
        commit_receipt_id="governed_state_commit_receipt:market-briefing-v1",
        commit_receipt_digest="sha256:" + "d" * 64,
        committed_at=NOW,
    )
    lineage = HistoricalLineageReferenceV1Alpha1(
        referenced_contract=activation.contract,
        referenced_record_ref=activation.commit_receipt_id,
        referenced_material_digest=f"sha256:{canonical_hash(activation.model_dump(mode='json'))}",
    )
    source = provenance_from_canonical_source_snapshot(
        _snapshot(),
        span=ByteRangeSpanV1Alpha1(
            source_version_id=_snapshot().source_snapshot_ref,
            start_byte=0,
            end_byte=24,
        ),
        capture_method_ref="source.canonical-snapshot",
    )
    material = source.model_dump(mode="python")
    material["historical_lineage"] = (lineage,)
    with_lineage = SourceProvenanceV1Alpha1.model_validate(material)

    assert with_lineage.historical_lineage == (lineage,)
    assert lineage.referenced_contract == "ace.application.domain-activation-commit-reference/v1alpha2"
    assert lineage.authority_stage == "historical_reference"
    assert lineage.live_authority is False
    assert "activation" not in type(lineage).model_fields
    assert "approve" not in type(lineage).model_fields

    widened = lineage.model_dump(mode="python")
    widened["live_authority"] = True
    with pytest.raises(ValueError, match="False"):
        HistoricalLineageReferenceV1Alpha1.model_validate(widened)

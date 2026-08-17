"""Host seam from canonical Core source capture to Code incident evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources

from ace.core import CanonicalSourceSnapshotV1Alpha1, SourceAcquisitionMode, canonical_hash, canonical_json
from core.engine.code_intelligence.incidents import IncidentSourceEnvelopeV1Alpha1

TBTC_INCIDENT_FIXTURE_RESOURCE = "fixtures/tbtc_deposit_pause_2020_v1.json"
TBTC_INCIDENT_REPORT_URI = (
    "https://github.com/keep-network/tbtc-website/blob/"
    "083c62168e470e466e9d701fb48242eef254d7b5/"
    "src/pages/news/2020-05-21-details-of-the-tbtc-deposit-pause-on-may-18-2020.md"
)


@dataclass(frozen=True, slots=True)
class PreparedCodeIncidentSource:
    """Exact Core snapshot paired with its authority-free Code envelope."""

    snapshot: CanonicalSourceSnapshotV1Alpha1
    envelope: IncidentSourceEnvelopeV1Alpha1


def bundled_tbtc_incident_fixture_text() -> str:
    """Read the packaged public fixture without accepting a caller-controlled path."""

    package = resources.files("core.engine.code_intelligence")
    return package.joinpath(TBTC_INCIDENT_FIXTURE_RESOURCE).read_text(encoding="utf-8")


def incident_envelope_from_canonical_snapshot(
    snapshot: CanonicalSourceSnapshotV1Alpha1,
) -> IncidentSourceEnvelopeV1Alpha1:
    """Narrow an already validated Core snapshot into the Code-owned contract."""

    snapshot = CanonicalSourceSnapshotV1Alpha1.model_validate(snapshot.model_dump())
    if snapshot.source_type_ref != "code-intelligence.public-incident-fixture":
        raise ValueError("canonical source snapshot is not a Code incident fixture")
    if snapshot.acquisition_mode is not SourceAcquisitionMode.PREPARED_FIXTURE:
        raise ValueError("Code incident projection accepts only the prepared fixture source")
    assert snapshot.source_snapshot_ref is not None
    assert snapshot.source_snapshot_digest is not None
    assert snapshot.source_published_at is not None
    assert snapshot.event_effective_at is not None
    assert snapshot.locator is not None
    return IncidentSourceEnvelopeV1Alpha1(
        source_definition_ref=snapshot.source_definition_ref,
        source_snapshot_ref=snapshot.source_snapshot_ref,
        source_snapshot_digest=snapshot.source_snapshot_digest,
        source_type_ref=snapshot.source_type_ref,
        source_uri=snapshot.source_uri,
        captured_payload_json=snapshot.captured_payload_json,
        captured_payload_digest=snapshot.captured_payload_digest,
        source_published_at=snapshot.source_published_at,
        event_effective_at=snapshot.event_effective_at,
        observed_at=snapshot.observed_at,
        ingested_at=snapshot.ingested_at,
        locator=snapshot.locator,
        acquisition_mode=snapshot.acquisition_mode.value,
        acquisition_receipt_ref=snapshot.acquisition_receipt_ref,
        acquisition_receipt_digest=snapshot.acquisition_receipt_digest,
    )


def prepare_bundled_tbtc_incident_source(
    *,
    observed_at: datetime,
    ingested_at: datetime | None = None,
) -> PreparedCodeIncidentSource:
    """Capture the packaged MIT fixture through the canonical Core source model."""

    ingested_at = ingested_at or observed_at
    payload = canonical_json(json.loads(bundled_tbtc_incident_fixture_text()))
    payload_digest = f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
    acquisition_digest = f"sha256:{canonical_hash({'mode': 'prepared_fixture', 'payload': payload_digest})}"
    snapshot = CanonicalSourceSnapshotV1Alpha1(
        source_definition_ref="source_definition:code-intelligence-tbtc-incident-v1",
        source_type_ref="code-intelligence.public-incident-fixture",
        source_uri=TBTC_INCIDENT_REPORT_URI,
        captured_payload_json=payload,
        captured_payload_digest=payload_digest,
        source_published_at=datetime(2020, 5, 21, 17, 2, 51, 487000, tzinfo=UTC),
        event_effective_at=datetime(2020, 3, 15, 15, 52, tzinfo=UTC),
        observed_at=observed_at,
        ingested_at=ingested_at,
        locator="git-blob:693535acb820c7b8347c4e1bf3bccc81414b01c8",
        acquisition_mode=SourceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="acquisition_receipt:tbtc-incident-fixture-v1",
        acquisition_receipt_digest=acquisition_digest,
    )
    return PreparedCodeIncidentSource(
        snapshot=snapshot,
        envelope=incident_envelope_from_canonical_snapshot(snapshot),
    )


__all__ = [
    "PreparedCodeIncidentSource",
    "TBTC_INCIDENT_FIXTURE_RESOURCE",
    "TBTC_INCIDENT_REPORT_URI",
    "bundled_tbtc_incident_fixture_text",
    "incident_envelope_from_canonical_snapshot",
    "prepare_bundled_tbtc_incident_source",
]

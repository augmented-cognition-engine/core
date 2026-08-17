#!/usr/bin/env python3
"""Emit a body-free local receipt for the qualified tBTC incident coordinate."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from git import Repo

from core.engine.code_intelligence.contracts import stable_digest
from core.engine.code_intelligence.incident_index_binding import (
    ExactLocalRepositorySnapshotV1Alpha1,
    IncidentLocalIndexBindingReceiptV1Alpha1,
    bind_incident_projection_to_local_index,
    capture_exact_local_repository_snapshot,
    validate_incident_local_index_binding,
)
from core.engine.code_intelligence.incident_source import prepare_bundled_tbtc_incident_source
from core.engine.code_intelligence.incidents import project_public_incident_to_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path, help="Exact clean tBTC checkout")
    parser.add_argument("--output", required=True, type=Path, help="New body-free JSON receipt")
    return parser


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def main() -> int:
    args = _parser().parse_args()
    repository = args.repository.absolute().resolve(strict=True)
    output = args.output.absolute()
    if output.exists():
        raise ValueError("output receipt already exists")
    output_parent = output.parent.resolve(strict=True)
    if _is_within(output.resolve(strict=False), repository):
        raise ValueError("output receipt must be outside the verified repository")

    observed_at = datetime.now(UTC)
    prepared = prepare_bundled_tbtc_incident_source(observed_at=observed_at)
    projection = project_public_incident_to_code(prepared.envelope)
    snapshot = capture_exact_local_repository_snapshot(
        repository,
        projection.code_coordinates[0],
        captured_at=datetime.now(UTC),
    )
    receipt = bind_incident_projection_to_local_index(
        repository_path=repository,
        source=prepared.envelope,
        projection=projection,
        snapshot=snapshot,
    )
    reopened_snapshot = ExactLocalRepositorySnapshotV1Alpha1.model_validate_json(snapshot.model_dump_json())
    reopened_receipt = IncidentLocalIndexBindingReceiptV1Alpha1.model_validate_json(receipt.model_dump_json())
    validated = validate_incident_local_index_binding(
        repository_path=repository,
        receipt=reopened_receipt,
        source=prepared.envelope,
        projection=projection,
        snapshot=reopened_snapshot,
    )

    repo = Repo(repository, search_parent_directories=False)
    coordinate = projection.code_coordinates[0]
    result = {
        "contract": "ace.code-intelligence.incident-local-index-binding-local-evidence/v1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "temporary_local_evidence": True,
        "checkout": {
            "path": str(repository),
            "repository_url": "https://github.com/keep-network/tbtc",
            "head": repo.head.commit.hexsha,
            "clean": not repo.is_dirty(untracked_files=True),
            "tracked_entry": repo.git.ls_tree("HEAD", "--", coordinate.path),
        },
        "source": {
            "source_snapshot_ref": prepared.envelope.source_snapshot_ref,
            "source_snapshot_digest": prepared.envelope.source_snapshot_digest,
            "paired_source_projection_validation": True,
        },
        "projection": {
            "projection_id": projection.projection_id,
            "projection_digest": stable_digest(projection),
            "relation_id": projection.relations[0].relation_id,
            "relation": "affected_code_snapshot",
        },
        "local_index": {
            "index_id": snapshot.index_id,
            "index_digest": snapshot.index_digest,
            "artifact_id": snapshot.artifact_id,
            "artifact_file_digest": snapshot.artifact.file_digest,
            "artifact_span_digest": snapshot.artifact.span_digest,
            "repository_snapshot_id": snapshot.snapshot_id,
            "repository_snapshot_digest": snapshot.snapshot_digest,
            "captured_at": snapshot.captured_at.isoformat().replace("+00:00", "Z"),
            "paired_repository_revalidation": True,
        },
        "binding": {"receipt_id": validated.receipt_id, **validated.model_dump(mode="json")},
        "restart": {
            "snapshot_round_trip_validated": True,
            "receipt_round_trip_validated": True,
        },
        "limitations": {
            "solidity_semantic_analysis": False,
            "dependency_inference": False,
            "impact_inference": False,
            "source_body_included": False,
            "live_journey_wired": False,
            "self_authenticates_repository_snapshot": False,
        },
        "authority": {
            "source": False,
            "reasoning": False,
            "change": False,
            "approval": False,
            "delivery": False,
            "execution": False,
            "effect": False,
        },
    }
    payload = json.dumps(
        result,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    output_parent.joinpath(output.name).write_text(payload + "\n", encoding="utf-8", errors="strict")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

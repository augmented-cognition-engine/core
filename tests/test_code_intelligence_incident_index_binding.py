from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from git import Repo
from pydantic import ValidationError

from core.engine.code_intelligence import incident_index_binding as binding
from core.engine.code_intelligence.incident_index_binding import (
    ExactLocalRepositorySnapshotV1Alpha1,
    IncidentIndexBindingError,
    IncidentLocalIndexBindingReceiptV1Alpha1,
    bind_incident_projection_to_local_index,
    bundled_tbtc_code_artifact_bytes,
    capture_exact_local_repository_snapshot,
    validate_incident_local_index_binding,
)
from core.engine.code_intelligence.incident_source import prepare_bundled_tbtc_incident_source
from core.engine.code_intelligence.incidents import (
    IncidentProjectionError,
    IncidentToCodeProjectionV1Alpha1,
    project_public_incident_to_code,
)

OBSERVED_AT = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
CAPTURED_AT = datetime(2026, 8, 14, 12, 1, tzinfo=UTC)
EXPECTED_REVISION = "9651d53a443b3d2470e13ee1db0ecae60be8b246"
EXPECTED_PATH = "solidity/contracts/deposit/DepositRedemption.sol"


def _local_fixture_repository(tmp_path: Path) -> Path:
    root = tmp_path / "tbtc"
    target = root / EXPECTED_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(bundled_tbtc_code_artifact_bytes())
    repo = Repo.init(root)
    with repo.config_writer() as config:
        config.set_value("user", "name", "ACE fixture")
        config.set_value("user", "email", "fixture@invalid.example")
    repo.index.add([EXPECTED_PATH])
    repo.index.commit("Freeze exact qualified tBTC artifact")
    repo.create_remote("origin", "https://github.com/keep-network/tbtc.git")
    return root


def _source_projection():
    prepared = prepare_bundled_tbtc_incident_source(observed_at=OBSERVED_AT)
    projection = project_public_incident_to_code(prepared.envelope)
    return prepared, projection


def _qualified_identity(*, dirty: bool = False):
    return binding._GitIdentity(  # noqa: SLF001 - controlled adapter seam for offline exact-byte tests
        repository_url="https://github.com/keep-network/tbtc",
        revision=EXPECTED_REVISION,
        dirty=dirty,
        working_tree_digest="dirty" if dirty else "clean",
    )


def _capture(tmp_path: Path, monkeypatch) -> tuple:
    root = _local_fixture_repository(tmp_path)
    prepared, projection = _source_projection()
    monkeypatch.setattr(binding, "_git_identity", lambda _: _qualified_identity())
    snapshot = capture_exact_local_repository_snapshot(
        root,
        projection.code_coordinates[0],
        captured_at=CAPTURED_AT,
    )
    return root, prepared, projection, snapshot


def test_exact_local_inventory_binds_body_free_receipt_without_solidity_semantics(tmp_path: Path, monkeypatch) -> None:
    root, prepared, projection, snapshot = _capture(tmp_path, monkeypatch)
    receipt = bind_incident_projection_to_local_index(
        repository_path=root,
        source=prepared.envelope,
        projection=projection,
        snapshot=snapshot,
    )

    assert snapshot.index.analysis_profile == "exact-source-coordinate-inventory-v1"
    assert snapshot.index.observed_languages == ("solidity",)
    assert snapshot.index.semantic_languages == ()
    assert snapshot.artifact.path == EXPECTED_PATH
    assert snapshot.artifact.symbol == "redemptionTransactionChecks"
    assert (snapshot.artifact.line_start, snapshot.artifact.line_end) == (326, 355)
    assert snapshot.artifact.file_digest == ("sha256:22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330")
    assert snapshot.artifact.span_digest == ("sha256:8dcc8a65e144e04de894826c9b7777430570265f175198a0b687d6652c50d172")
    assert snapshot.artifact.git_blob_sha == "e7e16d77c32fd23437320cede83c07db75e6f5e8"
    assert receipt.semantic_scope == "none"
    assert receipt.dependency_inference_performed is receipt.impact_inference_performed is False
    assert receipt.body_included is False
    assert receipt.provider_neutral is receipt.read_only is True
    assert receipt.source_authority is receipt.reasoning_authority is False
    assert receipt.change_authority is receipt.approval_authority is False
    assert receipt.delivery_authority is receipt.execution_authority is receipt.effect_authority is False
    receipt_payload = receipt.model_dump(mode="json")
    serialized = json.dumps(receipt_payload, sort_keys=True)
    assert "pragma solidity" not in serialized
    assert "excerpt" not in receipt_payload and "body" not in receipt_payload


def test_content_ids_stay_stable_while_snapshot_identity_closes_capture_time(tmp_path: Path, monkeypatch) -> None:
    root, prepared, projection, first = _capture(tmp_path, monkeypatch)
    same_capture = capture_exact_local_repository_snapshot(
        root,
        projection.code_coordinates[0],
        captured_at=CAPTURED_AT,
    )
    shifted_capture = capture_exact_local_repository_snapshot(
        root,
        projection.code_coordinates[0],
        captured_at=CAPTURED_AT + timedelta(seconds=30),
    )
    assert first.index_id == same_capture.index_id == shifted_capture.index_id
    assert first.index_digest == same_capture.index_digest == shifted_capture.index_digest
    assert first.artifact_id == same_capture.artifact_id == shifted_capture.artifact_id
    assert first.snapshot_id == same_capture.snapshot_id
    assert first.snapshot_digest == same_capture.snapshot_digest
    assert first.snapshot_id != shifted_capture.snapshot_id
    assert first.snapshot_digest != shifted_capture.snapshot_digest

    receipt = bind_incident_projection_to_local_index(
        repository_path=root,
        source=prepared.envelope,
        projection=projection,
        snapshot=first,
    )
    reopened_snapshot = ExactLocalRepositorySnapshotV1Alpha1.model_validate_json(first.model_dump_json())
    reopened_receipt = IncidentLocalIndexBindingReceiptV1Alpha1.model_validate_json(receipt.model_dump_json())
    validated = validate_incident_local_index_binding(
        repository_path=root,
        receipt=reopened_receipt,
        source=prepared.envelope,
        projection=projection,
        snapshot=reopened_snapshot,
    )
    assert validated == receipt
    assert validated.receipt_id == receipt.receipt_id


def test_crosswired_or_shifted_capture_timestamps_fail_closed(tmp_path: Path, monkeypatch) -> None:
    root, prepared, projection, snapshot = _capture(tmp_path, monkeypatch)
    receipt = bind_incident_projection_to_local_index(
        repository_path=root,
        source=prepared.envelope,
        projection=projection,
        snapshot=snapshot,
    )

    crosswired = snapshot.model_dump(mode="json")
    crosswired["index"]["generated_at"] = datetime(1999, 1, 1, tzinfo=UTC).isoformat()
    crosswired["captured_at"] = datetime(2099, 1, 1, tzinfo=UTC).isoformat()
    with pytest.raises(ValidationError, match="capture timestamp differs"):
        ExactLocalRepositorySnapshotV1Alpha1.model_validate(crosswired)

    shifted_time = CAPTURED_AT + timedelta(seconds=30)
    shifted = snapshot.model_dump(mode="json")
    shifted["index"]["generated_at"] = shifted_time.isoformat()
    shifted["captured_at"] = shifted_time.isoformat()
    shifted_snapshot = ExactLocalRepositorySnapshotV1Alpha1.model_validate(shifted)
    assert shifted_snapshot.index_id == snapshot.index_id
    assert shifted_snapshot.artifact_id == snapshot.artifact_id
    assert shifted_snapshot.snapshot_id != snapshot.snapshot_id
    assert shifted_snapshot.snapshot_digest != snapshot.snapshot_digest
    with pytest.raises(IncidentIndexBindingError, match="identities do not match"):
        validate_incident_local_index_binding(
            repository_path=root,
            receipt=receipt,
            source=prepared.envelope,
            projection=projection,
            snapshot=shifted_snapshot,
        )


@pytest.mark.parametrize(
    ("identity", "message"),
    [
        (
            binding._GitIdentity("https://github.com/attacker/tbtc", EXPECTED_REVISION, False, "clean"),  # noqa: SLF001
            "URL differs",
        ),
        (
            binding._GitIdentity("https://github.com/keep-network/tbtc", "0" * 40, False, "clean"),  # noqa: SLF001
            "revision differs",
        ),
        (_qualified_identity(dirty=True), "must be clean"),
    ],
)
def test_wrong_repository_revision_or_dirty_checkout_fails_closed(
    tmp_path: Path,
    monkeypatch,
    identity,
    message: str,
) -> None:
    root = _local_fixture_repository(tmp_path)
    _, projection = _source_projection()
    monkeypatch.setattr(binding, "_git_identity", lambda _: identity)
    with pytest.raises(IncidentIndexBindingError, match=message):
        capture_exact_local_repository_snapshot(root, projection.code_coordinates[0])


def test_late_git_identity_change_cannot_race_exact_capture(tmp_path: Path, monkeypatch) -> None:
    root = _local_fixture_repository(tmp_path)
    _, projection = _source_projection()
    identities = iter((_qualified_identity(), _qualified_identity(dirty=True)))
    monkeypatch.setattr(binding, "_git_identity", lambda _: next(identities))
    with pytest.raises(IncidentIndexBindingError, match="changed during exact coordinate capture"):
        capture_exact_local_repository_snapshot(root, projection.code_coordinates[0])


def test_absent_file_digest_mismatch_and_symlink_fail_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(binding, "_git_identity", lambda _: _qualified_identity())
    _, projection = _source_projection()

    absent = _local_fixture_repository(tmp_path / "absent")
    (absent / EXPECTED_PATH).unlink()
    with pytest.raises(IncidentIndexBindingError, match="absent"):
        capture_exact_local_repository_snapshot(absent, projection.code_coordinates[0])

    mismatched = _local_fixture_repository(tmp_path / "mismatch")
    target = mismatched / EXPECTED_PATH
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(IncidentIndexBindingError, match="whole-file digest"):
        capture_exact_local_repository_snapshot(mismatched, projection.code_coordinates[0])

    symlinked = _local_fixture_repository(tmp_path / "symlink")
    target = symlinked / EXPECTED_PATH
    replacement = symlinked / "replacement.sol"
    replacement.write_bytes(bundled_tbtc_code_artifact_bytes())
    target.unlink()
    os.symlink(replacement, target)
    with pytest.raises(IncidentIndexBindingError, match="symlink"):
        capture_exact_local_repository_snapshot(symlinked, projection.code_coordinates[0])


def test_traversal_absent_symbol_and_span_mismatch_fail_closed(tmp_path: Path, monkeypatch) -> None:
    root = _local_fixture_repository(tmp_path)
    _, projection = _source_projection()
    coordinate = projection.code_coordinates[0]
    monkeypatch.setattr(binding, "_git_identity", lambda _: _qualified_identity())

    traversal = coordinate.model_copy(update={"path": "../DepositRedemption.sol"})
    with pytest.raises(IncidentIndexBindingError, match="coordinate failed closed"):
        capture_exact_local_repository_snapshot(root, traversal)

    monkeypatch.setattr(binding, "_FUNCTION_DECLARATION", re_compile_never())
    with pytest.raises(IncidentIndexBindingError, match="symbol is absent"):
        capture_exact_local_repository_snapshot(root, coordinate)

    wrong_span = coordinate.model_copy(update={"excerpt": coordinate.excerpt.replace("return", "returns", 1)})
    with pytest.raises(IncidentIndexBindingError, match="coordinate failed closed"):
        capture_exact_local_repository_snapshot(root, wrong_span)


def re_compile_never():
    import re

    return re.compile(r"this-symbol-can-never-occur")


def test_projection_requires_paired_source_validation_before_binding(tmp_path: Path, monkeypatch) -> None:
    root, prepared, projection, snapshot = _capture(tmp_path, monkeypatch)
    raw = projection.model_dump(mode="json")
    forged_digest = "sha256:" + "1" * 64
    forged_ref = "source_snapshot:" + "1" * 32
    raw["source_snapshot_digest"] = forged_digest
    raw["source_snapshot_ref"] = forged_ref
    for evidence in raw["evidence"]:
        evidence["source_snapshot_digest"] = forged_digest
        evidence["source_snapshot_ref"] = forged_ref
    standalone = IncidentToCodeProjectionV1Alpha1.model_validate(raw)

    with pytest.raises(IncidentProjectionError, match="does not match the canonical source"):
        bind_incident_projection_to_local_index(
            repository_path=root,
            source=prepared.envelope,
            projection=standalone,
            snapshot=snapshot,
        )


def test_crosswired_snapshot_and_receipt_fail_closed(tmp_path: Path, monkeypatch) -> None:
    root, prepared, projection, snapshot = _capture(tmp_path, monkeypatch)
    artifact = snapshot.artifact.model_copy(update={"path": "solidity/contracts/deposit/Other.sol"})
    crosswired = snapshot.model_copy(update={"artifact": artifact, "artifact_id": artifact.artifact_id})
    with pytest.raises(IncidentIndexBindingError, match="cross-wired|differs from current exact checkout"):
        bind_incident_projection_to_local_index(
            repository_path=root,
            source=prepared.envelope,
            projection=projection,
            snapshot=crosswired,
        )

    receipt = bind_incident_projection_to_local_index(
        repository_path=root,
        source=prepared.envelope,
        projection=projection,
        snapshot=snapshot,
    )
    forged = receipt.model_copy(update={"index_id": "code_exact_local_index:" + "0" * 32})
    with pytest.raises(IncidentIndexBindingError, match="identities do not match"):
        validate_incident_local_index_binding(
            repository_path=root,
            receipt=forged,
            source=prepared.envelope,
            projection=projection,
            snapshot=snapshot,
        )

    artifact = snapshot.artifact.model_copy(update={"path": "solidity/contracts/deposit/Other.sol"})
    crosswired = snapshot.model_copy(update={"artifact": artifact, "artifact_id": artifact.artifact_id})
    fully_crosswired = receipt.model_copy(
        update={
            "artifact_id": artifact.artifact_id,
            "repository_snapshot_id": crosswired.snapshot_id,
            "repository_snapshot_digest": crosswired.snapshot_digest,
        }
    )
    monkeypatch.setattr(binding, "revalidate_exact_local_repository_snapshot", lambda *args: args[2])
    with pytest.raises(IncidentIndexBindingError, match="cross-wired"):
        validate_incident_local_index_binding(
            repository_path=root,
            receipt=fully_crosswired,
            source=prepared.envelope,
            projection=projection,
            snapshot=crosswired,
        )


def test_semantic_dependency_or_impact_claims_are_schema_impossible(tmp_path: Path, monkeypatch) -> None:
    root, prepared, projection, snapshot = _capture(tmp_path, monkeypatch)
    receipt = bind_incident_projection_to_local_index(
        repository_path=root,
        source=prepared.envelope,
        projection=projection,
        snapshot=snapshot,
    )
    for field in ("semantic_analysis_performed", "dependency_inference_performed", "impact_inference_performed"):
        raw_snapshot = snapshot.model_dump(mode="json")
        raw_snapshot[field] = True
        with pytest.raises(ValidationError):
            ExactLocalRepositorySnapshotV1Alpha1.model_validate(raw_snapshot)
    for field in ("dependency_inference_performed", "impact_inference_performed"):
        raw_receipt = receipt.model_dump(mode="json")
        raw_receipt[field] = True
        with pytest.raises(ValidationError):
            IncidentLocalIndexBindingReceiptV1Alpha1.model_validate(raw_receipt)


def test_packaged_artifact_is_exact_and_package_accessible() -> None:
    payload = bundled_tbtc_code_artifact_bytes()
    assert len(payload) == 17_849
    assert hashlib.sha256(payload).hexdigest() == "22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330"
    material = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    assert hashlib.sha1(material, usedforsecurity=False).hexdigest() == "e7e16d77c32fd23437320cede83c07db75e6f5e8"


def test_exact_upstream_mit_license_is_preserved_for_distribution() -> None:
    license_path = Path(__file__).parents[1] / "LICENSE.keep-network-tbtc-9651d53-MIT"
    payload = license_path.read_bytes()
    assert len(payload) == 1_053
    assert hashlib.sha256(payload).hexdigest() == "59f67a2ea030f1fcbfd4f5ffd0aae8b65f66954e5aa0fdd5b745c4ac9eba6fb9"
    material = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    assert hashlib.sha1(material, usedforsecurity=False).hexdigest() == "80a1ed24975b0263f29157a7bc788d9e30ab2adf"
    assert b"Copyright (c) 2020 Keep SEZC." in payload
    assert b"The above copyright notice and this permission notice" in payload

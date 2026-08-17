from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from importlib import resources
from typing import Any

import pytest

from ace.core import CanonicalSourceSnapshotV1Alpha1, SourceAcquisitionMode, canonical_hash, canonical_json
from core.engine.code_intelligence.incident_source import (
    TBTC_INCIDENT_FIXTURE_RESOURCE,
    bundled_tbtc_incident_fixture_text,
    incident_envelope_from_canonical_snapshot,
    prepare_bundled_tbtc_incident_source,
)
from core.engine.code_intelligence.incidents import (
    IncidentProjectionError,
    IncidentSourceEnvelopeV1Alpha1,
    IncidentToCodeProjectionV1Alpha1,
    project_public_incident_to_code,
    validate_incident_projection_against_source,
)
from scripts import verify_code_incident_fixture as verify_fixture_module
from scripts.verify_code_incident_fixture import artifact_facts, verify_artifact_bytes, verify_span

OBSERVED_AT = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _fixture() -> dict[str, Any]:
    return json.loads(bundled_tbtc_incident_fixture_text())


def _envelope(payload: dict[str, Any], *, mode: SourceAcquisitionMode = SourceAcquisitionMode.PREPARED_FIXTURE):
    payload_json = canonical_json(payload)
    payload_digest = f"sha256:{hashlib.sha256(payload_json.encode()).hexdigest()}"
    receipt_digest = f"sha256:{canonical_hash({'mode': mode.value, 'payload': payload_digest})}"
    snapshot = CanonicalSourceSnapshotV1Alpha1(
        source_definition_ref="source_definition:code-intelligence-tbtc-incident-v1",
        source_type_ref="code-intelligence.public-incident-fixture",
        source_uri=(
            "https://github.com/keep-network/tbtc-website/blob/"
            "083c62168e470e466e9d701fb48242eef254d7b5/"
            "src/pages/news/2020-05-21-details-of-the-tbtc-deposit-pause-on-may-18-2020.md"
        ),
        captured_payload_json=payload_json,
        captured_payload_digest=payload_digest,
        source_published_at=datetime(2020, 5, 21, 17, 2, 51, 487000, tzinfo=UTC),
        event_effective_at=datetime(2020, 3, 15, 15, 52, tzinfo=UTC),
        observed_at=OBSERVED_AT,
        ingested_at=OBSERVED_AT,
        locator="git-blob:693535acb820c7b8347c4e1bf3bccc81414b01c8",
        acquisition_mode=mode,
        acquisition_receipt_ref="acquisition_receipt:tbtc-incident-fixture-v1",
        acquisition_receipt_digest=receipt_digest,
    )
    return incident_envelope_from_canonical_snapshot(snapshot)


def _positive(payload: dict[str, Any]) -> dict[str, Any]:
    return next(section for section in payload["sections"] if section["kind"] == "source_declared_code_coordinate")


def _timeline(payload: dict[str, Any]) -> dict[str, Any]:
    return next(section for section in payload["sections"] if section["kind"] == "timeline_only")


def test_qualified_fixture_projects_one_exact_relation_and_two_explicit_omissions() -> None:
    prepared = prepare_bundled_tbtc_incident_source(observed_at=OBSERVED_AT)
    first = project_public_incident_to_code(prepared.envelope)
    second = project_public_incident_to_code(prepared.envelope)

    assert prepared.snapshot.source_snapshot_ref == first.source_snapshot_ref
    assert first == second
    assert first.projection_id == second.projection_id
    assert first.incident.report_commit == "083c62168e470e466e9d701fb48242eef254d7b5"
    assert first.incident.report_blob_sha == "693535acb820c7b8347c4e1bf3bccc81414b01c8"
    assert first.incident.report_content_digest == (
        "sha256:9f105c2a56cae01b16e27625dee1b6c2d32a5f9dae71225bb0c0fb4a659a6a72"
    )
    assert len(first.code_coordinates) == len(first.relations) == 1
    coordinate = first.code_coordinates[0]
    assert coordinate.revision == "9651d53a443b3d2470e13ee1db0ecae60be8b246"
    assert coordinate.path == "solidity/contracts/deposit/DepositRedemption.sol"
    assert coordinate.symbol == "redemptionTransactionChecks"
    assert (coordinate.line_start, coordinate.line_end) == (326, 355)
    relation = first.relations[0]
    assert relation.relation == "affected_code_snapshot"
    assert relation.lexical_match_is_causality is False
    assert relation.introduced_by_claimed is False
    assert relation.root_cause_claimed is False
    assert {item.reason for item in first.omissions} == {
        "no_source_declared_code_coordinate",
        "historical_change_not_conflated_with_affected_snapshot",
    }
    assert "runtime error text" in first.omissions[0].detail
    assert [item.spdx_id for item in first.license_anchors] == ["MIT", "MIT"]
    assert all(clock.occurred_at.utcoffset().total_seconds() == 0 for clock in first.incident.clocks)
    assert first.provider_neutral is first.read_only is True
    assert first.source_acquisition_mode == "prepared_fixture"
    assert first.live_external_fetch_claimed is False
    assert first.governed_adapter_delivery_claimed is False
    assert first.source_snapshot_revalidation_required is True
    assert first.self_authenticates_source_snapshot is False
    assert first.source_authority is False
    assert first.reasoning_authority is False
    assert first.change_authority is False
    assert first.approval_authority is False
    assert first.delivery_authority is False
    assert first.execution_authority is False
    assert first.effect_authority is False


def test_relation_evidence_binds_report_declaration_and_exact_code_coordinate() -> None:
    projection = project_public_incident_to_code(_envelope(_fixture()))
    relation = projection.relations[0]
    evidence = {item.evidence_id: item for item in projection.evidence}

    assert set(relation.evidence_refs) <= set(evidence)
    report = evidence[relation.evidence_refs[0]]
    code = evidence[relation.evidence_refs[1]]
    assert report.immutable_uri.endswith(".md#L45")
    assert (report.line_start, report.line_end) == (45, 45)
    assert code.immutable_uri.endswith("DepositRedemption.sol#L326-L355")
    assert code.content_digest == projection.code_coordinates[0].excerpt_sha256
    assert code.artifact_digest == projection.code_coordinates[0].file_sha256
    timeline_omission = next(item for item in projection.omissions if item.section_id == "incident-timeline")
    assert timeline_omission.evidence_ref in evidence
    assert evidence[timeline_omission.evidence_ref].immutable_uri.endswith(".md#L21-L39")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_sha256", "sha256:" + "0" * 64),
        ("repository_commit", "0" * 40),
        ("repository_path", "src/pages/news/not-the-report.md"),
        ("git_blob_sha", "0" * 40),
        ("byte_count", 1),
        ("repository_url", "https://attacker.example/tbtc-website"),
        ("raw_url", "https://attacker.example/report"),
        ("published_url", "https://attacker.example/news"),
    ],
)
def test_tampered_report_identity_or_digest_fails_closed(field: str, value: str) -> None:
    payload = _fixture()
    payload["report"][field] = value
    if field in {"repository_url", "repository_commit", "repository_path"}:
        payload["report"]["immutable_url"] = (
            f"{payload['report']['repository_url']}/blob/{payload['report']['repository_commit']}/"
            f"{payload['report']['repository_path']}"
        )

    with pytest.raises(IncidentProjectionError, match="report revision, path, blob, URI, or digest"):
        project_public_incident_to_code(_envelope(payload))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("file_sha256", "sha256:" + "0" * 64),
        ("revision", "0" * 40),
        ("path", "solidity/contracts/deposit/Other.sol"),
        ("symbol", "otherFunction"),
        ("git_blob_sha", "0" * 40),
        ("byte_count", 1),
        ("repository_url", "https://attacker.example/tbtc"),
        ("raw_url", "https://attacker.example/code"),
    ],
)
def test_tampered_code_digest_or_coordinate_fails_closed(field: str, value: str) -> None:
    payload = _fixture()
    coordinate = _positive(payload)["code_coordinate"]
    coordinate[field] = value
    if field in {"revision", "path", "repository_url"}:
        coordinate["immutable_url"] = (
            f"{coordinate['repository_url']}/blob/{coordinate['revision']}/{coordinate['path']}"
            f"#L{coordinate['line_start']}-L{coordinate['line_end']}"
        )

    with pytest.raises(IncidentProjectionError, match="code coordinate|fixture failed closed"):
        project_public_incident_to_code(_envelope(payload))


def test_tampered_report_or_code_excerpt_digest_fails_closed() -> None:
    report_payload = _fixture()
    _timeline(report_payload)["excerpt"] += " tampered"
    with pytest.raises(IncidentProjectionError, match="incident excerpt"):
        project_public_incident_to_code(_envelope(report_payload))

    code_payload = _fixture()
    _positive(code_payload)["code_coordinate"]["excerpt_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(IncidentProjectionError, match="code excerpt digest"):
        project_public_incident_to_code(_envelope(code_payload))


def test_self_consistent_forged_source_spans_fail_closed() -> None:
    report_payload = _fixture()
    declaration = _positive(report_payload)
    declaration["excerpt"] = "A schema-valid replacement line that declares no coordinate."
    declaration["excerpt_sha256"] = f"sha256:{hashlib.sha256(declaration['excerpt'].encode()).hexdigest()}"
    with pytest.raises(IncidentProjectionError, match="affected snapshot"):
        project_public_incident_to_code(_envelope(report_payload))

    code_payload = _fixture()
    coordinate = _positive(code_payload)["code_coordinate"]
    coordinate["excerpt"] = "\n".join(f"    // fabricated line {index}" for index in range(30))
    coordinate["excerpt_sha256"] = f"sha256:{hashlib.sha256(coordinate['excerpt'].encode()).hexdigest()}"
    with pytest.raises(IncidentProjectionError, match="affected snapshot"):
        project_public_incident_to_code(_envelope(code_payload))


def test_timeline_error_text_cannot_be_promoted_to_lexical_causality() -> None:
    payload = _fixture()
    timeline = _timeline(payload)
    positive = _positive(payload)
    timeline["code_coordinate"] = positive["code_coordinate"]
    positive["code_coordinate"] = None

    with pytest.raises(IncidentProjectionError, match="timeline-only evidence cannot declare"):
        project_public_incident_to_code(_envelope(payload))


@pytest.mark.parametrize("source_kind", ["error_buffer", "failure_memory"])
def test_generic_failure_records_are_not_incidents(source_kind: str) -> None:
    payload = _fixture()
    payload["source_kind"] = source_kind

    with pytest.raises(IncidentProjectionError, match="source_kind"):
        project_public_incident_to_code(_envelope(payload))


def test_duplicate_and_conflicting_sections_fail_closed() -> None:
    duplicate = _fixture()
    duplicate["sections"].append(dict(duplicate["sections"][0]))
    with pytest.raises(IncidentProjectionError, match="repeats a section id"):
        project_public_incident_to_code(_envelope(duplicate))

    conflict = _fixture()
    _positive(conflict)["code_coordinate"]["relation"] = "introduced_by"
    with pytest.raises(IncidentProjectionError, match="affected_code_snapshot"):
        project_public_incident_to_code(_envelope(conflict))


def test_path_traversal_and_coordinate_bounds_fail_closed() -> None:
    traversal = _fixture()
    coordinate = _positive(traversal)["code_coordinate"]
    coordinate["path"] = "../DepositRedemption.sol"
    coordinate["immutable_url"] = (
        f"{coordinate['repository_url']}/blob/{coordinate['revision']}/{coordinate['path']}"
        f"#L{coordinate['line_start']}-L{coordinate['line_end']}"
    )
    with pytest.raises(IncidentProjectionError, match="traversal"):
        project_public_incident_to_code(_envelope(traversal))

    unbounded = _fixture()
    coordinate = _positive(unbounded)["code_coordinate"]
    coordinate["line_end"] = 526
    coordinate["immutable_url"] = (
        f"{coordinate['repository_url']}/blob/{coordinate['revision']}/{coordinate['path']}#L326-L526"
    )
    with pytest.raises(IncidentProjectionError, match="line bounds"):
        project_public_incident_to_code(_envelope(unbounded))


def test_source_snapshot_payload_digest_is_revalidated_at_projection_boundary() -> None:
    envelope = _envelope(_fixture())
    tampered = envelope.model_copy(update={"captured_payload_digest": "sha256:" + "0" * 64})

    with pytest.raises(IncidentProjectionError, match="payload digest"):
        project_public_incident_to_code(tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_definition_ref", "source_definition:forged"),
        ("source_snapshot_ref", "source_snapshot:" + "0" * 32),
        ("source_snapshot_digest", "sha256:" + "0" * 64),
        ("locator", "git-blob:" + "0" * 40),
        ("acquisition_receipt_ref", "acquisition_receipt:forged"),
        ("acquisition_receipt_digest", "sha256:" + "0" * 64),
    ],
)
def test_forged_or_crosswired_provenance_envelope_fails_closed(field: str, value: str) -> None:
    envelope = _envelope(_fixture()).model_copy(update={field: value})
    with pytest.raises(IncidentProjectionError, match="provenance|snapshot identity"):
        project_public_incident_to_code(envelope)


def test_host_seam_revalidates_model_copy_of_canonical_snapshot() -> None:
    prepared = prepare_bundled_tbtc_incident_source(observed_at=OBSERVED_AT)
    forged = prepared.snapshot.model_copy(update={"source_snapshot_digest": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="source_snapshot_digest does not match"):
        incident_envelope_from_canonical_snapshot(forged)


def test_noncanonical_payload_spelling_cannot_claim_canonical_snapshot_identity() -> None:
    raw = _envelope(_fixture()).model_dump(mode="json")
    raw["captured_payload_json"] = " " + raw["captured_payload_json"]
    raw["captured_payload_digest"] = f"sha256:{hashlib.sha256(raw['captured_payload_json'].encode()).hexdigest()}"
    with pytest.raises(ValueError, match="canonical JSON spelling"):
        IncidentSourceEnvelopeV1Alpha1.model_validate(raw)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("incident", "incident_id"), "code_incident:" + "0" * 32),
        (("relations", 0, "source_incident_id"), "code_incident:" + "0" * 32),
        (("relations", 0, "target_coordinate_id"), "code_incident_coordinate:" + "0" * 32),
        (("relations", 0, "relation_id"), "code_incident_relation:" + "0" * 32),
        (("evidence", 0, "immutable_uri"), "https://attacker.example/evidence"),
        (("evidence", 1, "source_snapshot_digest"), "sha256:" + "0" * 64),
        (("omissions", 0, "evidence_ref"), "code_incident_evidence:" + "0" * 32),
    ],
)
def test_serialized_projection_rejects_forged_ids_and_crosslinks(path: tuple[Any, ...], value: str) -> None:
    projection = project_public_incident_to_code(_envelope(_fixture()))
    raw = projection.model_dump(mode="json")
    target: Any = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="identity|resolve|cross-wired|source spans"):
        IncidentToCodeProjectionV1Alpha1.model_validate(raw)


def test_serialized_projection_round_trip_revalidates_exact_graph() -> None:
    envelope = _envelope(_fixture())
    projection = project_public_incident_to_code(envelope)
    assert IncidentToCodeProjectionV1Alpha1.model_validate(projection.model_dump()) == projection
    assert validate_incident_projection_against_source(projection, envelope) == projection


def test_cross_consistent_snapshot_forgery_requires_paired_source_revalidation() -> None:
    envelope = _envelope(_fixture())
    raw = project_public_incident_to_code(envelope).model_dump(mode="json")
    forged_digest = "sha256:" + "1" * 64
    forged_ref = "source_snapshot:" + "1" * 32
    raw["source_snapshot_digest"] = forged_digest
    raw["source_snapshot_ref"] = forged_ref
    for evidence in raw["evidence"]:
        evidence["source_snapshot_digest"] = forged_digest
        evidence["source_snapshot_ref"] = forged_ref

    standalone = IncidentToCodeProjectionV1Alpha1.model_validate(raw)
    assert standalone.self_authenticates_source_snapshot is False
    assert standalone.source_snapshot_revalidation_required is True
    with pytest.raises(IncidentProjectionError, match="does not match the canonical source"):
        validate_incident_projection_against_source(standalone, envelope)


def test_serialized_projection_rejects_forged_acquisition_receipt() -> None:
    raw = project_public_incident_to_code(_envelope(_fixture())).model_dump(mode="json")
    raw["acquisition_receipt_ref"] = "acquisition_receipt:forged"
    raw["acquisition_receipt_digest"] = "sha256:" + "1" * 64
    with pytest.raises(ValueError, match="frozen prepared fixture"):
        IncidentToCodeProjectionV1Alpha1.model_validate(raw)


def test_serialized_projection_rejects_duplicate_or_unbounded_graph_material() -> None:
    projection = project_public_incident_to_code(_envelope(_fixture()))
    duplicate = projection.model_dump(mode="json")
    duplicate["evidence"][1] = dict(duplicate["evidence"][0])
    with pytest.raises(ValueError, match="unique"):
        IncidentToCodeProjectionV1Alpha1.model_validate(duplicate)

    missing = projection.model_dump(mode="json")
    missing["evidence"].pop()
    with pytest.raises(ValueError, match="at least 3 items"):
        IncidentToCodeProjectionV1Alpha1.model_validate(missing)


def test_live_acquisition_is_not_accepted_by_prepared_incident_host_seam() -> None:
    with pytest.raises(ValueError, match="only the prepared fixture"):
        _envelope(_fixture(), mode=SourceAcquisitionMode.LIVE)


def test_bundled_fixture_is_package_accessible_and_pins_verified_material() -> None:
    resource = resources.files("core.engine.code_intelligence").joinpath(TBTC_INCIDENT_FIXTURE_RESOURCE)
    payload = json.loads(resource.read_text(encoding="utf-8"))

    assert payload == _fixture()
    assert payload["report"]["content_sha256"] == (
        "sha256:9f105c2a56cae01b16e27625dee1b6c2d32a5f9dae71225bb0c0fb4a659a6a72"
    )
    assert payload["report"]["byte_count"] == 20_336
    assert payload["report"]["raw_url"].startswith("https://raw.githubusercontent.com/keep-network/tbtc-website/")
    assert _positive(payload)["code_coordinate"]["file_sha256"] == (
        "sha256:22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330"
    )
    assert _positive(payload)["code_coordinate"]["byte_count"] == 17_849
    assert [item["spdx_id"] for item in payload["licenses"]] == ["MIT", "MIT"]
    assert [item["git_blob_sha"] for item in payload["licenses"]] == [
        "4ed19fdb338ca18942ed904d47e5c377103e45eb",
        "80a1ed24975b0263f29157a7bc788d9e30ab2adf",
    ]


def test_artifact_verifier_matches_independent_git_and_sha_tools() -> None:
    facts = artifact_facts(b"fixture\n")
    assert facts == {
        "byte_count": 8,
        "raw_sha256": "sha256:e80b71cd14d3cbd65f4173abcbfcf01a545dbca32a72d575108b553a648cc96f",
        "git_blob_sha": "ee8c1ee49b4799bbd170233915a897c19e3b55e1",
    }
    assert (
        verify_artifact_bytes(
            payload=b"fixture\n",
            expected={
                "byte_count": 8,
                "content_sha256": facts["raw_sha256"],
                "git_blob_sha": facts["git_blob_sha"],
            },
            digest_field="content_sha256",
        )
        == facts
    )
    with pytest.raises(ValueError, match="immutable artifact mismatch"):
        verify_artifact_bytes(
            payload=b"fixture!\n",
            expected={
                "byte_count": 8,
                "content_sha256": facts["raw_sha256"],
                "git_blob_sha": facts["git_blob_sha"],
            },
            digest_field="content_sha256",
        )


def _forbid_network_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_fetch(url: str) -> bytes:
        raise AssertionError(f"unexpected network read attempted for {url!r}")

    monkeypatch.setattr(verify_fixture_module, "_fetch_exact_raw_url", _unexpected_fetch)


def test_verify_fixture_cli_help_exits_zero_without_network(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _forbid_network_reads(monkeypatch)

    with pytest.raises(SystemExit) as excinfo:
        verify_fixture_module.main(["--help"])

    assert excinfo.value.code == 0
    assert "--allow-network" in capsys.readouterr().out


def test_verify_fixture_cli_default_invocation_is_nonzero_without_network(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _forbid_network_reads(monkeypatch)

    exit_code = verify_fixture_module.main([])

    assert exit_code != 0
    assert "--allow-network" in capsys.readouterr().err


def test_verify_fixture_cli_allow_network_flag_invokes_verifier_and_emits_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deterministic_result = {"report": {"byte_count": 8, "raw_sha256": "sha256:" + "0" * 64}}
    monkeypatch.setattr(verify_fixture_module, "verify_bundled_fixture", lambda: deterministic_result)

    exit_code = verify_fixture_module.main(["--allow-network"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == deterministic_result


def test_verify_fixture_cli_unknown_argument_fails_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_network_reads(monkeypatch)

    with pytest.raises(SystemExit) as excinfo:
        verify_fixture_module.main(["--bogus"])

    assert excinfo.value.code != 0


def test_span_verifier_uses_one_based_inclusive_lines_without_terminal_newline() -> None:
    expected = "beta\ngamma"
    digest = f"sha256:{hashlib.sha256(expected.encode()).hexdigest()}"
    assert (
        verify_span(
            payload=b"alpha\nbeta\ngamma\ndelta\n",
            line_start=2,
            line_end=3,
            expected_excerpt=expected,
            expected_digest=digest,
        )
        == digest
    )
    with pytest.raises(ValueError, match="frozen excerpt"):
        verify_span(
            payload=b"alpha\nbeta!\ngamma\ndelta\n",
            line_start=2,
            line_end=3,
            expected_excerpt=expected,
            expected_digest=digest,
        )

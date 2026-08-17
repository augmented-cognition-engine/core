from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo
from pydantic import ValidationError

from core.engine.code_intelligence.contracts import (
    CONTEXT_MANIFEST_MAX_OMISSION_CHARS,
    CONTEXT_MANIFEST_MAX_OMISSIONS,
    CONTEXT_MANIFEST_MAX_OMISSIONS_TOTAL_CHARS,
    LENS_MAX_OMISSION_CHARS,
    LENS_MAX_OMISSIONS,
    LENS_MAX_OMISSIONS_TOTAL_CHARS,
    AtriumCodeLensV1Alpha1,
    BoundedCodeHandoffV1Alpha1,
    CodeArtifactKind,
    CodeContextBlockV1Alpha1,
    CodeContextManifestV1Alpha1,
    CodeIntelligenceJourneyV1Alpha1,
    CodingAgentReturnV1Alpha1,
    ConfidenceBand,
    DerivationKind,
    stable_digest,
)
from core.engine.code_intelligence.handoff import validate_coding_agent_return
from core.engine.code_intelligence.journey import CodeIntelligenceJourney

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "docs" / "design").mkdir(parents=True)
    (root / "pkg" / "service.py").write_text(
        "def used(value: int) -> int:\n    return value + 1\n\ndef maybe_disconnected() -> None:\n    pass\n",
        encoding="utf-8",
    )
    (root / "pkg" / "consumer.py").write_text(
        "from pkg.service import used\n\ndef call() -> int:\n    return used(1)\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_service.py").write_text(
        "from pkg.service import used\n\ndef test_used():\n    assert used(1) == 2\n",
        encoding="utf-8",
    )
    (root / "docs" / "design" / "service-choice.md").write_text(
        "# Service choice\n\nThe used function is kept small so callers own policy.\n",
        encoding="utf-8",
    )
    repo = Repo.init(root)
    repo.index.add(["pkg/service.py", "pkg/consumer.py", "tests/test_service.py", "docs/design/service-choice.md"])
    repo.index.commit("initial service decision")
    return root


def test_journey_connects_impact_tests_rationale_and_bounded_handoff(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    result = CodeIntelligenceJourney(root, max_context_files=3, max_context_bytes=4_000).run(
        query="Why does used exist and what breaks if it changes?",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )

    assert result.lens.index.analysis_profile == "python-local-static-v1"
    assert result.lens.index.dirty is False
    assert "pkg/consumer.py" in result.lens.impact.direct_dependents
    assert "tests/test_service.py" in result.lens.impact.affected_tests
    assert any(node.kind is CodeArtifactKind.ADR for node in result.lens.nodes)
    assert any(node.kind is CodeArtifactKind.CONTRIBUTOR for node in result.lens.nodes)
    assert not any(node.kind is CodeArtifactKind.OWNERSHIP for node in result.lens.nodes)
    assert result.lens.impact.confidence is ConfidenceBand.SUPPORTED
    assert len(result.handoff.blocks) <= 3
    assert result.handoff.manifest.total_bytes <= 4_000
    assert result.handoff.receipt.grants_source_authority is False
    assert result.handoff.receipt.grants_reasoning_authority is False
    assert result.handoff.receipt.grants_delivery_authority is False
    assert result.handoff.receipt.grants_effect_authority is False
    assert result.handoff.receipt.execution_authority_revalidation_required is True


def test_handoff_contains_exact_named_implementation_span_under_tight_budget(tmp_path: Path) -> None:
    result = CodeIntelligenceJourney(
        _repository(tmp_path),
        max_context_files=1,
        max_context_bytes=64,
    ).run(
        query="Change the named used implementation",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )

    block = result.handoff.blocks[0]
    receipt = result.handoff.manifest.blocks[0]
    assert block.path == "pkg/service.py"
    assert block.symbol == "used"
    assert block.reason == "named target symbol:used"
    assert block.line_start == 1
    assert block.line_end == 2
    assert block.symbol_line_start == 1
    assert block.symbol_line_end == 2
    assert block.body == "def used(value: int) -> int:\n    return value + 1"
    assert receipt.symbol == "used"
    assert receipt.symbol_line_start == 1
    assert receipt.symbol_line_end == 2
    assert receipt.block_id == block.block_id
    assert "symbol_context_reduced:1" in result.handoff.manifest.omissions

    partial = block.model_dump()
    partial["symbol_line_end"] = None
    with pytest.raises(ValidationError, match="must be present together"):
        CodeContextBlockV1Alpha1.model_validate(partial)

    outside = block.model_dump()
    outside["symbol_line_end"] = block.line_end + 1
    with pytest.raises(ValidationError, match="falls outside"):
        CodeContextBlockV1Alpha1.model_validate(outside)

    reversed_span = block.model_dump()
    reversed_span["symbol_line_start"] = 2
    reversed_span["symbol_line_end"] = 1
    with pytest.raises(ValidationError, match="reversed"):
        CodeContextBlockV1Alpha1.model_validate(reversed_span)


def test_journey_connects_declared_owners_with_exact_evidence_without_granting_authority(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / ".github").mkdir()
    raw_declaration = "/pkg/service.py @ace/service-team service-owner@example.com"
    (root / ".github" / "CODEOWNERS").write_text(
        "# review routing\n" + raw_declaration + "\n",
        encoding="utf-8",
    )
    repo = Repo(root)
    repo.index.add([".github/CODEOWNERS"])
    repo.index.commit("declare service reviewers")

    result = CodeIntelligenceJourney(root).run(query="change used", target_path="pkg/service.py")

    declared_nodes = [
        node
        for node in result.lens.nodes
        if node.kind is CodeArtifactKind.OWNERSHIP and node.derivation is DerivationKind.DECLARED
    ]
    assert {node.label for node in declared_nodes} == {"@ace/service-team", "service-owner@example.com"}
    assert all(node.confidence is ConfidenceBand.OBSERVED for node in declared_nodes)
    assert all(
        "grants no source, change, approval, delivery, or effect authority" in (node.detail or "")
        for node in declared_nodes
    )

    declared_edges = [edge for edge in result.lens.edges if edge.relation == "declared_review_responsibility"]
    assert len(declared_edges) == 2
    assert all(edge.derivation is DerivationKind.DECLARED for edge in declared_edges)
    assert all(edge.confidence is ConfidenceBand.OBSERVED for edge in declared_edges)
    declaration_anchor = next(
        anchor for anchor in result.lens.evidence if anchor.path == ".github/CODEOWNERS" and anchor.line_start == 2
    )
    assert declaration_anchor.line_end == 2
    assert declaration_anchor.derivation is DerivationKind.DECLARED
    assert all(edge.evidence_refs == (declaration_anchor.anchor_id,) for edge in declared_edges)
    assert any(edge.relation == "historical_contributor" for edge in result.lens.edges)
    assert not any("Declared path ownership unavailable" in omission for omission in result.lens.omissions)
    assert result.lens.source_authority is False
    assert result.lens.reasoning_authority is False
    assert result.lens.delivery_authority is False
    assert result.lens.effect_authority is False


def test_journey_reports_missing_declaration_without_promoting_contributors(tmp_path: Path) -> None:
    result = CodeIntelligenceJourney(_repository(tmp_path)).run(
        query="change used",
        target_path="pkg/service.py",
    )

    assert not any(
        node.kind is CodeArtifactKind.OWNERSHIP and node.derivation is DerivationKind.DECLARED
        for node in result.lens.nodes
    )
    assert not any(edge.relation == "declared_review_responsibility" for edge in result.lens.edges)
    historical_edges = [edge for edge in result.lens.edges if edge.relation == "historical_contributor"]
    assert historical_edges
    assert all(edge.derivation is DerivationKind.GIT for edge in historical_edges)
    historical_node_ids = {edge.source for edge in historical_edges}
    assert all(
        node.kind is CodeArtifactKind.CONTRIBUTOR for node in result.lens.nodes if node.node_id in historical_node_ids
    )
    omission = next(
        omission for omission in result.lens.omissions if omission.startswith("Declared path ownership unavailable")
    )
    assert "No tracked regular path-owner declaration exists" in omission
    assert "Git contributors do not establish target-path ownership" in omission


def test_journey_distinguishes_unassigned_target_in_existing_declaration(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "CODEOWNERS").write_text("/docs/** @ace/docs\n", encoding="utf-8")
    repo = Repo(root)
    repo.index.add(["CODEOWNERS"])
    repo.index.commit("declare docs reviewers")

    result = CodeIntelligenceJourney(root).run(query="change used", target_path="pkg/service.py")

    assert not any(edge.relation == "declared_review_responsibility" for edge in result.lens.edges)
    omission = next(
        omission for omission in result.lens.omissions if omission.startswith("Declared path ownership unassigned")
    )
    assert "CODEOWNERS contains no supported rule matching pkg/service.py" in omission
    assert "no owner is inferred" in omission


def test_disconnected_symbols_are_candidates_not_unreachable_claims(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "standalone.py").write_text("def plugin_entrypoint():\n    return 1\n", encoding="utf-8")
    repo = Repo(root)
    repo.index.add(["standalone.py"])
    repo.index.commit("add possible plugin entrypoint")

    result = CodeIntelligenceJourney(root).run(query="change used", target_path="pkg/service.py")

    candidate = next(item for item in result.lens.disconnected_symbols if item.symbol == "plugin_entrypoint")
    assert candidate.confidence is ConfidenceBand.INFERRED
    assert "may still be a CLI, plugin" in candidate.reason
    assert "safe deletion" in " ".join(result.lens.omissions)


def test_journey_rejects_path_escape_and_non_python_target(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    journey = CodeIntelligenceJourney(root)
    with pytest.raises(ValueError, match="escapes repository"):
        journey.run(query="bad", target_path="../outside.py")

    with pytest.raises(ValueError, match="canonical repository-relative spelling"):
        journey.run(query="bad", target_path="pkg/../pkg/service.py")

    (root / "pkg" / "service-link.py").symlink_to("service.py")
    with pytest.raises(ValueError, match="canonical repository-relative spelling"):
        journey.run(query="bad", target_path="pkg/service-link.py")

    (root / "frontend.ts").write_text("export const value = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="only Python"):
        journey.run(query="bad", target_path="frontend.ts")


def test_coding_agent_return_closes_exact_handoff_chain(tmp_path: Path) -> None:
    result = CodeIntelligenceJourney(_repository(tmp_path), max_context_files=3).run(
        query="What breaks if used changes?",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )
    returned = CodingAgentReturnV1Alpha1(
        receiver_ref=result.handoff.receipt.receiver_ref,
        handoff_id=result.handoff.receipt.handoff_id,
        index_id=result.lens.index.index_id,
        lens_id=result.lens.lens_id,
        manifest_id=result.handoff.manifest.manifest_id,
        disposition="no_change_recommended",
        summary="The context supports impact analysis but does not identify a requested behavior change.",
        consumed_block_ids=tuple(block.block_id for block in result.handoff.blocks),
        verification_refs=("pytest:tests/test_service.py",),
        uncertainties=("Runtime plugin registration was not observed.",),
        submitted_at=datetime.now(timezone.utc),
    )

    receipt = validate_coding_agent_return(result.handoff, returned)

    assert receipt.chain_validated is True
    assert receipt.return_id == returned.return_id
    assert receipt.disposition == "no_change_recommended"
    assert receipt.changed_paths == ()
    assert receipt.warnings == returned.uncertainties
    assert receipt.execution_authority_revalidation_required is True


def test_coding_agent_return_rejects_unknown_context_and_out_of_bounds_change(tmp_path: Path) -> None:
    result = CodeIntelligenceJourney(_repository(tmp_path), max_context_files=3).run(
        query="Change used",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )
    common = {
        "receiver_ref": result.handoff.receipt.receiver_ref,
        "handoff_id": result.handoff.receipt.handoff_id,
        "index_id": result.lens.index.index_id,
        "lens_id": result.lens.lens_id,
        "manifest_id": result.handoff.manifest.manifest_id,
        "summary": "Bounded test return.",
        "submitted_at": datetime.now(timezone.utc),
    }
    unknown = CodingAgentReturnV1Alpha1(
        **common,
        disposition="no_change_recommended",
        consumed_block_ids=("code_context_block:unknown",),
    )
    with pytest.raises(ValueError, match="unknown context blocks"):
        validate_coding_agent_return(result.handoff, unknown)

    outside = CodingAgentReturnV1Alpha1(
        **common,
        disposition="change_proposed",
        consumed_block_ids=(result.handoff.blocks[0].block_id,),
        changed_paths=("outside.py",),
    )
    with pytest.raises(ValueError, match="outside the bounded handoff"):
        validate_coding_agent_return(result.handoff, outside)


def _journey(tmp_path: Path):
    return CodeIntelligenceJourney(_repository(tmp_path), max_context_files=3).run(
        query="What breaks if used changes?",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )


def test_valid_journey_closes_every_cross_contract_identity(tmp_path: Path) -> None:
    result = _journey(tmp_path)
    payload = result.model_dump(mode="json")

    assert CodeIntelligenceJourneyV1Alpha1.model_validate(payload) == result
    assert result.handoff.manifest.index_id == result.lens.index.index_id
    assert result.handoff.receipt.index_id == result.lens.index.index_id
    assert result.handoff.manifest.lens_id == result.lens.lens_id == result.handoff.receipt.lens_id
    assert result.handoff.receipt.requested_change == result.lens.query
    assert result.lens.impact.target_path == result.lens.target_path
    included = result.handoff.receipt.included_paths
    assert included == tuple(item.path for item in result.handoff.manifest.blocks)
    assert len(set(included)) == len(included)

    anchors = {anchor.anchor_id for anchor in result.lens.evidence}
    assert all(set(node.evidence_refs) <= anchors for node in result.lens.nodes)
    assert all(item.evidence_ref in anchors for item in result.lens.disconnected_symbols)
    assert all(block.evidence_ref in anchors for block in result.handoff.blocks)
    node_ids = {node.node_id for node in result.lens.nodes}
    assert all(edge.source in node_ids and edge.target in node_ids for edge in result.lens.edges)

    historical = [edge for edge in result.lens.edges if edge.relation == "historical_contributor"]
    assert historical and all(edge.derivation is DerivationKind.GIT for edge in historical)
    commit_refs = [ref for edge in historical for ref in edge.evidence_refs]
    assert commit_refs and all(len(ref) == 44 and ref.startswith("git:") for ref in commit_refs)
    assert all(ref not in anchors for ref in commit_refs)


def test_journey_rejects_recomputed_extra_included_path(tmp_path: Path) -> None:
    payload = _journey(tmp_path).model_dump(mode="json")
    payload["handoff"]["receipt"]["included_paths"].append("pkg/consumer.py")

    with pytest.raises(ValidationError, match="included paths differ from the exact ordered manifest"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(payload)


def test_journey_rejects_crossed_lens_and_index_identities(tmp_path: Path) -> None:
    result = _journey(tmp_path)
    crossed = result.model_dump(mode="json")
    crossed["handoff"]["manifest"]["lens_id"] = result.lens.index.index_id
    crossed["handoff"]["receipt"]["lens_id"] = result.lens.index.index_id
    # Recompute the derived manifest identity so only the crossed lens remains.
    crossed["handoff"]["receipt"]["manifest_id"] = CodeContextManifestV1Alpha1.model_validate(
        crossed["handoff"]["manifest"]
    ).manifest_id
    with pytest.raises(ValidationError, match="names a different lens"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(crossed)

    swapped = result.model_dump(mode="json")
    swapped["handoff"]["receipt"]["index_id"] = result.lens.lens_id
    with pytest.raises(ValidationError, match="different index than the manifest"):
        BoundedCodeHandoffV1Alpha1.model_validate(swapped["handoff"])


def test_journey_rejects_unrelated_impact_target_and_requested_change(tmp_path: Path) -> None:
    result = _journey(tmp_path)
    impact = result.model_dump(mode="json")
    impact["lens"]["impact"]["target_path"] = "pkg/consumer.py"
    with pytest.raises(ValidationError, match="impact describes a different target path"):
        AtriumCodeLensV1Alpha1.model_validate(impact["lens"])

    request = result.model_dump(mode="json")
    request["handoff"]["receipt"]["requested_change"] = "Delete every disconnected symbol."
    with pytest.raises(ValidationError, match="requests a change the lens did not examine"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(request)


def test_journey_rejects_a_claim_whose_anchor_was_removed(tmp_path: Path) -> None:
    result = _journey(tmp_path)
    cited = next(node.evidence_refs[0] for node in result.lens.nodes if node.evidence_refs)
    lens = result.model_dump(mode="json")["lens"]
    kept = [anchor for anchor in lens["evidence"] if anchor["path"] != result.lens.target_path]
    lens["evidence"] = kept
    assert cited not in {item["path"] for item in kept}

    with pytest.raises(ValidationError, match="does not resolve to an exact source anchor"):
        AtriumCodeLensV1Alpha1.model_validate(lens)


def test_journey_never_reads_or_projects_an_untracked_external_symlink(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    outside = tmp_path / "outside_secret.py"
    outside.write_text("def outside_secret():\n    return 1\n", encoding="utf-8")
    (root / "external.py").symlink_to(outside)
    opened: list[str] = []
    real_open = os.open

    def recording_open(path, *args, **kwargs):
        opened.append(str(path))
        return real_open(path, *args, **kwargs)

    with patch.object(os, "open", recording_open):
        result = CodeIntelligenceJourney(root).run(query="change used", target_path="pkg/service.py")

    assert str(outside) not in opened
    assert not any(node.symbol == "outside_secret" for node in result.lens.nodes)
    assert not any(item.symbol == "outside_secret" for item in result.lens.disconnected_symbols)
    assert not any(block.path == "external.py" for block in result.handoff.blocks)
    assert result.lens.index.dirty is True
    assert any("Untracked symlinks contribute only their link target text" in item for item in result.lens.omissions)


def test_journey_never_reads_an_external_test_symlink(tmp_path: Path) -> None:
    """A ``test*.py`` symlink into another tree must be skipped by containment, not read.

    The outside file is written with content that would match the lexical test scan if
    it were ever read, so the assertion proves exclusion rather than accidental non-match.
    A normal, non-symlinked test file must still be found.
    """
    root = _repository(tmp_path)
    outside = tmp_path / "outside_test.py"
    outside.write_text(
        "from pkg.service import used\n\ndef test_used_from_outside():\n    assert used(1) == -1\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_outside_link.py").symlink_to(outside)
    real_read_text = Path.read_text
    read_paths: list[Path] = []

    def recording_read_text(self: Path, *args: object, **kwargs: object) -> str:
        read_paths.append(self)
        return real_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", recording_read_text):
        result = CodeIntelligenceJourney(root).run(query="change used", target_path="pkg/service.py")

    assert outside.resolve() not in {path.resolve() for path in read_paths}
    assert "tests/test_outside_link.py" not in result.lens.impact.affected_tests
    assert not any(node.path == "tests/test_outside_link.py" for node in result.lens.nodes)
    assert not any(item.path == "tests/test_outside_link.py" for item in result.lens.evidence)
    assert "tests/test_service.py" in result.lens.impact.affected_tests
    assert any(
        "Symlinked test candidates were skipped" in item and item.endswith("1 candidate(s).")
        for item in result.lens.omissions
    )


def test_journey_never_reads_an_external_decision_document_symlink(tmp_path: Path) -> None:
    """A decision-document symlink into another tree must be skipped by containment.

    The outside file mentions the target's own stem so it would lexically match the
    decision scan if it were ever read, proving exclusion rather than accidental
    non-match. The repository's own, non-symlinked decision document must still connect.
    """
    root = _repository(tmp_path)
    outside = tmp_path / "outside-decision.md"
    outside.write_text(
        "# Outside decision\n\nThis service rationale must never be scanned.\n",
        encoding="utf-8",
    )
    (root / "docs" / "design" / "outside-link.md").symlink_to(outside)
    real_read_text = Path.read_text
    read_paths: list[Path] = []

    def recording_read_text(self: Path, *args: object, **kwargs: object) -> str:
        read_paths.append(self)
        return real_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", recording_read_text):
        result = CodeIntelligenceJourney(root).run(query="change used", target_path="pkg/service.py")

    assert outside.resolve() not in {path.resolve() for path in read_paths}
    assert not any(node.path == "docs/design/outside-link.md" for node in result.lens.nodes)
    assert not any(item.path == "docs/design/outside-link.md" for item in result.lens.evidence)
    assert any(node.path == "docs/design/service-choice.md" for node in result.lens.nodes)
    assert any(
        "Symlinked decision-document candidates were skipped" in item and item.endswith("1 candidate(s).")
        for item in result.lens.omissions
    )


def test_large_untracked_symlink_set_yields_bounded_deterministic_lens_omissions(tmp_path: Path) -> None:
    """A working tree with many untracked symlinks must not blow up the lens.

    A planner that joined every untracked symlink path into one omission
    string would grow that entry's length in proportion to the working
    tree's untracked symlink count. Aggregating by deterministic count keeps
    the lens (and its serialized form) bounded regardless of how many
    untracked symlinks exist. Symlinks are given no file extension so the
    Tree-sitter scanner's extension-based file discovery never picks them up
    as source files; only the untracked-symlink disclosure path is exercised.
    """
    root = _repository(tmp_path)
    links_dir = root / "untracked_links"
    links_dir.mkdir()
    symlink_count = 1_000
    for index in range(symlink_count):
        (links_dir / f"link_{index:04d}").symlink_to("nonexistent-target")

    result = CodeIntelligenceJourney(root).run(query="change used", target_path="pkg/service.py")

    assert result.lens.index.dirty is True
    symlink_omissions = [
        item for item in result.lens.omissions if item.startswith("Untracked symlinks contribute only")
    ]
    assert len(symlink_omissions) == 1
    assert symlink_omissions[0].endswith(f"{symlink_count} symlink(s).")
    assert "link_" not in symlink_omissions[0]

    assert len(result.lens.omissions) <= LENS_MAX_OMISSIONS
    assert all(len(item) <= LENS_MAX_OMISSION_CHARS for item in result.lens.omissions)
    assert sum(len(item) for item in result.lens.omissions) <= LENS_MAX_OMISSIONS_TOTAL_CHARS

    payload = result.model_dump(mode="json")
    assert CodeIntelligenceJourneyV1Alpha1.model_validate(payload) == result
    assert len(json.dumps(payload["lens"]["omissions"])) < 2_000


def test_lens_omissions_reject_tampered_oversized_deserialization(tmp_path: Path) -> None:
    """The lens omissions bound is a Pydantic ``model_validator``, so it must reject a

    tampered/deserialized payload, not just the output the journey itself happens to
    produce, mirroring ``test_context_manifest_rejects_omissions_exceeding_contract_bounds``
    for ``AtriumCodeLensV1Alpha1``.
    """
    result = _journey(tmp_path)
    base = result.lens.model_dump(mode="json")

    too_many_items = dict(base, omissions=tuple(f"reason_{index}" for index in range(LENS_MAX_OMISSIONS + 1)))
    with pytest.raises(ValidationError, match=f"exceed {LENS_MAX_OMISSIONS} items"):
        AtriumCodeLensV1Alpha1.model_validate(too_many_items)

    too_long_item = dict(base, omissions=("x" * (LENS_MAX_OMISSION_CHARS + 1),))
    with pytest.raises(ValidationError, match=f"1..{LENS_MAX_OMISSION_CHARS} characters"):
        AtriumCodeLensV1Alpha1.model_validate(too_long_item)

    empty_item = dict(base, omissions=("",))
    with pytest.raises(ValidationError, match=f"1..{LENS_MAX_OMISSION_CHARS} characters"):
        AtriumCodeLensV1Alpha1.model_validate(empty_item)

    duplicate_items = dict(base, omissions=("same_reason", "same_reason"))
    with pytest.raises(ValidationError, match="duplicate entry"):
        AtriumCodeLensV1Alpha1.model_validate(duplicate_items)

    per_item_chars = LENS_MAX_OMISSIONS_TOTAL_CHARS // LENS_MAX_OMISSIONS + 10
    too_much_total = dict(
        base,
        omissions=tuple(f"reason_{index}:" + "x" * per_item_chars for index in range(LENS_MAX_OMISSIONS)),
    )
    with pytest.raises(ValidationError, match=f"total characters exceed {LENS_MAX_OMISSIONS_TOTAL_CHARS}"):
        AtriumCodeLensV1Alpha1.model_validate(too_much_total)

    # The same tampered lens embedded inside a full journey payload must be
    # rejected at the outer contract too, not only when validated standalone.
    journey_payload = result.model_dump(mode="json")
    journey_payload["lens"]["omissions"] = too_many_items["omissions"]
    with pytest.raises(ValidationError, match=f"exceed {LENS_MAX_OMISSIONS} items"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(journey_payload)


def test_context_block_span_must_equal_its_exact_body_line_count(tmp_path: Path) -> None:
    block = _journey(tmp_path).handoff.blocks[0]

    inflated = block.model_dump()
    inflated["line_end"] = block.line_end + 5
    inflated.update({"symbol": None, "symbol_line_start": None, "symbol_line_end": None, "symbol_body_digest": None})
    with pytest.raises(ValidationError, match="inclusive line span differs from the exact body line count"):
        CodeContextBlockV1Alpha1.model_validate(inflated)

    def spanned(body: str, line_start: int, line_end: int) -> dict:
        payload = block.model_dump()
        payload.update(
            {
                "body": body,
                "body_digest": stable_digest(body),
                "byte_count": len(body.encode()),
                "line_start": line_start,
                "line_end": line_end,
                "symbol": None,
                "symbol_line_start": None,
                "symbol_line_end": None,
                "symbol_body_digest": None,
            }
        )
        return payload

    # An empty body is exactly one empty line, never a zero-line span.
    assert CodeContextBlockV1Alpha1.model_validate(spanned("", 1, 1)).byte_count == 0
    with pytest.raises(ValidationError, match="inclusive line span"):
        CodeContextBlockV1Alpha1.model_validate(spanned("", 1, 2))

    # A trailing newline opens a final empty line, and that line is counted.
    assert CodeContextBlockV1Alpha1.model_validate(spanned("a\n", 1, 2)).line_end == 2
    with pytest.raises(ValidationError, match="inclusive line span"):
        CodeContextBlockV1Alpha1.model_validate(spanned("a\n", 1, 1))


def test_scanner_stats_rejects_missing_extra_negative_and_boolean_values(tmp_path: Path) -> None:
    base = _journey(tmp_path).model_dump(mode="json")
    assert set(base["scanner_stats"]) == {"files", "functions", "classes", "imports"}

    missing = copy.deepcopy(base)
    del missing["scanner_stats"]["imports"]
    with pytest.raises(ValidationError, match="exactly the keys files, functions, classes, imports"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(missing)

    extra = copy.deepcopy(base)
    extra["scanner_stats"]["symbols"] = 1
    with pytest.raises(ValidationError, match="exactly the keys files, functions, classes, imports"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(extra)

    negative = copy.deepcopy(base)
    negative["scanner_stats"]["files"] = -1
    with pytest.raises(ValidationError, match="nonnegative int"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(negative)

    relabeled = copy.deepcopy(base)
    relabeled["scanner_stats"]["functions"] = 999
    # A merely coherent-looking (nonnegative int) relabel is legal at this
    # standalone-model layer; only the paired living-run replay binds these
    # counts to the full snapshot they must describe.
    assert CodeIntelligenceJourneyV1Alpha1.model_validate(relabeled).scanner_stats["functions"] == 999

    boolean = copy.deepcopy(base)
    boolean["scanner_stats"]["classes"] = True
    with pytest.raises(ValidationError, match="nonnegative int"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(boolean)

    negative_boolean = copy.deepcopy(base)
    negative_boolean["scanner_stats"]["classes"] = False
    with pytest.raises(ValidationError, match="nonnegative int"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(negative_boolean)


def test_scanner_stats_rejects_string_and_float_values_before_pydantic_coerces_them(tmp_path: Path) -> None:
    """Numeric strings and integral floats must fail closed, not silently coerce.

    Pydantic's default ``int`` field coercion would otherwise accept ``"3"``
    or ``3.0`` and narrow them into a plain ``int`` before any validator sees
    the original type, letting a raw scanner stat of the wrong shape through
    unnoticed. The before-validator must reject these by exact ``type(value)
    is int``, ahead of that coercion.
    """
    base = _journey(tmp_path).model_dump(mode="json")

    numeric_string = copy.deepcopy(base)
    numeric_string["scanner_stats"]["files"] = "3"
    with pytest.raises(ValidationError, match="nonnegative int"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(numeric_string)

    integral_float = copy.deepcopy(base)
    integral_float["scanner_stats"]["functions"] = 3.0
    with pytest.raises(ValidationError, match="nonnegative int"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(integral_float)

    negative_string = copy.deepcopy(base)
    negative_string["scanner_stats"]["classes"] = "-1"
    with pytest.raises(ValidationError, match="nonnegative int"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(negative_string)

    negative_float = copy.deepcopy(base)
    negative_float["scanner_stats"]["imports"] = -1.0
    with pytest.raises(ValidationError, match="nonnegative int"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(negative_float)


def test_journey_bounds_an_empty_python_file_to_one_line(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "pkg" / "empty.py").write_text("", encoding="utf-8")
    (root / "pkg" / "consumer.py").write_text(
        "from pkg.service import used\nfrom pkg.empty import nothing\n\ndef call() -> int:\n    return used(1)\n",
        encoding="utf-8",
    )
    repo = Repo(root)
    repo.index.add(["pkg/empty.py", "pkg/consumer.py"])
    repo.index.commit("add an empty module")

    result = CodeIntelligenceJourney(root, max_context_files=8).run(
        query="What breaks if used changes?",
        target_path="pkg/service.py",
    )

    empty_blocks = [block for block in result.handoff.blocks if block.path == "pkg/empty.py"]
    assert all(block.line_start == block.line_end == 1 and block.body == "" for block in empty_blocks)


def test_multi_block_journey_regression_every_block_resolves_its_exact_anchor(tmp_path: Path) -> None:
    """Every block/anchor pair must match on path, span, and digest.

    ``pkg/consumer.py`` is long enough that the short graph-connection anchor
    minted while walking the dependency graph (span 1..40) is a different span
    than the block's own default context body (span 1..min(len,80)). A planner
    that reused any same-path anchor regardless of span would silently attach
    the wrong evidence to this block; this fixture exercises exactly that gap.
    """
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pkg" / "service.py").write_text(
        "def used(value: int) -> int:\n    return value + 1\n\ndef maybe_disconnected() -> None:\n    pass\n",
        encoding="utf-8",
    )
    consumer_lines = ["from pkg.service import used", "", "def call() -> int:", "    return used(1)", ""]
    consumer_lines += [f"# padding line {index}" for index in range(60)]
    (root / "pkg" / "consumer.py").write_text("\n".join(consumer_lines) + "\n", encoding="utf-8")
    (root / "tests" / "test_service.py").write_text(
        "from pkg.service import used\n\ndef test_used():\n    assert used(1) == 2\n",
        encoding="utf-8",
    )
    repo = Repo.init(root)
    repo.index.add(["pkg/service.py", "pkg/consumer.py", "tests/test_service.py"])
    repo.index.commit("multi-block regression fixture")

    result = CodeIntelligenceJourney(root, max_context_files=8, max_context_bytes=24_000).run(
        query="Change the named used implementation",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )

    assert len(result.handoff.blocks) >= 3
    assert any(block.symbol is not None for block in result.handoff.blocks)
    assert any(block.symbol is None for block in result.handoff.blocks)
    anchors_by_id = {anchor.anchor_id: anchor for anchor in result.lens.evidence}
    for block in result.handoff.blocks:
        anchor = anchors_by_id[block.evidence_ref]
        assert anchor.path == block.path
        if block.symbol is None:
            assert (anchor.line_start, anchor.line_end, anchor.content_digest) == (
                block.line_start,
                block.line_end,
                block.body_digest,
            )
        else:
            assert (anchor.line_start, anchor.line_end, anchor.content_digest) == (
                block.symbol_line_start,
                block.symbol_line_end,
                block.symbol_body_digest,
            )

    payload = result.model_dump(mode="json")
    assert CodeIntelligenceJourneyV1Alpha1.model_validate(payload) == result

    tampered = result.model_dump(mode="json")
    non_symbol_index = next(index for index, block in enumerate(result.handoff.blocks) if block.symbol is None)
    original_ref = result.handoff.blocks[non_symbol_index].evidence_ref
    other_anchor = next(anchor for anchor in result.lens.evidence if anchor.anchor_id != original_ref)
    tampered_block = tampered["handoff"]["blocks"][non_symbol_index]
    tampered_block["evidence_ref"] = other_anchor.anchor_id
    new_block_id = CodeContextBlockV1Alpha1.model_validate(tampered_block).block_id

    tampered_receipt = tampered["handoff"]["manifest"]["blocks"][non_symbol_index]
    tampered_receipt["evidence_ref"] = other_anchor.anchor_id
    tampered_receipt["block_id"] = new_block_id

    # Recompute the derived manifest and receipt identities so the mismatched
    # evidence anchor is the only real difference from the trusted result.
    tampered["handoff"]["receipt"]["manifest_id"] = CodeContextManifestV1Alpha1.model_validate(
        tampered["handoff"]["manifest"]
    ).manifest_id
    with pytest.raises(ValidationError, match="evidence anchor differs from its exact"):
        CodeIntelligenceJourneyV1Alpha1.model_validate(tampered)


@pytest.mark.parametrize("max_context_bytes", [50, 100, 256, 1000])
def test_low_budget_long_line_multi_block_journey_never_produces_a_false_anchor(
    tmp_path: Path, max_context_bytes: int
) -> None:
    """A byte budget must never split a source line, at any budget size.

    ``pkg/service.py`` pairs a matched symbol with a line far longer than any
    sampled budget, and ``pkg/consumer.py`` is long enough to need its own
    reduction. A planner that ever cut a body mid-line (instead of keeping
    only whole lines) would mint a block whose body cannot match a freshly
    re-read source anchor, or would blow up the exact-line-span contract
    validator. Sweeping budgets from smaller-than-one-long-line up to
    generous must produce neither an uncaught validation error nor a mismatch
    between any emitted block and its evidence.
    """
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    long_line = "    return value + " + "1" * 200
    (root / "pkg" / "service.py").write_text(
        f"def used(value: int) -> int:\n{long_line}\n\ndef maybe_disconnected() -> None:\n    pass\n",
        encoding="utf-8",
    )
    consumer_lines = ["from pkg.service import used", "", "def call() -> int:", "    return used(1)", ""]
    consumer_lines += [f"# padding line {index} " + "x" * 40 for index in range(60)]
    (root / "pkg" / "consumer.py").write_text("\n".join(consumer_lines) + "\n", encoding="utf-8")
    (root / "tests" / "test_service.py").write_text(
        "from pkg.service import used\n\ndef test_used():\n    assert used(1) == 2\n",
        encoding="utf-8",
    )
    repo = Repo.init(root)
    repo.index.add(["pkg/service.py", "pkg/consumer.py", "tests/test_service.py"])
    repo.index.commit("low-budget regression fixture")

    result = CodeIntelligenceJourney(root, max_context_files=8, max_context_bytes=max_context_bytes).run(
        query="Change the named used implementation",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )

    payload = result.model_dump(mode="json")
    assert CodeIntelligenceJourneyV1Alpha1.model_validate(payload) == result
    assert result.handoff.manifest.total_bytes <= max_context_bytes
    if max_context_bytes >= 256:
        assert len(result.handoff.blocks) >= 1

    anchors_by_id = {anchor.anchor_id: anchor for anchor in result.lens.evidence}
    for block in result.handoff.blocks:
        anchor = anchors_by_id[block.evidence_ref]
        assert anchor.path == block.path
        if block.symbol is None:
            assert (anchor.line_start, anchor.line_end, anchor.content_digest) == (
                block.line_start,
                block.line_end,
                block.body_digest,
            )
        else:
            assert (anchor.line_start, anchor.line_end, anchor.content_digest) == (
                block.symbol_line_start,
                block.symbol_line_end,
                block.symbol_body_digest,
            )
        source_lines = (root / block.path).read_text(encoding="utf-8").splitlines()
        assert block.body == "\n".join(source_lines[block.line_start - 1 : block.line_end])


def test_large_candidate_set_with_tiny_budget_has_bounded_deterministic_omissions(tmp_path: Path) -> None:
    """Many candidate files under a byte budget too small for even one line.

    A planner that emitted one path-specific omission per candidate would
    grow the manifest's omission metadata (and its serialized size) in
    proportion to repository size. Aggregating by reason keeps the manifest
    bounded regardless of how many candidate files exist.
    """
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pkg" / "service.py").write_text(
        "def used(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    tracked = ["pkg/service.py"]
    candidate_count = 150
    for index in range(candidate_count):
        name = f"pkg/consumer_{index:03d}.py"
        (root / name).write_text(
            f"from pkg.service import used\n\ndef call_{index}() -> int:\n    return used({index})\n",
            encoding="utf-8",
        )
        tracked.append(name)
    (root / "tests" / "test_service.py").write_text(
        "from pkg.service import used\n\ndef test_used():\n    assert used(1) == 2\n",
        encoding="utf-8",
    )
    tracked.append("tests/test_service.py")
    repo = Repo.init(root)
    repo.index.add(tracked)
    repo.index.commit("many dependents fixture")

    result = CodeIntelligenceJourney(root, max_context_files=500, max_context_bytes=4).run(
        query="change used",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )

    assert len(result.lens.impact.direct_dependents) >= candidate_count
    assert result.handoff.blocks == ()

    omissions = result.handoff.manifest.omissions
    assert len(omissions) <= CONTEXT_MANIFEST_MAX_OMISSIONS
    assert not any("pkg/consumer_" in item for item in omissions)

    reduced_or_omitted = [item for item in omissions if item.startswith("context_byte_limit_omitted:")]
    assert len(reduced_or_omitted) == 1
    assert int(reduced_or_omitted[0].split(":", 1)[1]) >= candidate_count

    payload = result.model_dump(mode="json")
    assert CodeIntelligenceJourneyV1Alpha1.model_validate(payload) == result
    assert len(json.dumps(payload["handoff"]["manifest"])) < 2_000


def test_context_manifest_rejects_omissions_exceeding_contract_bounds(tmp_path: Path) -> None:
    result = CodeIntelligenceJourney(_repository(tmp_path), max_context_files=3, max_context_bytes=4_000).run(
        query="change used",
        target_path="pkg/service.py",
        receiver_ref="coding-agent:test",
    )
    base = result.handoff.manifest.model_dump(mode="json")

    too_many_items = dict(
        base, omissions=tuple(f"reason_{index}" for index in range(CONTEXT_MANIFEST_MAX_OMISSIONS + 1))
    )
    with pytest.raises(ValidationError, match=f"exceed {CONTEXT_MANIFEST_MAX_OMISSIONS} items"):
        CodeContextManifestV1Alpha1.model_validate(too_many_items)

    too_long_item = dict(base, omissions=("x" * (CONTEXT_MANIFEST_MAX_OMISSION_CHARS + 1),))
    with pytest.raises(ValidationError, match=f"1..{CONTEXT_MANIFEST_MAX_OMISSION_CHARS} characters"):
        CodeContextManifestV1Alpha1.model_validate(too_long_item)

    empty_item = dict(base, omissions=("",))
    with pytest.raises(ValidationError, match=f"1..{CONTEXT_MANIFEST_MAX_OMISSION_CHARS} characters"):
        CodeContextManifestV1Alpha1.model_validate(empty_item)

    duplicate_items = dict(base, omissions=("same_reason:1", "same_reason:1"))
    with pytest.raises(ValidationError, match="duplicate entry"):
        CodeContextManifestV1Alpha1.model_validate(duplicate_items)

    per_item_chars = CONTEXT_MANIFEST_MAX_OMISSIONS_TOTAL_CHARS // CONTEXT_MANIFEST_MAX_OMISSIONS + 10
    too_much_total = dict(
        base,
        omissions=tuple(f"reason_{index}:" + "x" * per_item_chars for index in range(CONTEXT_MANIFEST_MAX_OMISSIONS)),
    )
    with pytest.raises(ValidationError, match=f"total characters exceed {CONTEXT_MANIFEST_MAX_OMISSIONS_TOTAL_CHARS}"):
        CodeContextManifestV1Alpha1.model_validate(too_much_total)


@pytest.mark.parametrize(
    ("script_name", "expected_doc"),
    [
        ("verify_code_intelligence_journey.py", "Run the frozen ACE-on-ACE Code Intelligence acceptance journey."),
        (
            "verify_code_intelligence_return.py",
            "Validate a coding-agent return against one exact Code Intelligence journey.",
        ),
    ],
)
def test_verifier_script_bootstraps_this_checkout_from_outside_cwd_without_pythonpath(
    tmp_path: Path, script_name: str, expected_doc: str
) -> None:
    """A verifier script launched by absolute path, from a cwd outside this checkout,

    isolated from user/site customization (``-I``), and with any inherited
    ``PYTHONPATH`` removed, must still resolve its own
    ``core.engine.code_intelligence`` package by walking up from its own
    ``__file__`` rather than by inheriting an ambient import path, and its
    post-import origin assertion must accept that resolution rather than
    mistaking it for a different, dirty checkout of the same package.
    """
    script_path = _PROJECT_ROOT / "scripts" / script_name
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, "-I", str(script_path), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert f"usage: {script_name}" in completed.stdout
    assert expected_doc in completed.stdout

from __future__ import annotations

from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from git import Repo
from git.objects.base import Object
from pydantic import ValidationError

from core.engine.code_intelligence.contracts import ConfidenceBand, DerivationKind, stable_digest
from core.engine.code_intelligence.ownership import (
    OWNERSHIP_MAX_UNCERTAINTY_ITEM_CHARS,
    OWNERSHIP_MAX_UNCERTAINTY_ITEMS,
    CodeOwnershipProjectionV1Alpha1,
    GitHubCodeownersAdapter,
    OwnershipProjectionStatus,
)


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "service.py").write_text("def serve():\n    return True\n", encoding="utf-8")
    repo = Repo.init(root)
    repo.index.add(["pkg/service.py"])
    repo.index.commit("initial source")
    return root


def _commit(root: Path, *paths: str) -> None:
    repo = Repo(root)
    repo.index.add(list(paths))
    repo.index.commit("update ownership fixture")


def test_missing_declaration_is_unavailable_and_never_infers_history(tmp_path: Path) -> None:
    projection = GitHubCodeownersAdapter(_repository(tmp_path)).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.source_path is None
    assert projection.owners == ()
    assert projection.searched_source_paths == (
        ".github/CODEOWNERS",
        "CODEOWNERS",
        "docs/CODEOWNERS",
    )
    assert "Git contributors do not establish" in " ".join(projection.uncertainties)
    assert projection.historical_contributors_are_current_owners is False
    assert projection.grants_source_authority is False
    assert projection.grants_change_authority is False
    assert projection.grants_approval_authority is False


def test_last_matching_declaration_has_exact_anchor_and_bounded_authority(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / ".github").mkdir()
    raw_line = "/pkg/service.py @ace/service-team service-owner@example.com"
    (root / ".github" / "CODEOWNERS").write_text(
        "# broad rule\n*.py @ace/python\n" + raw_line + "\n",
        encoding="utf-8",
    )
    _commit(root, ".github/CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.DECLARED
    assert projection.source_path == ".github/CODEOWNERS"
    assert [owner.owner_ref for owner in projection.owners] == ["@ace/service-team", "service-owner@example.com"]
    for owner in projection.owners:
        assert owner.matched_pattern == "/pkg/service.py"
        assert owner.confidence is ConfidenceBand.OBSERVED
        assert owner.evidence.path == ".github/CODEOWNERS"
        assert owner.evidence.line_start == owner.evidence.line_end == 3
        assert owner.evidence.content_digest == stable_digest(raw_line)
        assert owner.evidence.derivation is DerivationKind.DECLARED
        assert owner.declared_review_responsibility is True
        assert owner.identity_verified is False
        assert owner.platform_enforcement_verified is False
        assert owner.grants_source_authority is False
        assert owner.grants_change_authority is False
        assert owner.grants_approval_authority is False
        assert owner.grants_delivery_authority is False
        assert owner.grants_effect_authority is False


def test_declared_file_without_matching_rule_is_unassigned(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "CODEOWNERS").write_text("/docs/** @ace/docs\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNASSIGNED
    assert projection.source_path == "CODEOWNERS"
    assert projection.owners == ()
    assert "no supported rule matches" in " ".join(projection.uncertainties)


def test_unsupported_rule_fails_closed_instead_of_partially_claiming_owner(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "CODEOWNERS").write_text("*.py @ace/python\n[ab]*.py @ace/special\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.source_path is None
    assert projection.owners == ()
    assert "unsupported" in " ".join(projection.uncertainties)
    assert "failed closed" in " ".join(projection.uncertainties)


def test_adapter_rejects_paths_outside_or_missing_from_repository(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    adapter = GitHubCodeownersAdapter(root)

    with pytest.raises(ValueError, match="escapes repository"):
        adapter.project("../outside.py")
    with pytest.raises(ValueError, match="does not exist"):
        adapter.project("pkg/missing.py")

    outside = tmp_path / "outside.py"
    outside.write_text("outside = True\n", encoding="utf-8")
    (root / "pkg" / "external.py").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes repository"):
        adapter.project("pkg/external.py")


def test_declaration_source_must_be_a_tracked_current_regular_file(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    outside = tmp_path / "outside-codeowners"
    outside.write_text("/pkg/service.py @outside-owner\n", encoding="utf-8")
    (root / ".github").mkdir()
    source = root / ".github" / "CODEOWNERS"
    source.symlink_to(outside)
    _commit(root, ".github/CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.source_path is None
    assert projection.owners == ()
    assert "not a tracked regular file" in " ".join(projection.uncertainties)


def test_current_source_replaced_by_symlink_fails_closed(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    source = root / "CODEOWNERS"
    source.write_text("/pkg/service.py @tracked-owner\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")
    outside = tmp_path / "outside-codeowners"
    outside.write_text("/pkg/service.py @outside-owner\n", encoding="utf-8")
    source.unlink()
    source.symlink_to(outside)

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.owners == ()
    assert "symlink traversal" in " ".join(projection.uncertainties)


def test_ignored_untracked_declaration_cannot_modify_clean_head_projection(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / ".gitignore").write_text("CODEOWNERS\n", encoding="utf-8")
    _commit(root, ".gitignore")
    (root / "CODEOWNERS").write_text("/pkg/service.py @ignored-owner\n", encoding="utf-8")
    repo = Repo(root)
    assert repo.is_dirty(untracked_files=True) is False

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.owners == ()
    assert "tracked regular" in " ".join(projection.uncertainties)
    assert "@ignored-owner" not in " ".join(projection.uncertainties)


def test_target_aliases_and_contained_symlinks_are_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    adapter = GitHubCodeownersAdapter(root)

    with pytest.raises(ValueError, match="canonical repository-relative spelling"):
        adapter.project("pkg/../pkg/service.py")

    (root / "pkg" / "service-link.py").symlink_to("service.py")
    with pytest.raises(ValueError, match="canonical repository-relative spelling"):
        adapter.project("pkg/service-link.py")


def test_double_star_slash_matches_zero_or_more_directories(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "CODEOWNERS").write_text("/pkg/**/service.py @recursive-owner\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in projection.owners] == ["@recursive-owner"]


def test_directory_only_pattern_does_not_claim_same_named_regular_file(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "foo").write_text("regular file\n", encoding="utf-8")
    (root / "CODEOWNERS").write_text("foo/ @directory-owner\n", encoding="utf-8")
    _commit(root, "foo", "CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("foo")

    assert projection.status is OwnershipProjectionStatus.UNASSIGNED
    assert projection.owners == ()


def test_source_read_oserror_is_reported_as_unavailable(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    source = root / "CODEOWNERS"
    source.write_text("/pkg/service.py @owner\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")

    with patch.object(Object, "data_stream", new_callable=PropertyMock) as stream:
        stream.side_effect = OSError("simulated object read race")
        projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.owners == ()
    assert "could not be read" in " ".join(projection.uncertainties)


def test_dirty_tracked_declaration_projects_exact_head_bytes(tmp_path: Path) -> None:
    """HEAD proves the path and mode, so HEAD must also supply the bytes."""
    root = _repository(tmp_path)
    source = root / "CODEOWNERS"
    source.write_text("/pkg/service.py @head-owner\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")
    source.write_text("/pkg/service.py @worktree-owner\n", encoding="utf-8")
    assert Repo(root).is_dirty() is True

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in projection.owners] == ["@head-owner"]
    assert projection.owners[0].evidence.content_digest == stable_digest("/pkg/service.py @head-owner")
    assert projection.owners[0].grants_approval_authority is False


def test_case_aliased_target_spelling_is_rejected(tmp_path: Path) -> None:
    adapter = GitHubCodeownersAdapter(_repository(tmp_path))

    with pytest.raises(ValueError, match="exact component spelling"):
        adapter.project("PKG/service.py")
    with pytest.raises(ValueError, match="exact component spelling"):
        adapter.project("pkg/Service.py")


def test_noncanonical_double_star_placement_fails_closed(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "CODEOWNERS").write_text("/pkg/service.py @exact\nfoo/**bar @broken\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.owners == ()
    assert "** must be a whole path segment" in " ".join(projection.uncertainties)


def test_anchored_directory_rule_matches_the_directory_and_its_descendants(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "CODEOWNERS").write_text("/pkg @pkg-owner\n/pkg/service.py @exact-owner\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in projection.owners] == ["@exact-owner"]

    (root / "CODEOWNERS").write_text("/pkg @pkg-owner\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")
    descendant = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert descendant.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in descendant.owners] == ["@pkg-owner"]
    assert descendant.owners[0].matched_pattern == "/pkg"


def test_source_bytes_limit_boundary_and_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = "/pkg/service.py @owner\n"
    monkeypatch.setattr(GitHubCodeownersAdapter, "_MAX_SOURCE_BYTES", len(content.encode("utf-8")))

    boundary_root = _repository(tmp_path / "boundary")
    (boundary_root / "CODEOWNERS").write_text(content, encoding="utf-8")
    _commit(boundary_root, "CODEOWNERS")
    boundary = GitHubCodeownersAdapter(boundary_root).project("pkg/service.py")
    assert boundary.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in boundary.owners] == ["@owner"]

    over_root = _repository(tmp_path / "over")
    (over_root / "CODEOWNERS").write_text(content + "\n", encoding="utf-8")
    _commit(over_root, "CODEOWNERS")
    over = GitHubCodeownersAdapter(over_root).project("pkg/service.py")
    assert over.status is OwnershipProjectionStatus.UNAVAILABLE
    assert over.owners == ()
    assert "byte declaration size limit" in " ".join(over.uncertainties)


def test_line_bytes_limit_boundary_and_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    line_ok = "/pkg/service.py @owner"
    line_over = "/pkg/service.py @ownerx"
    monkeypatch.setattr(GitHubCodeownersAdapter, "_MAX_LINE_BYTES", len(line_ok.encode("utf-8")))

    boundary_root = _repository(tmp_path / "boundary")
    (boundary_root / "CODEOWNERS").write_text(line_ok + "\n", encoding="utf-8")
    _commit(boundary_root, "CODEOWNERS")
    boundary = GitHubCodeownersAdapter(boundary_root).project("pkg/service.py")
    assert boundary.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in boundary.owners] == ["@owner"]

    over_root = _repository(tmp_path / "over")
    (over_root / "CODEOWNERS").write_text(line_over + "\n", encoding="utf-8")
    _commit(over_root, "CODEOWNERS")
    over = GitHubCodeownersAdapter(over_root).project("pkg/service.py")
    assert over.status is OwnershipProjectionStatus.UNAVAILABLE
    assert over.owners == ()
    assert "byte line limit" in " ".join(over.uncertainties)


def test_rule_count_limit_boundary_and_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GitHubCodeownersAdapter, "_MAX_RULES", 2)

    boundary_root = _repository(tmp_path / "boundary")
    (boundary_root / "CODEOWNERS").write_text("/a.txt @owner-a\n/pkg/service.py @owner-b\n", encoding="utf-8")
    _commit(boundary_root, "CODEOWNERS")
    boundary = GitHubCodeownersAdapter(boundary_root).project("pkg/service.py")
    assert boundary.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in boundary.owners] == ["@owner-b"]

    over_root = _repository(tmp_path / "over")
    (over_root / "CODEOWNERS").write_text(
        "/a.txt @owner-a\n/pkg/service.py @owner-b\n/b.txt @owner-c\n", encoding="utf-8"
    )
    _commit(over_root, "CODEOWNERS")
    over = GitHubCodeownersAdapter(over_root).project("pkg/service.py")
    assert over.status is OwnershipProjectionStatus.UNAVAILABLE
    assert over.owners == ()
    assert "rule count limit" in " ".join(over.uncertainties)


def test_pattern_length_limit_boundary_and_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pattern_ok = "/pkg/service.py"
    pattern_over = pattern_ok + "x"
    monkeypatch.setattr(GitHubCodeownersAdapter, "_MAX_PATTERN_LENGTH", len(pattern_ok))

    boundary_root = _repository(tmp_path / "boundary")
    (boundary_root / "CODEOWNERS").write_text(f"{pattern_ok} @owner\n", encoding="utf-8")
    _commit(boundary_root, "CODEOWNERS")
    boundary = GitHubCodeownersAdapter(boundary_root).project("pkg/service.py")
    assert boundary.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in boundary.owners] == ["@owner"]

    over_root = _repository(tmp_path / "over")
    (over_root / "CODEOWNERS").write_text(f"{pattern_over} @owner\n", encoding="utf-8")
    _commit(over_root, "CODEOWNERS")
    over = GitHubCodeownersAdapter(over_root).project("pkg/service.py")
    assert over.status is OwnershipProjectionStatus.UNAVAILABLE
    assert over.owners == ()
    assert "pattern length limit" in " ".join(over.uncertainties)


def test_wildcard_complexity_limit_boundary_and_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GitHubCodeownersAdapter, "_MAX_PATTERN_WILDCARDS", 2)

    boundary_root = _repository(tmp_path / "boundary")
    (boundary_root / "aa.py").write_text("marker = True\n", encoding="utf-8")
    (boundary_root / "CODEOWNERS").write_text("*a*.py @owner-wild\n", encoding="utf-8")
    _commit(boundary_root, "aa.py", "CODEOWNERS")
    boundary = GitHubCodeownersAdapter(boundary_root).project("aa.py")
    assert boundary.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in boundary.owners] == ["@owner-wild"]

    over_root = _repository(tmp_path / "over")
    (over_root / "aa.py").write_text("marker = True\n", encoding="utf-8")
    (over_root / "CODEOWNERS").write_text("*a*a*.py @owner-wild\n", encoding="utf-8")
    _commit(over_root, "aa.py", "CODEOWNERS")
    over = GitHubCodeownersAdapter(over_root).project("aa.py")
    assert over.status is OwnershipProjectionStatus.UNAVAILABLE
    assert over.owners == ()
    assert "wildcard complexity limit" in " ".join(over.uncertainties)


def test_repeated_wildcard_pattern_rejected_deterministically_before_matching(tmp_path: Path) -> None:
    """A pattern shaped like the classic ``(*a)+`` ReDoS trigger must fail closed on a

    deterministic wildcard-count check, not on a wall-clock timeout, so this
    assertion needs no timing and cannot flake.
    """
    root = _repository(tmp_path)
    pathological_pattern = "*a" * 9 + "b"
    (root / "CODEOWNERS").write_text(f"{pathological_pattern} @owner\n", encoding="utf-8")
    _commit(root, "CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.owners == ()
    assert "wildcard complexity limit" in " ".join(projection.uncertainties)


def test_long_legal_near_miss_pattern_matches_with_a_deterministic_state_bound() -> None:
    """A legal (at-the-limit wildcard count), >=128-character pattern shaped like a

    classic ``(*a)+`` backtracking trigger must still resolve deterministically: it
    is rejected because the target never supplies the required trailing literal, and
    the internal DP walk visits a state count bounded by
    ``(len(pattern) + 1) * (len(target_path) + 1)`` -- proving the matcher cannot be
    driven into combinatorial backtracking by a legal near-miss pattern, without
    relying on any timing threshold.
    """
    pattern = "*a" * 8 + "a" * 111 + "!"
    assert len(pattern) >= 128
    target_path = "a" * 300  # near miss: every literal "a" matches, "!" never appears

    matched, states_visited = GitHubCodeownersAdapter._match_with_state_count(pattern, target_path)

    assert matched is False
    deterministic_bound = (len(pattern) + 1) * (len(target_path) + 1)
    assert states_visited <= deterministic_bound


def test_owners_per_rule_limit_boundary_and_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GitHubCodeownersAdapter, "_MAX_OWNERS_PER_RULE", 2)

    boundary_root = _repository(tmp_path / "boundary")
    (boundary_root / "CODEOWNERS").write_text("/pkg/service.py @o1 @o2\n", encoding="utf-8")
    _commit(boundary_root, "CODEOWNERS")
    boundary = GitHubCodeownersAdapter(boundary_root).project("pkg/service.py")
    assert boundary.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in boundary.owners] == ["@o1", "@o2"]

    over_root = _repository(tmp_path / "over")
    (over_root / "CODEOWNERS").write_text("/pkg/service.py @o1 @o2 @o3\n", encoding="utf-8")
    _commit(over_root, "CODEOWNERS")
    over = GitHubCodeownersAdapter(over_root).project("pkg/service.py")
    assert over.status is OwnershipProjectionStatus.UNAVAILABLE
    assert over.owners == ()
    assert "owner-per-rule limit" in " ".join(over.uncertainties)


def test_total_owners_limit_boundary_and_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GitHubCodeownersAdapter, "_MAX_TOTAL_OWNERS", 3)

    boundary_root = _repository(tmp_path / "boundary")
    (boundary_root / "CODEOWNERS").write_text("/a.txt @o1 @o2\n/pkg/service.py @o3\n", encoding="utf-8")
    _commit(boundary_root, "CODEOWNERS")
    boundary = GitHubCodeownersAdapter(boundary_root).project("pkg/service.py")
    assert boundary.status is OwnershipProjectionStatus.DECLARED
    assert [owner.owner_ref for owner in boundary.owners] == ["@o3"]

    over_root = _repository(tmp_path / "over")
    (over_root / "CODEOWNERS").write_text("/a.txt @o1 @o2\n/pkg/service.py @o3 @o4\n", encoding="utf-8")
    _commit(over_root, "CODEOWNERS")
    over = GitHubCodeownersAdapter(over_root).project("pkg/service.py")
    assert over.status is OwnershipProjectionStatus.UNAVAILABLE
    assert over.owners == ()
    assert "owner total limit" in " ".join(over.uncertainties)


def test_many_malformed_lines_yields_bounded_uncertainty_and_serialized_output(tmp_path: Path) -> None:
    """A <=1 MiB CODEOWNERS source with thousands of malformed lines must never expand

    into a multi-megabyte uncertainty or serialized projection: only a bounded number
    of diagnostics are retained verbatim, and the rest are aggregated deterministically.
    """
    root = _repository(tmp_path)
    malformed_line_count = 5_000
    content = "\n".join(f"badrule{index}" for index in range(malformed_line_count)) + "\n"
    assert len(content.encode("utf-8")) < GitHubCodeownersAdapter._MAX_SOURCE_BYTES
    (root / "CODEOWNERS").write_text(content, encoding="utf-8")
    _commit(root, "CODEOWNERS")

    projection = GitHubCodeownersAdapter(root).project("pkg/service.py")

    assert projection.status is OwnershipProjectionStatus.UNAVAILABLE
    assert projection.owners == ()
    joined = " ".join(projection.uncertainties)
    omitted = malformed_line_count - GitHubCodeownersAdapter._MAX_DIAGNOSTIC_ITEMS
    assert f"additional_malformed_rules:{omitted}" in joined
    assert len(joined) < 8_000
    serialized = projection.model_dump_json()
    assert len(serialized) < 20_000


def test_ownership_projection_uncertainty_bounds_apply_on_construction_and_deserialization() -> None:
    """The uncertainty bound is a Pydantic ``model_validator``, so it must reject both a

    directly constructed over-limit projection and a tampered/deserialized one, not just
    output the adapter itself happens to produce.
    """
    oversized_item_count = tuple(f"reason {index}" for index in range(OWNERSHIP_MAX_UNCERTAINTY_ITEMS + 1))
    with pytest.raises(ValidationError, match="uncertainties exceed"):
        CodeOwnershipProjectionV1Alpha1(
            target_path="pkg/service.py",
            status=OwnershipProjectionStatus.UNAVAILABLE,
            searched_source_paths=(),
            uncertainties=oversized_item_count,
        )

    tampered_payload = {
        "contract": "ace.code-intelligence.ownership-projection/v1alpha1",
        "target_path": "pkg/service.py",
        "status": "unavailable",
        "source_path": None,
        "searched_source_paths": [],
        "owners": [],
        "uncertainties": ["x" * (OWNERSHIP_MAX_UNCERTAINTY_ITEM_CHARS + 1)],
    }
    with pytest.raises(ValidationError, match="uncertainty entries exceed"):
        CodeOwnershipProjectionV1Alpha1.model_validate(tampered_payload)

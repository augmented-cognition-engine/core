"""Unit tests for the PI13 WS0 journey gate runner.

Provider-free and DB-free: everything here exercises the gate's data model,
orchestration, and report writing with injected probes. The installed-artifact
/ live-SurrealDB path is covered by the separate WS0 composition test.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest

import scripts.pi13_ws0_journey_gate
from scripts.pi13_ws0_journey_gate import (
    _CONNECT_AUTHORIZE_ROUTE,
    _CONNECT_PREVIEW_ROUTE,
    _REQUIRED_CONNECT_ROUTES,
    STEP_IDS,
    STEP_NAMES,
    JourneyGate,
    JourneyReport,
    ProbeContext,
    StepResult,
    StepStatus,
    _consent_before_read_probe,
    _import_outside_repo,
    _installed_distributions_exact,
    _qualified_connect_routes,
    build_default_probes,
    main,
    probe_j3,
    probe_j4,
    probe_j5,
    probe_j6,
    probe_j7,
    probe_j8,
    probe_j9,
    probe_j10,
    write_atomic,
)

pytestmark = pytest.mark.unit

CANONICAL_NAMES = (
    "Install",
    "Choose",
    "Connect",
    "Inventory",
    "First Brief",
    "Change",
    "Ask",
    "Correct",
    "Restart",
    "Own",
)


def _pass_result(step_id: str) -> StepResult:
    return StepResult(
        step_id=step_id,
        name=STEP_NAMES[step_id],
        status=StepStatus.PASS,
        summary=f"{step_id} ok",
    )


def _all_pass_results() -> tuple[StepResult, ...]:
    return tuple(_pass_result(step_id) for step_id in STEP_IDS)


def _context(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        repository_root=tmp_path / "repo",
        fixture_corpus=tmp_path / "corpus",
        json_report=tmp_path / "report.json",
        markdown_report=tmp_path / "report.md",
        surreal_url="",
    )


class TestStepVocabulary:
    def test_step_ids_are_exactly_j1_through_j10_in_order(self):
        assert STEP_IDS == tuple(f"J{i}" for i in range(1, 11))

    def test_step_names_are_the_ten_canonical_names_in_order(self):
        assert tuple(STEP_NAMES.keys()) == STEP_IDS
        assert tuple(STEP_NAMES.values()) == CANONICAL_NAMES


class TestStepResult:
    def test_pass_without_evidence_or_blocker_is_valid(self):
        result = _pass_result("J1")
        assert result.status is StepStatus.PASS

    @pytest.mark.parametrize("status", [StepStatus.FAIL, StepStatus.BLOCKED, StepStatus.PARTIAL])
    def test_non_pass_without_evidence_or_blocker_is_rejected(self, status):
        with pytest.raises(ValueError, match="requires evidence or a blocker"):
            StepResult(step_id="J1", name="Install", status=status, summary="bad")

    @pytest.mark.parametrize("status", [StepStatus.FAIL, StepStatus.BLOCKED, StepStatus.PARTIAL])
    def test_non_pass_with_evidence_or_blocker_is_accepted(self, status):
        with_evidence = StepResult(step_id="J1", name="Install", status=status, summary="s", evidence=("e",))
        with_blocker = StepResult(step_id="J1", name="Install", status=status, summary="s", blocker="b")
        assert with_evidence.evidence == ("e",)
        assert with_blocker.blocker == "b"

    def test_unknown_step_id_is_rejected(self):
        with pytest.raises(ValueError, match="unknown step id"):
            StepResult(step_id="J11", name="Nope", status=StepStatus.PASS, summary="s")


class TestJourneyReport:
    def test_missing_step_is_rejected(self):
        results = tuple(r for r in _all_pass_results() if r.step_id != "J5")
        with pytest.raises(ValueError, match="missing step results: J5"):
            JourneyReport(results=results)

    def test_duplicate_step_is_rejected(self):
        results = _all_pass_results() + (_pass_result("J3"),)
        with pytest.raises(ValueError, match="duplicate step results: J3"):
            JourneyReport(results=results)

    def test_out_of_order_steps_are_rejected(self):
        results = _all_pass_results()
        shuffled = results[1:] + results[:1]
        with pytest.raises(ValueError, match="out of order"):
            JourneyReport(results=shuffled)

    def test_all_pass_exit_code_is_zero(self):
        report = JourneyReport(results=_all_pass_results())
        assert report.all_pass is True
        assert report.exit_code == 0

    @pytest.mark.parametrize("status", [StepStatus.FAIL, StepStatus.BLOCKED, StepStatus.PARTIAL])
    def test_any_non_pass_exit_code_is_one(self, status):
        results = list(_all_pass_results())
        results[6] = StepResult(step_id="J7", name=STEP_NAMES["J7"], status=status, summary="s", blocker="b")
        report = JourneyReport(results=tuple(results))
        assert report.all_pass is False
        assert report.exit_code == 1

    def test_json_contains_all_ten_rows_in_order(self):
        payload = json.loads(JourneyReport(results=_all_pass_results()).to_json())
        assert [step["step_id"] for step in payload["steps"]] == list(STEP_IDS)
        assert [step["name"] for step in payload["steps"]] == list(CANONICAL_NAMES)

    def test_markdown_contains_all_ten_rows_in_order(self):
        markdown = JourneyReport(results=_all_pass_results()).to_markdown()
        rows = re.findall(r"^\| (J\d+) \|", markdown, flags=re.MULTILINE)
        assert rows == list(STEP_IDS)
        for name in CANONICAL_NAMES:
            assert f"| {name} |" in markdown


class TestJourneyGate:
    def test_raising_probe_becomes_fail_and_later_probes_still_run(self, tmp_path):
        ran: list[str] = []

        def exploding(context: ProbeContext) -> StepResult:
            ran.append("J2")
            raise RuntimeError("boom")

        def tracking(step_id: str):
            def probe(context: ProbeContext) -> StepResult:
                ran.append(step_id)
                return _pass_result(step_id)

            return probe

        probes = {step_id: tracking(step_id) for step_id in STEP_IDS}
        probes["J2"] = exploding
        report = JourneyGate(probes).run(_context(tmp_path))

        assert ran == list(STEP_IDS)
        j2 = report.results[1]
        assert j2.status is StepStatus.FAIL
        assert "RuntimeError: boom" in j2.evidence[0]
        assert all(r.status is StepStatus.PASS for r in report.results if r.step_id != "J2")

    def test_absent_probes_become_explicit_blocked(self, tmp_path):
        probes = {step_id: (lambda sid: lambda ctx: _pass_result(sid))(step_id) for step_id in STEP_IDS}
        del probes["J4"]
        del probes["J9"]
        report = JourneyGate(probes).run(_context(tmp_path))

        by_id = {r.step_id: r for r in report.results}
        for missing_id in ("J4", "J9"):
            assert by_id[missing_id].status is StepStatus.BLOCKED
            assert by_id[missing_id].blocker == f"probe_not_implemented:{missing_id}"
        assert len(report.results) == 10

    def test_unknown_probe_key_is_rejected(self):
        with pytest.raises(ValueError, match="unknown step ids: J99"):
            JourneyGate({"J99": lambda ctx: _pass_result("J1")})


class TestBuildDefaultProbes:
    def test_keys_equal_step_ids_exactly(self):
        assert tuple(build_default_probes().keys()) == STEP_IDS


class TestWriteAtomic:
    def test_replaces_existing_report(self, tmp_path):
        target = tmp_path / "out" / "report.json"
        write_atomic(target, "first\n")
        assert target.read_text(encoding="utf-8") == "first\n"
        write_atomic(target, "second\n")
        assert target.read_text(encoding="utf-8") == "second\n"
        leftovers = [p for p in target.parent.iterdir() if p != target]
        assert leftovers == []


class TestImportOutsideRepo:
    def test_rejects_module_resolving_under_repository_root(self, tmp_path, monkeypatch):
        repo_root = tmp_path / "repo"
        module_path = repo_root / "pkg" / "mod.py"
        module_path.parent.mkdir(parents=True)
        module_path.write_text("", encoding="utf-8")

        class FakeModule:
            __file__ = str(module_path)

        monkeypatch.setattr(importlib, "import_module", lambda name: FakeModule())
        with pytest.raises(RuntimeError, match="resolved inside repository root"):
            _import_outside_repo("pkg.mod", repo_root)

    def test_accepts_module_resolving_outside_repository_root(self, tmp_path, monkeypatch):
        outside = tmp_path / "site-packages" / "mod.py"
        outside.parent.mkdir(parents=True)
        outside.write_text("", encoding="utf-8")

        class FakeModule:
            __file__ = str(outside)

        monkeypatch.setattr(importlib, "import_module", lambda name: FakeModule())
        module = _import_outside_repo("mod", tmp_path / "repo")
        assert module.__file__ == str(outside)


class _FakeInstalledDistribution:
    """Only what _installed_distributions_exact reads: metadata Name and _path."""

    def __init__(self, name: str | None, dist_info: Path | str | None) -> None:
        self.metadata = {} if name is None else {"Name": name}
        if dist_info is not None:
            self._path = dist_info


class TestInstalledDistributionsExact:
    def _dist_info(self, tmp_path: Path, relative: str) -> Path:
        path = tmp_path / relative
        path.mkdir(parents=True)
        return path

    def test_same_dist_info_enumerated_twice_collapses_to_one(self, tmp_path):
        dist_info = self._dist_info(tmp_path, "site/ace_core-1.0.dist-info")
        first = _FakeInstalledDistribution("ace-core", dist_info)
        second = _FakeInstalledDistribution("ace-core", dist_info)

        result = _installed_distributions_exact([first, second])

        assert result == (first,)

    def test_name_spelling_and_path_indirection_still_collapse(self, tmp_path):
        dist_info = self._dist_info(tmp_path, "site/ace_core-1.0.dist-info")
        canonical = _FakeInstalledDistribution("ace-core", dist_info)
        variant = _FakeInstalledDistribution("Ace_Core", dist_info.parent / "." / dist_info.name)

        result = _installed_distributions_exact([canonical, variant])

        assert result == (canonical,)

    def test_genuinely_distinct_paths_sharing_a_name_are_both_retained(self, tmp_path):
        first = _FakeInstalledDistribution("ace-core", self._dist_info(tmp_path, "site-a/ace_core-1.0.dist-info"))
        second = _FakeInstalledDistribution("ace-core", self._dist_info(tmp_path, "site-b/ace_core-1.0.dist-info"))

        result = _installed_distributions_exact([first, second])

        assert set(result) == {first, second}

    def test_entries_without_name_or_path_are_retained_not_hidden(self, tmp_path):
        dist_info = self._dist_info(tmp_path, "site/ace_core-1.0.dist-info")
        keyed = _FakeInstalledDistribution("ace-core", dist_info)
        nameless = _FakeInstalledDistribution(None, self._dist_info(tmp_path, "site/broken-1.0.dist-info"))
        pathless = _FakeInstalledDistribution("ace-pathless", None)

        result = _installed_distributions_exact([keyed, nameless, pathless])

        assert result == (keyed, nameless, pathless)

    def test_keyed_output_order_is_deterministic_across_enumeration_order(self, tmp_path):
        alpha = _FakeInstalledDistribution("ace-alpha", self._dist_info(tmp_path, "site/ace_alpha-1.0.dist-info"))
        beta = _FakeInstalledDistribution("ace-beta", self._dist_info(tmp_path, "site/ace_beta-1.0.dist-info"))

        forward = _installed_distributions_exact([alpha, beta])
        reverse = _installed_distributions_exact([beta, alpha])

        assert forward == reverse == (alpha, beta)


class TestMain:
    def test_surreal_url_unset_writes_complete_reports_and_returns_one(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SURREAL_URL", raising=False)
        json_report = tmp_path / "reports" / "gate.json"
        markdown_report = tmp_path / "reports" / "gate.md"
        exit_code = main(
            [
                "--repository-root",
                str(tmp_path / "repo"),
                "--fixture-corpus",
                str(tmp_path / "corpus"),
                "--json-report",
                str(json_report),
                "--markdown-report",
                str(markdown_report),
            ]
        )

        assert exit_code == 1
        payload = json.loads(json_report.read_text(encoding="utf-8"))
        assert payload["all_pass"] is False
        assert payload["surreal_url"] == ""
        assert [step["step_id"] for step in payload["steps"]] == list(STEP_IDS)

        markdown = markdown_report.read_text(encoding="utf-8")
        rows = re.findall(r"^\| (J\d+) \|", markdown, flags=re.MULTILINE)
        assert rows == list(STEP_IDS)


class _FakeOpenApiModule:
    def __init__(self, paths: dict) -> None:
        self.app = types.SimpleNamespace(openapi=lambda: {"paths": paths})


class TestQualifiedConnectRoutes:
    def test_only_the_two_exact_connect_routes_are_reported(self):
        module = _FakeOpenApiModule(
            {
                _CONNECT_PREVIEW_ROUTE: {},
                _CONNECT_AUTHORIZE_ROUTE: {},
                "/v1/intelligence/builds/prepare": {},
                "/v1/intelligence/local-sources": {},
            }
        )
        assert _qualified_connect_routes(module) == sorted(_REQUIRED_CONNECT_ROUTES)

    def test_missing_authorize_route_is_reported_as_absent(self):
        module = _FakeOpenApiModule({_CONNECT_PREVIEW_ROUTE: {}})
        assert _qualified_connect_routes(module) == [_CONNECT_PREVIEW_ROUTE]

    def test_no_connect_routes_present_returns_empty(self):
        module = _FakeOpenApiModule({"/v1/intelligence/builds/prepare": {}})
        assert _qualified_connect_routes(module) == []


class _FakePlannerRegistry:
    def __init__(self, planner) -> None:
        self._planner = planner

    def load_installed_intelligence_build_planners(self):
        return {"intelligence_onboarding_profile:personal": self._planner} if self._planner else {}

    def resolve_intelligence_build_planner(self, profile_id: str):
        return self._planner


def _fake_pack_reference():
    from ace.intelligence.contracts.activation import CompiledPackRefV1

    digest = "a" * 64
    return CompiledPackRefV1(
        pack_id="personal_intelligence",
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{digest[:32]}",
        pack_digest=f"sha256:{digest}",
    )


class TestConsentBeforeReadProbe:
    def _context(self, tmp_path: Path) -> ProbeContext:
        return ProbeContext(
            repository_root=tmp_path / "repo",
            fixture_corpus=tmp_path / "corpus",
            json_report=tmp_path / "report.json",
            markdown_report=tmp_path / "report.md",
            surreal_url="",
        )

    def _patch_planner_registry(self, monkeypatch, planner):
        import ace.application.local_source_connect as local_source_connect

        real_import = scripts.pi13_ws0_journey_gate._import_outside_repo

        def fake_import(module_name: str, repository_root: Path):
            if module_name == "core.engine.core.intelligence_build_planner_registry":
                return _FakePlannerRegistry(planner)
            if module_name == "ace.application.local_source_connect":
                return local_source_connect
            return real_import(module_name, repository_root)

        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_import_outside_repo", fake_import)

    def test_missing_planner_raises(self, tmp_path, monkeypatch):
        self._patch_planner_registry(monkeypatch, planner=None)
        with pytest.raises(RuntimeError, match="did not resolve"):
            _consent_before_read_probe(self._context(tmp_path))

    def test_lexical_preview_and_zero_read_negatives_pass(self, tmp_path, monkeypatch):
        planner = types.SimpleNamespace(pack_reference=_fake_pack_reference())
        self._patch_planner_registry(monkeypatch, planner=planner)

        evidence = _consent_before_read_probe(self._context(tmp_path))

        assert any(item.startswith("consent_probe_preview:") for item in evidence)
        assert "local:read_only:no_network:no_write" in "".join(evidence)
        assert "consent_probe_rejected:missing_authorized:provider_calls=0" in evidence
        assert "consent_probe_rejected:false_authorized:provider_calls=0" in evidence


class TestProbeJ3Gating:
    def _context(self, tmp_path: Path) -> ProbeContext:
        return ProbeContext(
            repository_root=tmp_path / "repo",
            fixture_corpus=tmp_path / "corpus",
            json_report=tmp_path / "report.json",
            markdown_report=tmp_path / "report.md",
            surreal_url="",
        )

    def _patch_common(self, monkeypatch, *, connect_routes, consent_ok, executor_present):
        fake_artifact = types.SimpleNamespace(
            capability="source_snapshot",
            contract="ace.source.snapshot/v1alpha1",
            implementation_id="fake_provider",
            implementation_version="1.0.0",
            artifact_digest="sha256:" + ("b" * 64),
        )

        class _FakeExecutorRegistry:
            def load_installed_intelligence_build_executors(self):
                return {"intelligence_onboarding_profile:personal": object()} if executor_present else {}

        class _FakeSnapshotRegistry:
            SOURCE_SNAPSHOT_PROVIDER_ENTRY_POINT_GROUP = "pi13.fake.group"

            def load_installed_source_snapshot_providers(self):
                return {"intelligence_onboarding_profile:personal": object()}

            def resolve_source_snapshot_provider(self):
                return object()

        class _FakeSnapshotPort:
            @staticmethod
            def validate_source_snapshot_provider_registration(provider):
                return fake_artifact

        def fake_import(module_name: str, repository_root: Path):
            if module_name == "core.engine.core.intelligence_build_executor_registry":
                return _FakeExecutorRegistry()
            if module_name == "core.engine.api.main":
                return object()
            if module_name == "core.engine.core.source_snapshot_provider_registry":
                return _FakeSnapshotRegistry()
            if module_name == "ace.application.source_snapshot_provider":
                return _FakeSnapshotPort()
            raise AssertionError(f"unexpected module import: {module_name}")

        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_import_outside_repo", fake_import)
        monkeypatch.setattr(
            scripts.pi13_ws0_journey_gate, "_qualified_connect_routes", lambda api_module: connect_routes
        )
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_prepare_snapshot_activation", lambda context, artifact: [])

        def fake_consent_probe(context):
            if consent_ok:
                return ["consent_probe_preview:fake", "consent_probe_rejected:missing_authorized:provider_calls=0"]
            raise RuntimeError("consent probe failed")

        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_consent_before_read_probe", fake_consent_probe)

    def test_executor_absence_does_not_block_pass(self, tmp_path, monkeypatch):
        self._patch_common(
            monkeypatch,
            connect_routes=sorted(_REQUIRED_CONNECT_ROUTES),
            consent_ok=True,
            executor_present=False,
        )
        result = probe_j3(self._context(tmp_path))
        assert result.status is StepStatus.PASS
        assert any("executor_present:False" in item for item in result.evidence)

    def test_missing_authorize_route_still_fails(self, tmp_path, monkeypatch):
        self._patch_common(
            monkeypatch,
            connect_routes=[_CONNECT_PREVIEW_ROUTE],
            consent_ok=True,
            executor_present=True,
        )
        result = probe_j3(self._context(tmp_path))
        assert result.status is StepStatus.FAIL
        assert "connect_routes" in result.blocker

    def test_failing_consent_probe_still_fails(self, tmp_path, monkeypatch):
        self._patch_common(
            monkeypatch,
            connect_routes=sorted(_REQUIRED_CONNECT_ROUTES),
            consent_ok=False,
            executor_present=True,
        )
        result = probe_j3(self._context(tmp_path))
        assert result.status is StepStatus.FAIL
        assert "consent_probe" in result.blocker
        assert any("consent_probe:unavailable" in item for item in result.evidence)


def _walk_success() -> dict:
    return {
        "reached": "brief_queried",
        "error": None,
        "evidence": ["token:issued", "owner_bootstrap:grants=5", "connect_authorize:captures=2"],
        "inventory": {
            "source_health": 5,
            "entity": 5,
            "observation": 5,
            "observation_locators": [
                "notes/second.md",
                "notes/vault.md",
                "sample.csv",
                "sample.json",
                "sample.pdf",
            ],
            "observation_kinds": ["csv", "json", "md", "pdf"],
        },
        "ask": {
            "answered": True,
            "answer_claims": 2,
            "answer_citations": 2,
            "refused_unanswerable": True,
            "evidence": "answered_claims=2;citations=2;refused_unanswerable=True",
        },
        "correction": {"bound": True, "claim_id": "grounded_claim:abc", "evidence": "claim=grounded_claim:abc"},
        "restart": {"reopened_identically": True, "before": 6, "after": 6, "evidence": "identical=True"},
        "ownership": {
            "exported": True,
            "export_records": 6,
            "previewed": 6,
            "deletion_proved": True,
            "survivors_after_deletion": 0,
            "evidence": "export_records=6;preview_records=6;proof=True;survivors=0",
        },
        "brief": {
            "count": 1,
            "cited_claims": 5,
            "uncited_claims": 0,
            "citation_sources": ["notes/vault.md", "sample.csv", "sample.json", "sample.pdf"],
            "citation_kinds": ["csv", "json", "md", "pdf"],
            "unresolved_citations": 0,
        },
    }


class TestProbeJ7ConnectedAnswers:
    def test_j7_passes_when_a_cited_answer_and_an_honest_refusal_both_hold(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: _walk_success())
        result = probe_j7(_context(tmp_path))

        assert result.status is StepStatus.PASS
        assert result.blocker is None
        assert "answered_claims=2" in " ".join(result.evidence)

    def test_j7_is_partial_when_refusal_cannot_be_demonstrated(self, tmp_path, monkeypatch):
        """Answering a lexically disjoint question is not fabrication -- the claims
        are still real and cited -- but it means the honest-refusal half of J7
        cannot be shown, which the report must say rather than pass over."""

        walk = _walk_success()
        walk["ask"]["refused_unanswerable"] = False
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j7(_context(tmp_path))

        assert result.status is StepStatus.PARTIAL
        assert result.blocker == "WS0:ask_refusal_not_demonstrable"
        joined = " ".join((result.summary, *result.evidence))
        assert "stopword" in joined
        assert "retrieval" in joined

    def test_j7_fails_only_when_an_answer_carries_no_citation(self, tmp_path, monkeypatch):
        walk = _walk_success()
        walk["ask"] = {
            "answered": True,
            "answer_claims": 3,
            "answer_citations": 0,
            "refused_unanswerable": True,
            "evidence": "answered_claims=3;citations=0",
        }
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j7(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:ask_answered_without_citations"

    def test_j7_is_partial_when_no_connected_answer_was_produced(self, tmp_path, monkeypatch):
        walk = _walk_success()
        walk["ask"] = {
            "answered": False,
            "answer_claims": 0,
            "answer_citations": 0,
            "refused_unanswerable": True,
            "evidence": "answered_claims=0",
        }
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j7(_context(tmp_path))

        assert result.status is StepStatus.PARTIAL
        assert result.blocker == "WS0:connected_cited_answer_unavailable"


class TestProbeJ8ClaimBoundCorrection:
    def test_j8_passes_when_a_correction_binds_a_real_cited_claim(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: _walk_success())
        result = probe_j8(_context(tmp_path))

        assert result.status is StepStatus.PASS
        assert "grounded_claim:abc" in " ".join(result.evidence)

    def test_j8_is_partial_without_a_real_claim_to_correct(self, tmp_path, monkeypatch):
        walk = _walk_success()
        walk["correction"] = {"bound": False, "evidence": "no cited claim available to correct"}
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j8(_context(tmp_path))

        assert result.status is StepStatus.PARTIAL
        assert result.blocker == "WS0:claim_bound_correction_unavailable"


class TestProbeJ9Restart:
    def test_j9_passes_when_every_resource_reopens_identically(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: _walk_success())
        result = probe_j9(_context(tmp_path))

        assert result.status is StepStatus.PASS
        joined = " ".join((result.summary, *result.evidence))
        assert "identical=True" in joined
        # The claim must be exactly what was proven: a reopened connection pool,
        # not a restarted service with a persisted volume.
        assert "connection pool" in joined

    def test_j9_fails_when_reopened_material_differs(self, tmp_path, monkeypatch):
        walk = _walk_success()
        walk["restart"] = {"reopened_identically": False, "before": 6, "after": 5, "evidence": "identical=False"}
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j9(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:restart_material_changed"


class TestProbeJ10Ownership:
    def test_j10_passes_on_export_deletion_proof_and_non_reappearance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: _walk_success())
        result = probe_j10(_context(tmp_path))

        assert result.status is StepStatus.PASS
        assert "survivors=0" in " ".join(result.evidence)

    def test_j10_fails_when_the_preview_covered_no_records(self, tmp_path, monkeypatch):
        """Confirming a deletion whose preview covered nothing would prove nothing."""

        walk = _walk_success()
        walk["ownership"]["previewed"] = 0
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j10(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:ownership_deletion_preview_empty"

    def test_j10_fails_when_deleted_material_reappears(self, tmp_path, monkeypatch):
        walk = _walk_success()
        walk["ownership"]["survivors_after_deletion"] = 3
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j10(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:deleted_material_reappeared"


class TestProbeJ6StructuralBlocker:
    def test_j6_names_the_missing_public_reingest_surface(self, tmp_path):
        """Detection now exists and the executor routes revisions, so J6's old
        'nothing to detect against' summary would be false. The honest blocker is
        that no public surface admits a second capture of an edited source."""

        result = probe_j6(_context(tmp_path))

        assert result.status is StepStatus.BLOCKED
        assert result.blocker == "WS5:public_reingest_surface_unavailable"
        joined = " ".join((result.summary, *result.evidence))
        assert "content-revision" in joined
        assert "activation approval" in joined
        assert "live source ingress" in joined
        assert "no public route" in joined

    def test_j6_no_longer_claims_nothing_exists_to_detect_against(self, tmp_path):
        text = " ".join((probe_j6(_context(tmp_path)).summary, *probe_j6(_context(tmp_path)).evidence)).lower()

        assert "nothing exists to detect a change against" not in text


class TestProbeJ4InstalledWalk:
    def test_j4_passes_when_the_installed_walk_yields_markdown_inventory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: _walk_success())
        result = probe_j4(_context(tmp_path))

        assert result.step_id == "J4"
        assert result.status is StepStatus.PASS
        assert result.blocker is None
        joined = " ".join((result.summary, *result.evidence))
        assert "source_health=5" in joined
        assert "entity=5" in joined
        assert "observation=5" in joined
        assert "notes/vault.md" in joined
        assert "sample.pdf" in joined
        assert "observation_kinds:csv,json,md,pdf" in joined
        assert "token:issued" in joined

    def test_j4_fails_closed_naming_the_step_when_the_walk_stops_early(self, tmp_path, monkeypatch):
        walk = {
            "reached": "activation_plan_activate",
            "error": "RuntimeError: /activation-plan/activate: 409 canonical approval window",
            "evidence": ["token:issued"],
            "inventory": None,
            "brief": None,
        }
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j4(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:journey_walk:activation_plan_activate"
        assert "409" in " ".join(result.evidence)

    def test_j4_fails_when_inventory_is_empty_or_has_no_resolved_sources(self, tmp_path, monkeypatch):
        walk = _walk_success()
        walk["inventory"] = {
            "source_health": 1,
            "entity": 0,
            "observation": 0,
            "observation_locators": [],
            "observation_kinds": [],
        }
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j4(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:inventory_empty"

    def test_j4_fails_when_an_advertised_source_kind_never_reaches_inventory(self, tmp_path, monkeypatch):
        """WS4 breadth: the profile advertises four local kinds, so an inventory
        that silently covers only some of them is not the promised journey."""

        walk = _walk_success()
        # Enough resolved sources to clear the emptiness check: the gap is breadth.
        walk["inventory"]["observation_kinds"] = ["md"]
        walk["inventory"]["observation_locators"] = ["notes/second.md", "notes/vault.md"]
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j4(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:inventory_source_kinds_incomplete"
        assert "csv" in " ".join(result.evidence)


class TestProbeJ5InstalledWalk:
    def test_j5_passes_when_every_cited_claim_resolves_to_markdown_sources(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: _walk_success())
        result = probe_j5(_context(tmp_path))

        assert result.status is StepStatus.PASS
        joined = " ".join((result.summary, *result.evidence))
        assert "cited_claims=5" in joined
        assert "sample.pdf" in joined

    def test_j5_fails_when_citations_do_not_span_every_advertised_kind(self, tmp_path, monkeypatch):
        walk = _walk_success()
        walk["brief"]["citation_kinds"] = ["md"]
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j5(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:brief_citation_kinds_incomplete"

    def test_j5_fails_naming_the_brief_as_of_gate_when_the_walk_stops_in_synthesis(self, tmp_path, monkeypatch):
        """The walk reaches /start but canonical Brief assembly refuses the draft:
        citations' retrieved_at (admission commit) may not follow the Brief's
        as_of (the corpus validity cut). The gate must name that exact wall."""

        walk = {
            "reached": "start",
            "error": (
                "_WalkStopped: /v1/intelligence/builds/start: 503 ... ValidationError 1 validation error for "
                "BriefV1Alpha1 Value error, Brief citations must be available by the Brief as_of cutoff"
            ),
            "evidence": ["activation_plan_activate:replayed=False;session=ACTIVE"],
            "inventory": None,
            "brief": None,
        }
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j5(_context(tmp_path))

        assert result.status is StepStatus.BLOCKED
        assert result.blocker == "J4/WS0:journey_walk:start"
        joined = " ".join((result.summary, *result.evidence))
        assert "as_of cutoff" in joined
        assert "session=ACTIVE" in joined

    def test_j5_is_blocked_when_the_walk_never_reached_inventory(self, tmp_path, monkeypatch):
        walk = {"reached": "connect_authorize", "error": "boom", "evidence": [], "inventory": None, "brief": None}
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j5(_context(tmp_path))

        assert result.status is StepStatus.BLOCKED
        assert result.blocker == "J4/WS0:journey_walk:connect_authorize"

    def test_j5_fails_when_a_brief_exists_but_a_claim_is_uncited(self, tmp_path, monkeypatch):
        walk = _walk_success()
        walk["brief"]["uncited_claims"] = 1
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        result = probe_j5(_context(tmp_path))

        assert result.status is StepStatus.FAIL
        assert result.blocker == "WS0:brief_claims_uncited"


class TestStubProviderEnvironment:
    def test_configure_binds_the_stub_through_the_production_compat_slot(self, monkeypatch):
        monkeypatch.delenv("OPENAI_COMPAT_BASE_URL", raising=False)
        monkeypatch.delenv("API_KEY", raising=False)
        server = scripts.pi13_ws0_journey_gate.configure_stub_provider_environment()
        try:
            assert server is not None
            assert os.environ["OPENAI_COMPAT_BASE_URL"] == server.base_url
            assert os.environ["OPENAI_COMPAT_BASE_URL"].startswith("http://127.0.0.1:")
            assert len(os.environ["API_KEY"]) >= 32
        finally:
            server.stop()

    def test_configure_is_disabled_explicitly_and_never_overrides_an_operator_choice(self, monkeypatch):
        monkeypatch.setenv("PI13_WS0_STUB_PROVIDER", "0")
        assert scripts.pi13_ws0_journey_gate.configure_stub_provider_environment() is None
        monkeypatch.setenv("PI13_WS0_STUB_PROVIDER", "1")
        monkeypatch.setenv("OPENAI_COMPAT_BASE_URL", "http://operator.example/v1")
        assert scripts.pi13_ws0_journey_gate.configure_stub_provider_environment() is None
        assert os.environ["OPENAI_COMPAT_BASE_URL"] == "http://operator.example/v1"


class TestBlockedProbesStayVisibleInReports:
    def test_failed_walk_rows_reach_the_reports_with_their_exact_step(self, tmp_path, monkeypatch):
        walk = {
            "reached": "bind",
            "error": "RuntimeError: /bind: 409",
            "evidence": [],
            "inventory": None,
            "brief": None,
        }
        monkeypatch.setattr(scripts.pi13_ws0_journey_gate, "_installed_journey_walk", lambda context: walk)
        results = list(_all_pass_results())
        results[3] = probe_j4(_context(tmp_path))
        results[4] = probe_j5(_context(tmp_path))
        report = JourneyReport(results=tuple(results))

        payload = json.loads(report.to_json())
        by_id = {step["step_id"]: step for step in payload["steps"]}
        assert by_id["J4"]["status"] == "FAIL"
        assert by_id["J4"]["blocker"] == "WS0:journey_walk:bind"
        assert by_id["J5"]["status"] == "BLOCKED"
        assert by_id["J5"]["blocker"] == "J4/WS0:journey_walk:bind"
        assert "/bind: 409" in report.to_markdown()
        assert report.exit_code == 1


class TestFixtureCorpus:
    corpus = Path(__file__).parent / "fixtures" / "pi13_ws0"

    @pytest.mark.parametrize(
        ("relative", "signature"),
        [
            ("notes/vault.md", "PI13 WS0"),
            ("notes/second.md", "PI13 WS0"),
            ("sample.pdf", "%PDF-1.4"),
            ("sample.csv", "id,name,value"),
            ("sample.json", "pi13_ws0"),
        ],
    )
    def test_fixture_contains_expected_signature(self, relative, signature):
        path = self.corpus / relative
        assert path.is_file(), f"missing fixture: {path}"
        assert signature.encode("utf-8") in path.read_bytes()

    def test_pdf_starts_with_pdf_1_4_header(self):
        assert (self.corpus / "sample.pdf").read_bytes().startswith(b"%PDF-1.4")

    def test_json_fixture_is_valid_json(self):
        json.loads((self.corpus / "sample.json").read_text(encoding="utf-8"))

    def test_markdown_folder_holds_at_least_two_distinct_notes(self):
        """The Builder source-scope bridge fails closed below two exact captures;
        Markdown is the only WS3-mapped kind (PDF/CSV/JSON stay WS4)."""

        notes = sorted(path.name for path in (self.corpus / "notes").glob("*.md"))
        assert len(notes) >= 2
        assert len(set(notes)) == len(notes)


class TestWalkClock:
    def test_instants_are_strictly_increasing_and_never_ahead_of_real_time(self):
        clock = scripts.pi13_ws0_journey_gate._Clock()
        instants = [clock.now() for _ in range(50)]
        assert all(later > earlier for earlier, later in zip(instants[:-1], instants[1:], strict=True))
        # Durable artifacts stamped by the walk must already be "available" at the
        # server's real now, or later reads as-of now cannot see them.
        assert instants[-1] <= datetime.now(UTC)
        assert all(item.tzinfo is not None for item in instants)

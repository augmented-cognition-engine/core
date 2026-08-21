"""CI-shape tests for the PI13 WS0 allowed-failure journey job.

These assert the structural contract of the ``pi13-ws0`` job in
``.github/workflows/ci.yml`` without depending on incidental whitespace.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

PRE_EXISTING_JOBS = ["lint", "test", "naked-kernel", "canvas", "security", "docker"]

UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text())


@pytest.fixture(scope="module")
def job(workflow):
    return workflow["jobs"]["pi13-ws0"]


@pytest.fixture(scope="module")
def steps_by_name(job):
    named = {step["name"]: step for step in job["steps"] if "name" in step}
    assert len(named) == len([s for s in job["steps"] if "name" in s]), "duplicate step names in pi13-ws0"
    return named


def test_job_exists_with_expected_shell(workflow, job):
    assert "pi13-ws0" in workflow["jobs"]
    assert job["name"] == "PI13 WS0 — Personal J1-J10 (allowed failure)"
    assert job["runs-on"] == "ubuntu-latest"
    assert job["needs"] == "lint"
    assert job["timeout-minutes"] == 35


def test_job_is_allowed_failure_at_job_level(job):
    assert job["continue-on-error"] is True


def test_build_step_builds_all_four_wheel_sources(steps_by_name):
    run = steps_by_name["Build wheels (Core + local adapters + PI pack + PI bundle)"]["run"]
    assert '--outdir "$RUNNER_TEMP/pi13-ws0-dist" .' in run
    assert "for adapter in adapters/local_*" in run
    assert '--outdir "$RUNNER_TEMP/pi13-ws0-dist" "$adapter"' in run
    assert "domain_packs/personal_intelligence" in run
    assert "solution_bundles/personal_intelligence" in run


def test_venv_created_under_runner_temp_not_workspace(steps_by_name):
    run = steps_by_name["Create install venv outside the workspace"]["run"]
    assert 'python -m venv "$RUNNER_TEMP/pi13-ws0-venv"' in run
    assert "GITHUB_WORKSPACE" not in run


def test_surreal_step_is_pinned_in_memory_and_bounded(steps_by_name):
    run = steps_by_name["Start disposable SurrealDB (in-memory, no volume)"]["run"]
    assert "surrealdb/surrealdb:v3.2.3" in run
    # The start command must end on the in-memory backend, with no volume mount.
    assert " memory" in run
    assert "--volume" not in run
    tokens = run.split()
    assert "-v" not in tokens
    # Readiness polling is bounded, not an infinite wait.
    assert "for attempt in $(seq 1 30)" in run
    assert "is-ready" in run
    assert "exit 1" in run


def test_schema_step_runs_installed_module_against_ci_port(steps_by_name):
    step = steps_by_name["Apply schema from the installed package"]
    assert step["working-directory"] == "${{ runner.temp }}"
    assert step["env"]["SURREAL_URL"] == "ws://localhost:18130"
    assert '"$RUNNER_TEMP/pi13-ws0-venv/bin/python" -m scripts.schema_apply' in step["run"]


def test_runner_step_uses_installed_venv_and_stays_strict(steps_by_name):
    step = steps_by_name["Run J1-J10 journey gate (installed venv, stub model)"]
    run = step["run"]
    assert '"$RUNNER_TEMP/pi13-ws0-venv/bin/python"' in run
    assert "scripts/pi13_ws0_journey_gate.py" in run
    assert "--repository-root" in run
    assert "--fixture-corpus" in run
    assert "--json-report" in run
    assert "--markdown-report" in run
    # A red journey run must be visible: no swallowed exit codes.
    assert "|| true" not in run
    assert "continue-on-error" not in step


@pytest.mark.parametrize(
    "step_name",
    [
        "Publish journey report to step summary",
        "Upload journey report",
        "Tear down SurrealDB container",
    ],
)
def test_reporting_and_teardown_always_run(steps_by_name, step_name):
    assert steps_by_name[step_name]["if"] == "always()"


def test_upload_step_is_pinned_and_strict(steps_by_name):
    step = steps_by_name["Upload journey report"]
    assert step["uses"].startswith(f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}")
    assert step["with"]["name"] == "pi13-ws0-journey-report"
    assert step["with"]["path"] == "${{ runner.temp }}/pi13-ws0-report"
    assert step["with"]["if-no-files-found"] == "error"


def test_teardown_force_removes_named_container(steps_by_name):
    run = steps_by_name["Tear down SurrealDB container"]["run"]
    assert "docker rm -f pi13-ws0-surreal" in run


def test_pre_existing_jobs_remain_top_level(workflow, job):
    for job_id in PRE_EXISTING_JOBS:
        assert job_id in workflow["jobs"], f"{job_id} missing from top-level jobs"
        assert job_id not in job, f"{job_id} nested under pi13-ws0"

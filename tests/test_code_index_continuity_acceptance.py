from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.verify_code_index_continuity import run_acceptance


def _assert_acceptance(result: dict) -> None:
    assert result["accepted"] is True
    assert result["initial_capture"]["generation"] == 1
    assert result["initial_capture"]["parent_snapshot_id"] is None
    assert result["fresh_process_reopen"]["fresh_python_process"] is True
    assert result["fresh_process_reopen"]["full_rescan_permitted"] is False
    assert result["fresh_process_reopen"]["provider_invocation_permitted"] is False
    assert result["fresh_process_reopen"]["snapshot_id"] == result["initial_capture"]["snapshot_id"]
    assert result["fresh_process_reopen"]["index_id"] == result["initial_capture"]["index_id"]
    assert result["incremental_update"]["changed_files"] == ["pkg/service.py"]
    assert result["incremental_update"]["stats"]["updated"] == 1
    assert result["incremental_update"]["generation"] == 2
    assert result["incremental_update"]["parent_snapshot_id"] == result["initial_capture"]["snapshot_id"]
    assert result["incremental_update"]["parent_snapshot_digest"] == result["initial_capture"]["snapshot_digest"]
    assert result["incremental_update"]["index_id"] != result["initial_capture"]["index_id"]
    assert result["incremental_update"]["phase1_state_digest"] != result["initial_capture"]["phase1_state_digest"]
    assert result["immutable_history"] == {
        "snapshot_count": 2,
        "old_snapshot_still_readable": True,
        "old_snapshot_digest_unchanged": True,
        "old_symbol_absent": True,
        "new_symbol_present": True,
    }
    assert result["authority"] == {
        "provider_neutral": True,
        "grants_source_authority": False,
        "grants_reasoning_authority": False,
        "grants_delivery_authority": False,
        "grants_execution_authority": False,
        "grants_effect_authority": False,
        "repository_revalidation_required": True,
    }
    assert any("caller supplying the exact changed-file set" in item for item in result["limitations"])
    assert any("does not claim" in item for item in result["limitations"])


def test_durable_continuity_acceptance(tmp_path: Path) -> None:
    _assert_acceptance(run_acceptance(tmp_path))


def test_continuity_cli_emits_reproducible_evidence_packet(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    output = tmp_path / "continuity-evidence.json"
    work_root = tmp_path / "cli-work"
    completed = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "verify_code_index_continuity.py"),
            "--work-root",
            str(work_root),
            "--output",
            str(output),
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout == ""
    _assert_acceptance(json.loads(output.read_text(encoding="utf-8")))

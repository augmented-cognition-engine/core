from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_g1_public_evidence_package_replays_cleanly():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/verify_g1_living_product_graph.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "passed"
    assert receipt["contract"]["llm_calls"] == 0
    assert receipt["contract"]["domain_writes"] == 0
    assert receipt["determinism"] == {
        "fresh_process_byte_identical": True,
        "fresh_process_sha256": receipt["projection"]["sha256"],
        "reordered_byte_identical": True,
        "repeated_byte_identical": True,
    }
    assert receipt["projection"]["assertion_states"] == {
        "accepted": 1,
        "contested": 2,
        "provisional": 1,
        "rejected": 1,
    }

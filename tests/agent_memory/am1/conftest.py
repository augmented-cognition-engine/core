from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO / "evaluations/fixtures/agent_memory_am1_session_normalization_v1.json"


@pytest.fixture
def am1_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

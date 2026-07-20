# tests/canvas/conftest.py
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=False)
def fake_llm_trade_off():
    fake = AsyncMock()
    fake.complete = AsyncMock(
        return_value="""<reasoning>
Checking — two options: Postgres (relational) vs DynamoDB (NoSQL)
Scoring — consistency axis favors Postgres; team_familiarity also favors Postgres
Weighing — billing requires ACID; team SQL fluency reduces ramp cost
Conclusion — Postgres wins on both axes given billing and team constraints
</reasoning>
<json>
{
    "title": "Postgres vs DynamoDB",
    "question": "Postgres or DynamoDB?",
    "options": [
        {"name": "Postgres", "scores": {"consistency": 5, "team_familiarity": 5}, "note": "ACID, SQL"},
        {"name": "DynamoDB", "scores": {"consistency": 3, "team_familiarity": 2}, "note": "Scale, NoSQL"}
    ],
    "axes": [
        {"name": "consistency", "weight": 0.6},
        {"name": "team_familiarity", "weight": 0.4}
    ],
    "recommendation": "Postgres — ACID required for billing"
}
</json>"""
    )
    with patch("core.engine.canvas.framework_renderer.get_llm", return_value=fake):
        yield fake

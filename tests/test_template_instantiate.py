# tests/test_template_instantiate.py
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_instantiate_substitutes_variables():
    """All {{var}} placeholders in milestone/work_item templates are replaced."""
    from core.engine.templates.instantiate import instantiate_template

    playbook = {
        "id": "playbook:qbr",
        "name": "QBR Prep",
        "description": "QBR for {{customer_name}}",
        "domain_path": "business.operations",
        "variables": [
            {"name": "customer_name", "type": "string", "prompt": "Customer?"},
            {"name": "quarter", "type": "string", "prompt": "Quarter?"},
        ],
        "milestones": [
            {
                "title": "M1: {{customer_name}} data pull for {{quarter}}",
                "done_criteria": ["Data pulled for {{customer_name}}"],
                "work_items": [
                    {
                        "title": "Pull revenue for {{customer_name}}",
                        "archetype": "executor",
                        "mode": "procedural",
                        "domain_path": "business.finance",
                    },
                ],
            },
        ],
    }
    variables = {"customer_name": "Acme Corp", "quarter": "Q2 2026"}

    with patch("core.engine.templates.instantiate.pool") as mock_pool:
        mock_conn = AsyncMock()
        created_initiative = None

        async def track_create(query_str, params=None):
            nonlocal created_initiative
            if "CREATE initiative" in query_str:
                created_initiative = params
                return [[{"id": "initiative:inst1", "source": "template", "title": "QBR Prep"}]]
            if "UPDATE playbook" in query_str:
                return [[]]
            return [[]]

        mock_conn.query = track_create
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await instantiate_template(
            playbook=playbook, variables=variables, user_id="user:ed", product_id="product:default"
        )

    assert created_initiative is not None
    milestones = created_initiative.get("milestones", [])
    assert "Acme Corp" in milestones[0]["title"]
    assert "Q2 2026" in milestones[0]["title"]
    assert "{{customer_name}}" not in milestones[0]["title"]
    assert "Acme Corp" in milestones[0]["work_items"][0]["title"]


@pytest.mark.asyncio
async def test_instantiate_creates_initiative_with_template_source():
    """Instantiation creates an initiative with source='template'."""
    from core.engine.templates.instantiate import instantiate_template

    playbook = {
        "id": "playbook:simple",
        "name": "Simple template",
        "description": "Test",
        "domain_path": "architecture",
        "variables": [],
        "milestones": [{"title": "M1: Do the thing", "done_criteria": ["Done"], "work_items": []}],
    }

    with patch("core.engine.templates.instantiate.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[[{"id": "initiative:inst2", "source": "template", "playbook": "playbook:simple"}]]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await instantiate_template(
            playbook=playbook, variables={}, user_id="user:ed", product_id="product:default"
        )

    assert result["source"] == "template"


@pytest.mark.asyncio
async def test_instantiate_missing_variable_raises():
    """Missing required variable raises TemplateVariableError."""
    from core.engine.templates.instantiate import TemplateVariableError, instantiate_template

    playbook = {
        "id": "playbook:req",
        "name": "Required vars",
        "description": "Test",
        "domain_path": "architecture",
        "variables": [{"name": "required_var", "type": "string", "prompt": "Value?"}],
        "milestones": [],
    }

    with pytest.raises(TemplateVariableError):
        await instantiate_template(playbook=playbook, variables={}, user_id="user:ed", product_id="product:default")


@pytest.mark.asyncio
async def test_instantiate_uses_default_variable():
    """Variables with defaults are used when not provided."""
    from core.engine.templates.instantiate import instantiate_template

    playbook = {
        "id": "playbook:def",
        "name": "With defaults",
        "description": "For {{env}}",
        "domain_path": "architecture",
        "variables": [{"name": "env", "type": "string", "prompt": "Environment?", "default": "staging"}],
        "milestones": [{"title": "Deploy to {{env}}", "done_criteria": [], "work_items": []}],
    }

    with patch("core.engine.templates.instantiate.pool") as mock_pool:
        mock_conn = AsyncMock()
        created = None

        async def track(query_str, params=None):
            nonlocal created
            if "CREATE initiative" in query_str:
                created = params
                return [[{"id": "initiative:def1", "source": "template"}]]
            return [[]]

        mock_conn.query = track
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await instantiate_template(playbook=playbook, variables={}, user_id="user:ed", product_id="product:default")

    assert "staging" in created["milestones"][0]["title"]

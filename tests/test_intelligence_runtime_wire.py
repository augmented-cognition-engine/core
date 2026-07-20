# tests/test_intelligence_runtime_wire.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.runtime import Runtime
from core.engine.runtime.model_adapter import MockAdapter
from core.engine.runtime.models import AssistantMessage


@pytest.mark.asyncio
async def test_runtime_with_code_context():
    runtime = Runtime(
        adapter=MockAdapter(responses=["I see the auth module."]),
        enable_intelligence=True,
    )
    with patch.object(runtime._intelligence, "classify_and_load", new_callable=AsyncMock) as mock_cl:
        mock_cl.return_value = ({"discipline": "security", "specialties": []}, "")
        with patch.object(runtime._intelligence, "load_code_context", new_callable=AsyncMock) as mock_cc:
            mock_cc.return_value = "## Relevant Files\n- engine/auth/validate.py"
            msgs = [msg async for msg in runtime.chat("fix the auth bug")]
            mock_cc.assert_called_once()
            assistants = [m for m in msgs if isinstance(m, AssistantMessage)]
            assert len(assistants) == 1


@pytest.mark.asyncio
async def test_runtime_code_context_in_system_prompt():
    """Verify code_context is included in the assembled system prompt."""
    runtime = Runtime(
        adapter=MockAdapter(responses=["Done."]),
        enable_intelligence=True,
    )
    captured_systems = []

    original_assemble = runtime._assemble_system_prompt

    def capture_assemble(**kwargs):
        result = original_assemble(**kwargs)
        captured_systems.append(result)
        return result

    with patch.object(runtime, "_assemble_system_prompt", side_effect=capture_assemble):
        with patch.object(runtime._intelligence, "classify_and_load", new_callable=AsyncMock) as mock_cl:
            mock_cl.return_value = ({"discipline": "security", "specialties": []}, "")
            with patch.object(runtime._intelligence, "load_code_context", new_callable=AsyncMock) as mock_cc:
                mock_cc.return_value = "## Relevant Files\n- engine/auth/validate.py"
                _ = [msg async for msg in runtime.chat("fix the auth bug")]

    assert len(captured_systems) >= 1
    assert "# Code Context" in captured_systems[0]
    assert "engine/auth/validate.py" in captured_systems[0]


@pytest.mark.asyncio
async def test_runtime_code_context_skipped_when_empty():
    """When load_code_context returns empty string, # Code Context is not injected."""
    runtime = Runtime(
        adapter=MockAdapter(responses=["Done."]),
        enable_intelligence=True,
    )
    captured_systems = []

    original_assemble = runtime._assemble_system_prompt

    def capture_assemble(**kwargs):
        result = original_assemble(**kwargs)
        captured_systems.append(result)
        return result

    with patch.object(runtime, "_assemble_system_prompt", side_effect=capture_assemble):
        with patch.object(runtime._intelligence, "classify_and_load", new_callable=AsyncMock) as mock_cl:
            mock_cl.return_value = ({"discipline": "security", "specialties": []}, "")
            with patch.object(runtime._intelligence, "load_code_context", new_callable=AsyncMock) as mock_cc:
                mock_cc.return_value = ""
                _ = [msg async for msg in runtime.chat("fix the auth bug")]

    assert len(captured_systems) >= 1
    assert "# Code Context" not in captured_systems[0]

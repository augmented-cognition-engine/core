import asyncio
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_watcher_detects_file_change():
    from core.engine.live.file_watcher import FileWatcher

    mock_tracker = AsyncMock()
    mock_tracker.claim_file = AsyncMock(return_value={"state": "claimed"})

    watcher = FileWatcher(
        project_root="/tmp/test-project",
        session_id="agent_session:test",
        product_id="product:platform",
        edit_tracker=mock_tracker,
        path_to_id_cache={"foo.py": "graph_file:foo"},
    )

    watcher._on_file_changed("/tmp/test-project/foo.py")
    await asyncio.sleep(0.2)
    await watcher._flush_pending()

    mock_tracker.claim_file.assert_called_once()


@pytest.mark.asyncio
async def test_watcher_resolves_relative_path():
    from core.engine.live.file_watcher import FileWatcher

    mock_tracker = AsyncMock()
    mock_tracker.claim_file = AsyncMock(return_value={"state": "claimed"})

    watcher = FileWatcher(
        project_root="/tmp/test-project",
        session_id="agent_session:test",
        product_id="product:platform",
        edit_tracker=mock_tracker,
        path_to_id_cache={"engine/core/auth.py": "graph_file:auth"},
    )

    watcher._on_file_changed("/tmp/test-project/engine/core/auth.py")
    await asyncio.sleep(0.2)
    await watcher._flush_pending()

    mock_tracker.claim_file.assert_called_once()
    call_kwargs = mock_tracker.claim_file.call_args
    assert call_kwargs[1]["file_id"] == "graph_file:auth" or call_kwargs.kwargs.get("file_id") == "graph_file:auth"


def test_watcher_filters_noise():
    from core.engine.live.file_watcher import FileWatcher

    watcher = FileWatcher(
        project_root="/tmp/test",
        session_id="s:1",
        product_id="product:platform",
        edit_tracker=None,
        path_to_id_cache={},
    )

    assert watcher._should_ignore("/tmp/test/.git/objects/abc") is True
    assert watcher._should_ignore("/tmp/test/__pycache__/foo.pyc") is True
    assert watcher._should_ignore("/tmp/test/node_modules/pkg/index.js") is True
    assert watcher._should_ignore("/tmp/test/engine/core/auth.py") is False


@pytest.mark.asyncio
async def test_watcher_debounces():
    from core.engine.live.file_watcher import FileWatcher

    mock_tracker = AsyncMock()
    mock_tracker.claim_file = AsyncMock(return_value={"state": "claimed"})

    watcher = FileWatcher(
        project_root="/tmp/test",
        session_id="s:1",
        product_id="product:platform",
        edit_tracker=mock_tracker,
        path_to_id_cache={"foo.py": "graph_file:foo"},
        debounce_ms=100,
    )

    # Rapid-fire same file
    watcher._on_file_changed("/tmp/test/foo.py")
    watcher._on_file_changed("/tmp/test/foo.py")
    watcher._on_file_changed("/tmp/test/foo.py")

    await asyncio.sleep(0.2)
    await watcher._flush_pending()

    # Should only claim once despite 3 events
    assert mock_tracker.claim_file.call_count == 1

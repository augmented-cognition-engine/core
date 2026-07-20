"""Tests for engine/worker/fs_watcher.py

Uses a temp directory and verifies the watcher debounces and posts to /observe.
The watcher calls localhost:37778/observe via httpx; we mock the httpx.AsyncClient.
"""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_fs_watcher_posts_on_file_create(tmp_path):
    """Creating a file in the watched dir should trigger a POST to /observe."""
    from core.engine.worker.fs_watcher import FileChangeHandler

    posted = []

    async def fake_post(payload: dict) -> None:
        posted.append(payload)

    handler = FileChangeHandler(
        watch_dir=str(tmp_path),
        product_id="product:platform",
        post_fn=fake_post,
        debounce_seconds=0.05,
    )

    test_file = tmp_path / "hello.py"
    test_file.write_text("# test")

    # Simulate a file created event
    from watchdog.events import FileCreatedEvent

    event = FileCreatedEvent(str(test_file))
    handler.on_created(event)

    # Wait for debounce
    await asyncio.sleep(0.2)
    await handler.flush()

    assert len(posted) >= 1
    assert posted[0]["event_type"] == "fs.file.created"
    assert "hello.py" in posted[0]["payload"]["path"]


@pytest.mark.asyncio
async def test_fs_watcher_excludes_dotgit(tmp_path):
    """Events from .git/ paths must be silently ignored."""
    from core.engine.worker.fs_watcher import FileChangeHandler

    posted = []

    async def fake_post(payload: dict) -> None:
        posted.append(payload)

    handler = FileChangeHandler(
        watch_dir=str(tmp_path),
        product_id="product:platform",
        post_fn=fake_post,
        debounce_seconds=0.05,
    )

    from watchdog.events import FileCreatedEvent

    git_file = tmp_path / ".git" / "COMMIT_EDITMSG"
    event = FileCreatedEvent(str(git_file))
    handler.on_created(event)

    await asyncio.sleep(0.2)
    await handler.flush()

    assert posted == [], ".git events must be excluded"


def test_fs_watcher_excluded_paths():
    """Verify the exclusion predicate covers all documented paths."""
    from core.engine.worker.fs_watcher import is_excluded

    assert is_excluded("/project/.git/HEAD")
    assert is_excluded("/project/venv/lib/something.py")
    assert is_excluded("/project/__pycache__/mod.cpython-312.pyc")
    assert is_excluded("/project/node_modules/pkg/index.js")
    assert is_excluded("/project/build/main.pyc")
    assert not is_excluded("/project/engine/worker/processor.py")
    assert not is_excluded("/project/portal/src/App.tsx")


# ---------------------------------------------------------------------------
# _classify_discipline tests
# ---------------------------------------------------------------------------


def test_classify_discipline_py_api():
    from core.engine.worker.fs_watcher import _classify_discipline

    disc, conf = _classify_discipline("/project/engine/api/routes.py", "py")
    assert disc == "api_design"
    assert conf >= 0.5


def test_classify_discipline_py_model():
    from core.engine.worker.fs_watcher import _classify_discipline

    disc, conf = _classify_discipline("/project/engine/product/model.py", "py")
    assert disc == "data_modeling"
    assert conf >= 0.5


def test_classify_discipline_py_auth():
    from core.engine.worker.fs_watcher import _classify_discipline

    disc, conf = _classify_discipline("/project/engine/auth/jwt.py", "py")
    assert disc == "security"
    assert conf >= 0.5


def test_classify_discipline_py_generic():
    from core.engine.worker.fs_watcher import _classify_discipline

    disc, conf = _classify_discipline("/project/engine/orchestrator/runner.py", "py")
    assert disc == "architecture"
    assert conf == 0.5


def test_classify_discipline_md():
    from core.engine.worker.fs_watcher import _classify_discipline

    disc, conf = _classify_discipline("/project/docs/design.md", "md")
    assert disc == "documentation"
    assert conf >= 0.5


def test_classify_discipline_ts_ui():
    from core.engine.worker.fs_watcher import _classify_discipline

    disc, conf = _classify_discipline("/project/portal/src/ui/Button.tsx", "tsx")
    assert disc == "ux"
    assert conf >= 0.5


def test_classify_discipline_surql():
    from core.engine.worker.fs_watcher import _classify_discipline

    disc, conf = _classify_discipline("/project/schema/v095.surql", "surql")
    assert disc == "data_modeling"
    assert conf >= 0.5


def test_classify_discipline_test_file_excluded():
    """Test files should return (None, 0.0) even if the extension matches."""
    from core.engine.worker.fs_watcher import _classify_discipline

    disc, conf = _classify_discipline("/project/tests/test_api.py", "py")
    assert disc is None
    assert conf == 0.0


# ---------------------------------------------------------------------------
# _is_test_file tests
# ---------------------------------------------------------------------------


def test_is_test_file():
    from core.engine.worker.fs_watcher import _is_test_file

    assert _is_test_file("/project/tests/test_api.py")
    assert _is_test_file("/project/engine/test_api.py")
    assert _is_test_file("/project/portal/src/Button.test.tsx")
    assert not _is_test_file("/project/engine/api/routes.py")
    assert not _is_test_file("/project/engine/worker/processor.py")
    # pytest temp dirs must NOT be treated as test files (basename-only check avoids false positives)
    assert not _is_test_file("/tmp/pytest-of-edwin/pytest-61/test_fs_watcher_emits_canvas_c0/api/routes.py")


# ---------------------------------------------------------------------------
# canvas.code.edited emit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fs_watcher_emits_canvas_code_edited(tmp_path):
    """_fire should emit canvas.code.edited for a confident discipline mapping."""
    from core.engine.events import bus as real_bus
    from core.engine.worker.fs_watcher import FileChangeHandler

    emitted = []

    async def capture(event_type, payload):
        if event_type == "canvas.code.edited":
            emitted.append(payload)

    real_bus.on("canvas.code.edited", capture)

    posted = []

    async def fake_post(payload: dict) -> None:
        posted.append(payload)

    handler = FileChangeHandler(
        watch_dir=str(tmp_path),
        product_id="product:platform",
        post_fn=fake_post,
        debounce_seconds=0.05,
    )

    # An API file should get a confident discipline mapping
    api_file = tmp_path / "api" / "routes.py"
    api_file.parent.mkdir(parents=True)
    api_file.write_text("# routes")

    tasks_before = asyncio.all_tasks()
    await handler._fire(str(api_file), "modified")
    # Only drain the NEW tasks created by _fire (avoids session-loop pollution).
    new_tasks = asyncio.all_tasks() - tasks_before - {asyncio.current_task()}
    if new_tasks:
        await asyncio.gather(*new_tasks, return_exceptions=True)

    real_bus.off("canvas.code.edited", capture)

    assert len(emitted) >= 1
    assert emitted[0]["discipline"] is not None
    assert emitted[0]["product_id"] == "product:platform"
    assert emitted[0]["is_test_file"] is False


@pytest.mark.asyncio
async def test_fs_watcher_does_not_emit_for_test_files(tmp_path):
    """canvas.code.edited must NOT be emitted for test files."""
    from core.engine.events import bus as real_bus
    from core.engine.worker.fs_watcher import FileChangeHandler

    emitted = []

    async def capture(event_type, payload):
        if event_type == "canvas.code.edited":
            emitted.append(payload)

    real_bus.on("canvas.code.edited", capture)

    posted = []

    async def fake_post(payload: dict) -> None:
        posted.append(payload)

    handler = FileChangeHandler(
        watch_dir=str(tmp_path),
        product_id="product:platform",
        post_fn=fake_post,
        debounce_seconds=0.05,
    )

    test_file = tmp_path / "tests" / "test_api.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("# test")

    tasks_before = asyncio.all_tasks()
    await handler._fire(str(test_file), "modified")
    new_tasks = asyncio.all_tasks() - tasks_before - {asyncio.current_task()}
    if new_tasks:
        await asyncio.gather(*new_tasks, return_exceptions=True)

    real_bus.off("canvas.code.edited", capture)

    assert emitted == [], "canvas.code.edited must not be emitted for test files"


@pytest.mark.asyncio
async def test_fs_watcher_does_not_emit_for_deleted_events(tmp_path):
    """canvas.code.edited must NOT be emitted for deleted events."""
    from core.engine.events import bus as real_bus
    from core.engine.worker.fs_watcher import FileChangeHandler

    emitted = []

    async def capture(event_type, payload):
        if event_type == "canvas.code.edited":
            emitted.append(payload)

    real_bus.on("canvas.code.edited", capture)

    posted = []

    async def fake_post(payload: dict) -> None:
        posted.append(payload)

    handler = FileChangeHandler(
        watch_dir=str(tmp_path),
        product_id="product:platform",
        post_fn=fake_post,
        debounce_seconds=0.05,
    )

    api_file = tmp_path / "api" / "routes.py"
    api_file.parent.mkdir(parents=True)
    # File doesn't exist — simulating delete

    tasks_before = asyncio.all_tasks()
    await handler._fire(str(api_file), "deleted")
    new_tasks = asyncio.all_tasks() - tasks_before - {asyncio.current_task()}
    if new_tasks:
        await asyncio.gather(*new_tasks, return_exceptions=True)

    real_bus.off("canvas.code.edited", capture)

    assert emitted == [], "canvas.code.edited must not be emitted for deleted events"

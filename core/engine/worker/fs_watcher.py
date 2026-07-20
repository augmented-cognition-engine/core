# engine/worker/fs_watcher.py
"""File system watcher — posts file change observations to /observe.

Watches CLAUDE_PROJECT_DIR for file changes outside Claude Code hooks.
Closes the observation gap for edits in other editors, git operations,
and shell commands that hooks don't capture.

Architecture:
- Uses watchdog.observers.Observer (already a project dep, verified).
- FileChangeHandler debounces events (500ms quiet window by default).
- Excluded: .git/, venv/, .venv/, node_modules/, __pycache__, *.pyc, *.swp
- Calls /observe with a synthetic payload (source='fs_watcher').
- Runs as a background task in the FastAPI worker lifespan.
- Emits canvas.code.edited when a file edit has a confident discipline mapping.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Coroutine

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# Paths (or path fragments) that should never trigger observations.
_EXCLUDED_FRAGMENTS = (
    "/.git/",
    "/.git",
    "/venv/",
    "/.venv/",
    "/node_modules/",
    "/__pycache__/",
    "/__pycache__",
)
_EXCLUDED_SUFFIXES = (".pyc", ".swp", ".swo", ".tmp")

_DEFAULT_DEBOUNCE = 0.5  # seconds

_TEST_DIR_FRAGMENTS = ("/test/", "/tests/", "/spec/")
_TEST_BASENAME_FRAGMENTS = ("test_", "_test.", ".test.", "_spec.")


def _is_test_file(path: str) -> bool:
    """Return True if this path is a test file (should be excluded from code.edited).

    Checks directory-level fragments against the full path, and filename-level
    fragments against the basename only — avoids false positives from pytest's
    own temp directories (e.g. /tmp/pytest-of-user/test_foo0/).
    """
    p = path.lower()
    basename = Path(path).name.lower()
    if any(frag in p for frag in _TEST_DIR_FRAGMENTS):
        return True
    return any(frag in basename for frag in _TEST_BASENAME_FRAGMENTS)


def _classify_discipline(path: str, ext: str) -> tuple[str | None, float]:
    """Heuristic path → discipline classifier.

    Returns (discipline, confidence). confidence < 0.5 means the classifier
    is uncertain and canvas.code.edited should NOT be emitted.
    """
    p = path.lower()
    # Test files are excluded — too noisy
    if _is_test_file(p):
        return None, 0.0

    if ext in ("py",):
        if "auth" in p or "security" in p:
            return "security", 0.8
        if "model" in p or "schema" in p or "db" in p:
            return "data_modeling", 0.7
        if "api" in p:
            return "api_design", 0.7
        if "engine/voice" in p:
            return "ux", 0.6
        if "engine/sentinel" in p:
            return "observability", 0.6
        return "architecture", 0.5
    if ext in ("md",):
        return "documentation", 0.7
    if ext in ("ts", "tsx", "js", "jsx"):
        if "ui" in p or "component" in p:
            return "ux", 0.7
        return "api_design", 0.5
    if ext in ("surql", "sql"):
        return "data_modeling", 0.8
    return None, 0.0


def is_excluded(path: str) -> bool:
    """Return True if this path should be ignored by the watcher."""
    for fragment in _EXCLUDED_FRAGMENTS:
        if fragment in path:
            return True
    for suffix in _EXCLUDED_SUFFIXES:
        if path.endswith(suffix):
            return True
    return False


PostFn = Callable[[dict], Coroutine]


class FileChangeHandler(FileSystemEventHandler):
    """Debouncing file-system event handler.

    Accepts an async `post_fn` coroutine factory so the handler is testable
    without a running HTTP server — tests inject a fake_post; production
    injects _post_observation.
    """

    def __init__(
        self,
        watch_dir: str,
        product_id: str,
        post_fn: PostFn,
        debounce_seconds: float = _DEFAULT_DEBOUNCE,
    ) -> None:
        super().__init__()
        self.watch_dir = watch_dir
        self.product_id = product_id
        self.post_fn = post_fn
        self.debounce_seconds = debounce_seconds
        # pending: map from abs_path → (event_type_str, timer_handle)
        self._pending: dict[str, tuple[str, asyncio.TimerHandle | None]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop | None:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def _schedule(self, path: str, event_kind: str) -> None:
        """Schedule a debounced post for `path`."""
        loop = self._get_loop()
        if loop is None:
            # No running loop — use asyncio.run for the flush (fallback for tests)
            asyncio.ensure_future(self._fire(path, event_kind))
            return

        # Cancel existing timer if any
        existing = self._pending.get(path)
        if existing and existing[1] is not None:
            existing[1].cancel()

        handle = loop.call_later(
            self.debounce_seconds,
            lambda: asyncio.ensure_future(self._fire(path, event_kind), loop=loop),
        )
        self._pending[path] = (event_kind, handle)

    async def _fire(self, path: str, event_kind: str) -> None:
        """Emit the observation for `path`."""
        self._pending.pop(path, None)
        rel_path = os.path.relpath(path, self.watch_dir)
        ext = Path(path).suffix.lstrip(".").lower() or "unknown"
        try:
            size: int | None = os.path.getsize(path) if os.path.exists(path) else None
        except OSError:
            size = None

        payload = {
            "source": "fs_watcher",
            "event_type": f"fs.file.{event_kind}",
            "session_id": None,
            "product_id": self.product_id,
            "payload": {
                "path": rel_path,
                "absolute_path": path,
                "size_bytes": size,
                "ext": ext,
            },
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.post_fn(payload)
        except Exception as exc:
            logger.warning("fs_watcher: post_fn failed for %s: %s", path, exc)

        # Emit canvas.code.edited when the classifier produces a confident discipline
        if event_kind in ("created", "modified"):
            discipline, confidence = _classify_discipline(path, ext)
            if discipline and confidence >= 0.5 and not _is_test_file(path):
                try:
                    from core.engine.events.bus import bus

                    await bus.emit(
                        "canvas.code.edited",
                        {
                            "product_id": self.product_id,
                            "path": rel_path,
                            "discipline": discipline,
                            "discipline_confidence": confidence,
                            "size_bytes": size,
                            "is_test_file": False,
                        },
                    )
                except Exception as exc:
                    logger.debug("fs_watcher: canvas.code.edited emit failed: %s", exc)

    async def flush(self) -> None:
        """Fire all pending debounced events immediately (for tests / shutdown)."""
        pending = list(self._pending.items())
        for path, (event_kind, handle) in pending:
            if handle is not None:
                handle.cancel()
            self._pending.pop(path, None)
            await self._fire(path, event_kind)

    def _handle(self, path: str, event_kind: str) -> None:
        if is_excluded(path):
            return
        self._schedule(path, event_kind)

    def on_created(self, event) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(event.src_path, "created")

    def on_modified(self, event) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(event.src_path, "modified")

    def on_deleted(self, event) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(event.src_path, "deleted")


async def _post_observation(payload: dict) -> None:
    """POST the synthetic payload to the local /observe endpoint."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "http://localhost:37778/observe",
                json={
                    "content": (f"[fs_watcher] {payload['event_type']}: {payload['payload']['path']}"),
                    "type": "pattern",
                    "domain_path": "general",
                    "confidence": 0.6,
                    "source": "fs_watcher",
                    "product_id": payload["product_id"],
                    "file_path": payload["payload"]["absolute_path"],
                },
            )
            if resp.status_code != 200:
                logger.warning("fs_watcher: /observe returned %d", resp.status_code)
    except Exception as exc:
        logger.debug("fs_watcher: /observe post failed (non-fatal): %s", exc)


async def run_fs_watcher(
    watch_dir: str | None = None,
    product_id: str = "product:platform",
) -> None:
    """Start the watchdog Observer and run until cancelled.

    Designed to be launched as an asyncio background task in the FastAPI lifespan.
    """
    dir_to_watch = watch_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    handler = FileChangeHandler(
        watch_dir=dir_to_watch,
        product_id=product_id,
        post_fn=_post_observation,
        debounce_seconds=_DEFAULT_DEBOUNCE,
    )

    observer = Observer()
    observer.schedule(handler, dir_to_watch, recursive=True)
    observer.start()
    logger.info("fs_watcher: watching %s", dir_to_watch)

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("fs_watcher: shutting down")
        await handler.flush()
        observer.stop()
        observer.join()
        raise

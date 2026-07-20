"""Filesystem watcher — monitors project directory during agent execution.

Wraps watchdog to detect file changes in real-time. Maps filesystem events
to EditTracker.claim_file() calls. Debounces rapid writes (100ms window).
Filters noise (.git, __pycache__, node_modules, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
_IGNORE_EXTENSIONS = {".pyc", ".pyo", ".so", ".o", ".dylib"}
_MAX_FILE_SIZE = 1_000_000


class FileWatcher:
    """Watches project directory for file changes during an agent session."""

    def __init__(
        self,
        project_root: str,
        session_id: str,
        product_id: str,
        edit_tracker,
        path_to_id_cache: dict[str, str],
        debounce_ms: int = 100,
    ):
        self._root = project_root
        self._session_id = session_id
        self._org_id = product_id
        self._tracker = edit_tracker
        self._cache = path_to_id_cache
        self._debounce_ms = debounce_ms
        self._observer = None
        self._pending: dict[str, float] = {}
        self._flush_task: asyncio.Task | None = None
        self._running = False

    def _should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored."""
        parts = Path(path).parts
        for part in parts:
            if part in _IGNORE_DIRS:
                return True
        ext = os.path.splitext(path)[1]
        if ext in _IGNORE_EXTENSIONS:
            return True
        try:
            if os.path.isfile(path) and os.path.getsize(path) > _MAX_FILE_SIZE:
                return True
        except OSError:
            pass
        return False

    def _on_file_changed(self, path: str) -> None:
        """Called by watchdog handler. Debounces before tracking."""
        if self._should_ignore(path):
            return
        self._pending[path] = time.monotonic()

    async def _flush_pending(self) -> None:
        """Process pending file changes after debounce window."""
        if not self._pending or not self._tracker:
            return

        now = time.monotonic()
        threshold = self._debounce_ms / 1000.0
        ready = {p: t for p, t in self._pending.items() if (now - t) >= threshold}

        for path in ready:
            del self._pending[path]
            file_id = self._cache.get(path)
            if not file_id:
                try:
                    rel = os.path.relpath(path, self._root)
                    file_id = self._cache.get(rel)
                except ValueError:
                    pass

            if not file_id:
                continue

            try:
                await self._tracker.claim_file(
                    product_id=self._org_id,
                    session_id=self._session_id,
                    file_id=file_id,
                )
            except Exception as exc:
                logger.debug("Watcher claim failed for %s: %s", path, exc)

    async def _flush_loop(self) -> None:
        """Background loop that flushes pending changes."""
        while self._running:
            await self._flush_pending()
            await asyncio.sleep(0.15)

    def start(self) -> None:
        """Start watching the project directory."""
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            watcher = self

            class _Handler(FileSystemEventHandler):
                def on_modified(self, event):
                    if not event.is_directory:
                        watcher._on_file_changed(event.src_path)

                def on_created(self, event):
                    if not event.is_directory:
                        watcher._on_file_changed(event.src_path)

            self._observer = Observer()
            self._observer.schedule(_Handler(), self._root, recursive=True)
            self._observer.start()
            self._running = True
            self._flush_task = asyncio.ensure_future(self._flush_loop())
            logger.info("File watcher started on %s for session %s", self._root, self._session_id)
        except ImportError:
            logger.warning("watchdog not installed — file watcher disabled")
        except Exception as exc:
            logger.warning("Failed to start file watcher: %s", exc)

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        logger.info("File watcher stopped for session %s", self._session_id)

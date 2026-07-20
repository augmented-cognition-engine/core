# engine/scanner/commit_watcher.py
"""Commit Watcher — poll for new git commits and trigger incremental capability mapping.

Runs as a background task in the FastAPI lifespan. Checks for new commits
every poll_interval seconds. When found, triggers the existing scanner's
incremental scan + capability mapper.
"""

import asyncio
import logging
import subprocess

logger = logging.getLogger(__name__)


class CommitWatcher:
    """Poll for new commits, trigger incremental scan + capability mapping."""

    def __init__(self, repo_path: str, poll_interval: int = 300):
        self._repo_path = repo_path
        self._poll_interval = poll_interval  # seconds (default 5 min)
        self._last_sha = None
        self._running = False
        self._task = None

    def _get_head_sha(self) -> str | None:
        """Get the current HEAD commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            logger.warning(f"Failed to get HEAD SHA: {e}")
            return None

    def _get_changed_files(self, from_sha: str, to_sha: str) -> list[str]:
        """Get list of files changed between two commits."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", from_sha, to_sha],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return [f for f in result.stdout.strip().split("\n") if f]
            return []
        except Exception as e:
            logger.warning(f"Failed to get changed files: {e}")
            return []

    async def start(self):
        """Start polling for commits."""
        self._running = True
        self._last_sha = self._get_head_sha()
        logger.info(
            f"CommitWatcher started. Repo: {self._repo_path}, Poll: {self._poll_interval}s, HEAD: {self._last_sha}"
        )
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        """Stop polling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CommitWatcher stopped")

    async def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                await self._check_for_changes()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"CommitWatcher poll error: {e}")

    async def _check_for_changes(self):
        """Check if HEAD has changed since last poll."""
        current_sha = self._get_head_sha()
        if not current_sha or current_sha == self._last_sha:
            return

        logger.info(f"New commits detected: {self._last_sha[:8]}..{current_sha[:8]}")
        changed_files = self._get_changed_files(self._last_sha, current_sha)
        logger.info(f"Changed files: {len(changed_files)}")

        try:
            from core.engine.events.bus import bus

            await bus.emit(
                "commit.detected",
                {
                    "product_id": "product:platform",
                    "from_sha": self._last_sha,
                    "to_sha": current_sha,
                    "changed_files": changed_files,
                    "file_count": len(changed_files),
                },
            )
        except Exception:
            pass

        # Trigger capability mapping for changed files
        try:
            from core.engine.core.db import pool
            from core.engine.product.capability_mapper import CapabilityMapper

            mapper = CapabilityMapper(pool)
            new_files = [{"id": f"graph_file:{f.replace('/', '_')}", "path": f} for f in changed_files]
            if new_files:
                result = await mapper.incremental_map(new_files, "product:platform")
                logger.info(f"Capability mapping: {result}")
        except Exception as e:
            logger.warning(f"Capability mapping failed (non-fatal): {e}")

        # Re-embed changed files
        try:
            from core.engine.scanner.embed_hook import embed_changed_files

            embedded = await embed_changed_files(changed_files, self._repo_path)
            logger.info("Re-embedded %d changed files", embedded)
        except Exception:
            pass

        # Embed function-level nodes for changed files
        try:
            from core.engine.scanner.embed_hook import embed_functions

            fn_count = await embed_functions(self._repo_path)
            if fn_count:
                logger.info("Function embeddings updated: %d", fn_count)
        except Exception:
            pass

        # Security scan on changed files
        try:
            from core.engine.events.bus import bus
            from core.engine.scanner.security_scanner import findings_to_intelligence, scan_files

            findings = await scan_files(changed_files, self._repo_path)
            if findings:
                intel = findings_to_intelligence(findings)
                await bus.emit(
                    "security.scan.complete",
                    {
                        "product_id": "product:platform",
                        "findings_count": len(findings),
                        "severity_breakdown": {
                            s: sum(1 for f in findings if f.severity == s) for s in ("ERROR", "WARNING", "INFO")
                        },
                        "intelligence": intel,
                    },
                )
                logger.info("Security scan: %d findings", len(findings))

                # Emit security findings into capture pipeline
                try:
                    from datetime import datetime, timezone

                    from core.engine.capture.service import capture_service
                    from core.engine.capture.watchers import StreamEvent

                    errors = sum(1 for f in findings if f.severity == "ERROR")
                    warnings = sum(1 for f in findings if f.severity == "WARNING")
                    content = (
                        f"Security scan: {len(findings)} findings in {len(changed_files)} changed files. "
                        f"Errors: {errors}, Warnings: {warnings}.\n"
                        + "\n".join(f"- [{f.severity}] {f.rule}: {f.message} ({f.path})" for f in findings[:10])
                    )
                    await capture_service.emit(
                        StreamEvent(
                            timestamp=datetime.now(timezone.utc),
                            event_type="tool_result",
                            content=content,
                            session_id=f"commit_{current_sha[:12]}",
                            metadata={
                                "product_id": "product:platform",
                                "source": "security_scanner",
                                "discipline_hint": "security",
                            },
                        )
                    )
                except Exception as exc:
                    logger.debug("Capture emit failed for security scan: %s", exc)
        except Exception as exc:
            logger.warning("Security scan failed (non-fatal): %s", exc)

        # Emit commit activity into capture pipeline
        try:
            from datetime import datetime, timezone

            from core.engine.capture.service import capture_service
            from core.engine.capture.watchers import StreamEvent

            content = (
                f"Commit detected: {self._last_sha[:8]}..{current_sha[:8]}. "
                f"{len(changed_files)} files changed: {', '.join(changed_files[:10])}"
            )
            await capture_service.emit(
                StreamEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="tool_result",
                    content=content,
                    session_id=f"commit_{current_sha[:12]}",
                    metadata={
                        "product_id": "product:platform",
                        "source": "commit_watcher",
                        "discipline_hint": "devops",
                    },
                )
            )
        except Exception as exc:
            logger.debug("Capture emit failed for commit: %s", exc)

        # Trigger automated review when new commits land on a feature branch
        try:
            from core.engine.review.watcher import check_and_review

            review_result = await check_and_review(repo_path=self._repo_path)
            if review_result:
                logger.info(
                    "Auto-review complete: %d findings, gate %s",
                    review_result.get("findings_count", 0),
                    "passed" if review_result.get("pass_quality_gate") else "FAILED",
                )
        except Exception as e:
            logger.warning(f"Auto-review failed (non-fatal): {e}")

        self._last_sha = current_sha

    def get_status(self) -> dict:
        """Return current watcher status."""
        return {
            "running": self._running,
            "repo_path": self._repo_path,
            "poll_interval": self._poll_interval,
            "last_sha": self._last_sha,
        }

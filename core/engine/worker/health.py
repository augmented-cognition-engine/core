# engine/worker/health.py
"""Module-level WorkerHealthState singleton — tracks hook pipeline activity.

Updated by app.py endpoints in real time. Exposed via GET /health/status.
Never raises — all methods are safe to call unconditionally.
"""

from __future__ import annotations

import time
from collections import deque

_STALE_THRESHOLD_SECONDS = 30 * 60  # 30 minutes


class WorkerHealthState:
    """In-process health metrics for the ACE worker."""

    def __init__(self) -> None:
        self.worker_start_time: float = time.time()
        self.last_hook_post_at: float | None = None
        self.hook_post_count: int = 0
        self.capture_count: int = 0
        self.last_synthesis_at: float | None = None
        self.last_error: str | None = None
        self.lease_claim_count: int = 0
        self.recovered_lease_count: int = 0
        self.lease_loss_count: int = 0
        self.leased_outcome_count: int = 0
        self.drain_cycle_count: int = 0
        self.last_drain_at: float | None = None
        self.last_lease_loss: str | None = None
        self._leased_outcome_times: deque[float] = deque()

    def record_hook_post(self) -> None:
        self.last_hook_post_at = time.time()
        self.hook_post_count += 1

    def record_capture(self) -> None:
        self.capture_count += 1

    def record_synthesis(self) -> None:
        self.last_synthesis_at = time.time()

    def record_error(self, msg: str) -> None:
        self.last_error = msg[:200]

    def record_lease_claim(self, *, recovered: bool) -> None:
        self.lease_claim_count += 1
        if recovered:
            self.recovered_lease_count += 1

    def record_lease_loss(self, msg: str) -> None:
        self.lease_loss_count += 1
        self.last_lease_loss = msg[:200]

    def record_leased_outcome(self) -> None:
        now = time.time()
        self.leased_outcome_count += 1
        self._leased_outcome_times.append(now)
        self._prune_outcomes(now)

    def record_drain_cycle(self) -> None:
        self.drain_cycle_count += 1
        self.last_drain_at = time.time()

    def _prune_outcomes(self, now: float | None = None) -> None:
        cutoff = (now or time.time()) - 300
        while self._leased_outcome_times and self._leased_outcome_times[0] < cutoff:
            self._leased_outcome_times.popleft()

    @property
    def leased_outcomes_last_5m(self) -> int:
        self._prune_outcomes()
        return len(self._leased_outcome_times)

    @property
    def leased_outcomes_per_minute(self) -> float:
        return round(self.leased_outcomes_last_5m / 5.0, 3)

    @property
    def idle_seconds(self) -> float | None:
        if self.last_hook_post_at is None:
            return None
        return time.time() - self.last_hook_post_at

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.worker_start_time

    @property
    def pipeline_status(self) -> str:
        """Return 'active', 'idle', 'stale', or 'never_used'."""
        if self.last_hook_post_at is None:
            return "never_used"
        idle = self.idle_seconds
        if idle is None:
            return "never_used"
        if idle > _STALE_THRESHOLD_SECONDS:
            return "stale"
        if idle > 60:
            return "idle"
        return "active"


_state = WorkerHealthState()


def get_health_state() -> WorkerHealthState:
    return _state

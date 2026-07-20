"""ExecutionRuntime — runs an ActionPlan with per-action risk-tier enforcement.

MUTATING actions have NO execution code path here — they are recorded as gated and
surfaced for approval, never performed. READ/REVERSIBLE actions run through the
path-confined executors. Fully non-fatal."""

from __future__ import annotations

import logging
import subprocess

from core.engine.arms.base import ActionPlan, ArmResult, RiskTier
from core.engine.arms.execution.executors import ExecutionError, get_executor

logger = logging.getLogger(__name__)


class ExecutionRuntime:
    async def run(self, plan: ActionPlan, workspace) -> ArmResult:
        performed = []
        logs = []
        for action in plan.actions:
            if action.risk == RiskTier.MUTATING:
                logs.append(f"[gated] {action.verb} — surfaced for approval, not performed")
                continue
            executor = get_executor(action.verb)
            if executor is None:
                logs.append(f"[blocked] unknown verb {action.verb}")
                continue
            try:
                out = executor(workspace.path, action.args)
                performed.append(action)
                logs.append(f"[ok] {action.verb}: {out}")
            except ExecutionError as exc:
                logs.append(f"[blocked] {action.verb}: {exc}")
            except Exception as exc:  # non-fatal: capture, keep going
                logs.append(f"[error] {action.verb}: {exc}")
        return ArmResult(plan=plan, performed=performed, simulated=False, logs=logs, workspace=workspace)

    async def run_tests(self, cmd: list[str], workspace, timeout: int = 120) -> tuple[bool, str]:
        """Scoped, read-only validation of the arm's own work (for verify). cwd=workspace."""
        try:
            proc = subprocess.run(cmd, cwd=workspace.path, capture_output=True, text=True, timeout=timeout)
            return proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]
        except subprocess.TimeoutExpired:
            return False, f"timeout after {timeout}s"
        except Exception as exc:
            return False, f"run_tests failed: {exc}"

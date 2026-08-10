from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime

from ace.core import (
    ActionIntentV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    GovernedOperationBindingV1Alpha1,
    canonical_json,
)
from core.engine.core.action_execution import (
    BoundedActionAdapterRegistry,
    build_surreal_governed_action_execution_service,
)
from core.engine.core.db import pool


class _UnusedAuthorizer:
    async def authorize_action(self, request):
        raise AssertionError(f"restart unexpectedly requested authorization: {request}")


class _UnusedAdapter:
    def __init__(self, artifact: CapabilityArtifactIdentityV1Alpha1) -> None:
        self.artifact_identity = artifact
        self.prepare_calls = 0
        self.execute_calls = 0

    async def prepare(self, intent):
        self.prepare_calls += 1
        raise AssertionError(f"restart unexpectedly prepared action: {intent}")

    async def execute(self, plan, authorization):
        self.execute_calls += 1
        raise AssertionError(f"restart unexpectedly executed action: {(plan, authorization)}")


async def main() -> None:
    request = json.loads(sys.stdin.read())
    intent = ActionIntentV1Alpha1.model_validate_json(canonical_json(request["intent"]))
    binding = GovernedOperationBindingV1Alpha1.model_validate_json(canonical_json(request["binding"]))
    adapter = _UnusedAdapter(binding.artifact)
    await pool.init()
    try:
        outcome = await build_surreal_governed_action_execution_service(
            db=pool,
            authorizer=_UnusedAuthorizer(),
            operation_binding=binding,
            adapters=BoundedActionAdapterRegistry((adapter,)),
            clock=lambda: datetime.fromisoformat(request["restarted_at"]),
        ).execute(intent)
        print(
            canonical_json(
                {
                    "disposition": outcome.result.disposition,
                    "effect_state": outcome.result.effect_state,
                    "failure_code": outcome.result.failure_code,
                    "replayed": outcome.replayed,
                    "prepare_calls": adapter.prepare_calls,
                    "execute_calls": adapter.execute_calls,
                    "terminal": outcome.terminal.model_dump(mode="json"),
                }
            )
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

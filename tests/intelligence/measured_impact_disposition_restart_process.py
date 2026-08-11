from __future__ import annotations

import asyncio
import json
import sys

from ace.application import (
    MeasuredImpactDispositionRequestV1Alpha1,
    MeasuredImpactDispositionService,
)
from ace.core import GovernedOperationBindingV1Alpha1, canonical_json
from core.engine.core.db import pool
from core.engine.core.immutable_records import SurrealImmutableRecordStore


class _UnusedAuthorizer:
    async def authorize_action(self, request):
        raise AssertionError(f"historical disposition replay requested authority: {request.authorization_key}")


async def main() -> None:
    payload = json.loads(sys.stdin.read())
    await pool.init()
    try:
        admission = await MeasuredImpactDispositionService(
            store=SurrealImmutableRecordStore(pool),
            authorizer=_UnusedAuthorizer(),
            operation_binding=GovernedOperationBindingV1Alpha1.model_validate_json(
                json.dumps(payload["operation_binding"])
            ),
        ).decide(MeasuredImpactDispositionRequestV1Alpha1.model_validate_json(json.dumps(payload["request"])))
        if not admission.replayed:
            raise RuntimeError("fresh process appended a disposition instead of replaying history")
        print(
            canonical_json(
                {
                    "decision": admission.decision.model_dump(mode="json"),
                    "transaction": admission.transaction_receipt.model_dump(mode="json"),
                }
            )
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

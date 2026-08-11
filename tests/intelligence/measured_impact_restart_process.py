from __future__ import annotations

import asyncio
import json
import sys

from ace.application import MeasuredImpactService
from ace.core import GovernedOperationBindingV1Alpha1, canonical_json
from ace.intelligence import ImpactEvaluationRequestV1Alpha1
from core.engine.core.db import pool
from core.engine.core.immutable_records import SurrealImmutableRecordStore


class _UnusedAuthorizer:
    async def authorize_action(self, request):
        raise AssertionError(f"historical replay unexpectedly requested authority: {request.request_id}")


async def main() -> None:
    payload = json.loads(sys.stdin.read())
    await pool.init()
    try:
        admission = await MeasuredImpactService(
            store=SurrealImmutableRecordStore(pool),
            authorizer=_UnusedAuthorizer(),
            operation_binding=GovernedOperationBindingV1Alpha1.model_validate_json(
                json.dumps(payload["operation_binding"])
            ),
        ).evaluate(ImpactEvaluationRequestV1Alpha1.model_validate_json(json.dumps(payload["request"])))
        if not admission.replayed:
            raise RuntimeError("fresh process recomputed measured impact instead of replaying history")
        print(
            canonical_json(
                {
                    "evaluation": admission.evaluation.model_dump(mode="json"),
                    "proposal": admission.proposal.model_dump(mode="json") if admission.proposal else None,
                    "transaction": admission.transaction_receipt.model_dump(mode="json"),
                }
            )
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

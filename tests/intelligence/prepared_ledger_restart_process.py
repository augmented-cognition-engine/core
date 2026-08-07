from __future__ import annotations

import asyncio
import json
import sys

from ace.application import (
    DomainActivationAdmissionService,
    PreparedIntelligenceLedgerService,
    bind_committed_activation,
)
from ace.core import canonical_json
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore


class _UnusedAuthority:
    async def resolve_approval(self, **kwargs):
        raise AssertionError(f"reload unexpectedly resolved approval: {kwargs}")

    async def resolve_grant(self, **kwargs):
        raise AssertionError(f"reload unexpectedly resolved authority: {kwargs}")


async def main() -> None:
    request = json.loads(sys.stdin.read())
    await pool.init()
    try:
        committed = await DomainActivationAdmissionService(
            store=SurrealGovernedStateStore(pool),
            authority=_UnusedAuthority(),
        ).reload(
            product_id=request["product_id"],
            activation_key=request["activation_key"],
        )
        if committed is None:
            raise RuntimeError("fresh process could not reload committed activation")
        pack = CompiledDomainPackV1.model_validate(request["pack"])
        service = PreparedIntelligenceLedgerService(
            binding=bind_committed_activation(pack=pack, committed=committed),
            store=SurrealImmutableRecordStore(pool),
        )
        replay = await service.replay(derivation_key=request["derivation_key"])
        if replay is None:
            raise RuntimeError("fresh process could not replay prepared derivation")
        print(
            canonical_json(
                {
                    "resources": [resource.model_dump(mode="json") for resource in replay.resources],
                    "attention": replay.attention_receipt.model_dump(mode="json"),
                    "transaction": replay.transaction_receipt.model_dump(mode="json"),
                }
            )
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

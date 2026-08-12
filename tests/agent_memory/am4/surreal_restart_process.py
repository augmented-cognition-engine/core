from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from surrealdb import AsyncSurreal

from ace.application.agent_memory_assertions import MemoryGraphProjectionService
from ace.core.agent_memory import AgentMemoryScopeV1Alpha1
from ace.core.agent_memory_lifecycle import (
    DEPENDENCY_SNAPSHOT_RECORD_KIND,
    ERASURE_RECEIPT_RECORD_KIND,
    LIFECYCLE_EVENT_RECORD_KIND,
    LIFECYCLE_RECEIPT_RECORD_KIND,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from tests.agent_memory.am2.test_surreal_am2_restart import _Authority


class _Pool:
    def __init__(self, url: str, namespace: str, database: str) -> None:
        self.url = url
        self.namespace = namespace
        self.database = database

    @asynccontextmanager
    async def connection(self):
        db = AsyncSurreal(self.url)
        await db.connect()
        await db.signin({"username": "root", "password": "root"})
        await db.use(self.namespace, self.database)
        try:
            yield db
        finally:
            await db.close()


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(item for child in value.values() for item in _strings(child))
    if isinstance(value, list):
        return tuple(item for child in value for item in _strings(child))
    return ()


async def main() -> None:
    raw = json.loads(sys.stdin.read())
    scope = AgentMemoryScopeV1Alpha1.model_validate(raw["scope"], strict=False)
    context = AuthenticatedRuntimeContextV1Alpha1.model_validate(raw["context"], strict=False)
    now = datetime.fromisoformat(raw["now"])
    target = raw["target_ref"]
    store = SurrealImmutableRecordStore(_Pool(raw["url"], raw["namespace"], raw["database"]))
    records = await store.scan_product_records(product_id=scope.product_id)
    content_free_kinds = {
        DEPENDENCY_SNAPSHOT_RECORD_KIND,
        ERASURE_RECEIPT_RECORD_KIND,
        LIFECYCLE_EVENT_RECORD_KIND,
        LIFECYCLE_RECEIPT_RECORD_KIND,
    }
    target_in_supported = any(
        record.record_kind not in content_free_kinds and target in _strings(record.payload) for record in records
    )
    projection = await MemoryGraphProjectionService(
        store=store,
        authorization=_Authority(),
        clock=lambda: now,
    ).rebuild(context=context, scope=scope)
    print(
        json.dumps(
            {
                "target_in_supported_records": target_in_supported,
                "target_in_rebuilt_graph": target in projection.model_dump_json(),
                "erasure_receipts": sum(item.record_kind == ERASURE_RECEIPT_RECORD_KIND for item in records),
            },
            sort_keys=True,
        )
    )


asyncio.run(main())

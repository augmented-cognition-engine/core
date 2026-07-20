"""Tool executor — resolves, validates, and runs tools with concurrency control.

Concurrency rules (from Claude Code's StreamingToolExecutor):
- Read-only tools run in parallel
- Write tools run serially (exclusive access)
- Results returned in insertion order regardless of completion order
"""

from __future__ import annotations

import asyncio
import logging

from core.engine.runtime.models import ToolResultMessage, ToolUseBlock
from core.engine.runtime.tools import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Execute tool_use blocks from model responses."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(self, blocks: list[ToolUseBlock]) -> list[ToolResultMessage]:
        """Execute tool blocks with concurrency rules. Returns results in input order."""
        if not blocks:
            return []

        batches = self._partition(blocks)
        results: dict[str, ToolResultMessage] = {}

        for batch in batches:
            if len(batch) == 1 or not all(self._is_read_only(b) for b in batch):
                for block in batch:
                    results[block.id] = await self._execute_one(block)
            else:
                tasks = [self._execute_one(b) for b in batch]
                batch_results = await asyncio.gather(*tasks)
                for block, result in zip(batch, batch_results):
                    results[block.id] = result

        return [results[b.id] for b in blocks]

    def _partition(self, blocks: list[ToolUseBlock]) -> list[list[ToolUseBlock]]:
        """Group consecutive read-only tools into parallel batches."""
        batches: list[list[ToolUseBlock]] = []
        current_batch: list[ToolUseBlock] = []
        current_is_read_only = True

        for block in blocks:
            ro = self._is_read_only(block)
            if ro and current_is_read_only:
                current_batch.append(block)
            else:
                if current_batch:
                    batches.append(current_batch)
                current_batch = [block]
                current_is_read_only = ro

        if current_batch:
            batches.append(current_batch)

        return batches

    def _is_read_only(self, block: ToolUseBlock) -> bool:
        tool = self._registry.get(block.name)
        return tool.is_read_only if tool else False

    async def _execute_one(self, block: ToolUseBlock) -> ToolResultMessage:
        tool = self._registry.get(block.name)
        if not tool:
            return ToolResultMessage(
                tool_use_id=block.id,
                content=f"Error: Unknown tool '{block.name}'",
                is_error=True,
            )
        try:
            result = await tool.execute(block.input)
            return ToolResultMessage(tool_use_id=block.id, content=result, is_error=False)
        except Exception as e:
            logger.exception("Tool %s failed", block.name)
            return ToolResultMessage(tool_use_id=block.id, content=f"Error: {e}", is_error=True)

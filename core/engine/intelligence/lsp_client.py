"""JSON-RPC over stdio client for LSP servers.

Implements the Language Server Protocol transport layer.
Sends requests/notifications, reads responses, manages request IDs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def encode_message(obj: dict) -> bytes:
    """Encode a JSON-RPC message with Content-Length header."""
    body = json.dumps(obj).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def decode_header(data: bytes) -> int:
    """Extract Content-Length from LSP header bytes."""
    for line in data.split(b"\r\n"):
        if line.startswith(b"Content-Length:"):
            return int(line.split(b":")[1].strip())
    raise ValueError("No Content-Length header found")


class LSPClient:
    """JSON-RPC client for a single LSP server process."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self._reader = process.stdout
        self._writer = process.stdin
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._running = False
        self._read_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the message read loop."""
        self._running = True
        self._read_task = asyncio.get_event_loop().create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Continuously read messages from the server."""
        while self._running:
            try:
                message = await self._read_message()
                if message is None:
                    break
                msg_id = message.get("id")
                if msg_id is not None and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if "error" in message:
                        future.set_exception(
                            LSPError(
                                message["error"].get("message", "Unknown LSP error"),
                                message["error"].get("code", -1),
                            )
                        )
                    else:
                        future.set_result(message.get("result"))
                # Notifications from server (diagnostics, etc.) — log and skip
                elif "method" in message:
                    logger.debug("LSP notification: %s", message.get("method"))
            except asyncio.CancelledError:
                break
            except Exception:
                if self._running:
                    logger.exception("LSP read loop error")
                break

    async def _read_message(self) -> dict | None:
        """Read a single LSP message (header + body)."""
        # Read headers until empty line
        headers = b""
        while True:
            line = await self._reader.readline()
            if not line:
                return None
            headers += line
            if headers.endswith(b"\r\n\r\n"):
                break

        content_length = decode_header(headers)
        body = await self._reader.readexactly(content_length)
        return json.loads(body)

    async def request(self, method: str, params: dict | None = None) -> Any:
        """Send a request and wait for the response."""
        self._request_id += 1
        msg_id = self._request_id
        message = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params or {},
        }
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        self._writer.write(encode_message(message))
        await self._writer.drain()
        return await asyncio.wait_for(future, timeout=30)

    async def notify(self, method: str, params: dict | None = None) -> None:
        """Send a notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        self._writer.write(encode_message(message))
        await self._writer.drain()

    async def shutdown(self) -> None:
        """Send shutdown request and exit notification."""
        self._running = False
        try:
            await asyncio.wait_for(self.request("shutdown"), timeout=5)
        except Exception:
            pass
        try:
            await self.notify("exit")
        except Exception:
            pass
        if self._read_task:
            self._read_task.cancel()
        if self._process.returncode is None:
            self._process.terminate()


class LSPError(Exception):
    def __init__(self, message: str, code: int) -> None:
        self.code = code
        super().__init__(message)

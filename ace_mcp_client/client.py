# ace_mcp_client/client.py
"""HTTP client for the ACE API.

Token discovery order:
  1. Explicit token= parameter
  2. ACE_TOKEN environment variable
  3. ~/.ace/token.json file
  4. ACE_API_KEY env var → POST /auth/token to exchange for JWT

Base URL from ACE_URL env var (default: http://localhost:3000).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_TOKEN_FILE = Path(os.environ.get("ACE_CONFIG_DIR", Path.home() / ".ace")) / "token.json"


class AceClient:
    """Async HTTP client wrapper for the ACE REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url or os.environ.get("ACE_URL", "http://localhost:3000")
        self._token = token
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout)
        return self._client

    async def _resolve_token(self) -> str | None:
        """Resolve auth token using the discovery chain."""
        if self._token:
            return self._token

        # 1. Environment variable
        env_token = os.environ.get("ACE_TOKEN")
        if env_token:
            self._token = env_token
            return self._token

        # 2. Token file
        if _TOKEN_FILE.exists():
            try:
                data = json.loads(_TOKEN_FILE.read_text())
                file_token = data.get("token")
                if file_token:
                    self._token = file_token
                    return self._token
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Failed to read token file: %s", exc)

        # 3. API key exchange
        api_key = os.environ.get("ACE_API_KEY")
        if api_key:
            try:
                client = await self._ensure_client()
                r = await client.post("/auth/token", json={"api_key": api_key})
                r.raise_for_status()
                self._token = r.json().get("token")
                return self._token
            except httpx.HTTPError as exc:
                logger.warning("Token exchange failed: %s", exc)

        return None

    async def _headers(self) -> dict[str, str]:
        token = await self._resolve_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def get(self, path: str, params: dict | None = None) -> dict:
        """Send a GET request and return JSON response."""
        client = await self._ensure_client()
        headers = await self._headers()
        r = await client.get(path, params=params, headers=headers)
        r.raise_for_status()
        return r.json()

    async def post(self, path: str, json: dict | None = None) -> dict:
        """Send a POST request and return JSON response."""
        client = await self._ensure_client()
        headers = await self._headers()
        r = await client.post(path, json=json, headers=headers)
        r.raise_for_status()
        return r.json()

    async def submit_task(
        self,
        body: dict,
        *,
        wait: bool = False,
        wait_timeout: float | None = None,
        poll_interval: float = 1.0,
    ) -> dict:
        """Submit a durable task receipt, optionally polling for its result.

        Submission itself remains bounded by the ordinary HTTP timeout.  A
        caller that wants synchronous CLI/script behavior polls the durable
        receipt rather than holding one long-lived request open.
        """
        payload = dict(body)
        payload.setdefault("wait_seconds", 1.0)
        receipt = await self.post("/tasks", json=payload)
        if not wait or receipt.get("status") in {"completed", "failed", "degraded"}:
            return receipt
        return await self.wait_for_task(
            str(receipt["id"]),
            timeout=wait_timeout,
            poll_interval=poll_interval,
        )

    async def wait_for_task(
        self,
        task_id: str,
        *,
        timeout: float | None = None,
        poll_interval: float = 1.0,
    ) -> dict:
        """Poll a durable task until a terminal state or the caller's deadline."""
        started = time.monotonic()
        while True:
            task = await self.get(f"/tasks/{task_id}")
            if task.get("status") in {"completed", "failed", "degraded"}:
                return task
            if timeout is not None and time.monotonic() - started >= timeout:
                return {
                    **task,
                    "polling": {
                        "status": "timed_out",
                        "message": "Polling stopped; task execution may still be running and remains retrievable.",
                    },
                }
            await asyncio.sleep(max(0.05, poll_interval))

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

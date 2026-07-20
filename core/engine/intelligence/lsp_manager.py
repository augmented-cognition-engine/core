"""LSP server lifecycle manager — start, query, keep warm, restart.

Manages multiple LSP servers (one per language). Auto-provisions on first use.
Provides unified query API regardless of language.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from core.engine.intelligence.lsp_client import LSPClient
from core.engine.intelligence.provisioner import ServerProvisioner
from core.engine.intelligence.servers import SERVERS, get_server_config

logger = logging.getLogger(__name__)


@dataclass
class Location:
    uri: str
    line: int
    character: int


@dataclass
class SymbolInfo:
    name: str
    kind: int
    location: Location
    container_name: str = ""


@dataclass
class ServerState:
    language: str
    process: asyncio.subprocess.Process | None = None
    client: LSPClient | None = None
    initialized: bool = False
    root_uri: str = ""


class LSPManager:
    """Manages LSP server lifecycles and provides a unified query API."""

    def __init__(self) -> None:
        self._servers: dict[str, ServerState] = {}
        self._provisioner = ServerProvisioner()

    @property
    def active_servers(self) -> list[str]:
        return [lang for lang, state in self._servers.items() if state.initialized]

    def is_running(self, language: str) -> bool:
        state = self._servers.get(language)
        return state is not None and state.initialized

    def is_supported(self, language: str) -> bool:
        return language in SERVERS

    async def start(self, language: str, root_path: str) -> bool:
        """Start an LSP server for a language. Auto-provisions if needed.

        Returns True if server started successfully.
        """
        if self.is_running(language):
            return True

        config = get_server_config(language)
        if not config:
            logger.warning("No LSP server configured for %s", language)
            return False

        # Provision if needed
        try:
            binary = self._provisioner.provision(language)
        except Exception as exc:
            logger.error("Failed to provision %s: %s", config["name"], exc)
            return False

        # Start the process
        try:
            cmd = [binary] + config.get("args", [])
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            client = LSPClient(process)
            await client.start()

            # Initialize — use absolute path for rootUri
            abs_root = os.path.abspath(root_path)
            root_uri = f"file://{abs_root}"
            await client.request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": root_uri,
                    "rootPath": abs_root,
                    "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(abs_root)}],
                    "capabilities": {
                        "textDocument": {
                            "references": {"dynamicRegistration": False},
                            "definition": {"dynamicRegistration": False},
                            "documentSymbol": {"dynamicRegistration": False},
                        },
                        "workspace": {
                            "symbol": {"dynamicRegistration": False},
                        },
                    },
                    "initializationOptions": config.get("init_options", {}),
                },
            )
            await client.notify("initialized")

            self._servers[language] = ServerState(
                language=language,
                process=process,
                client=client,
                initialized=True,
                root_uri=root_uri,
            )
            logger.info("LSP server %s started for %s", config["name"], root_path)
            return True

        except Exception as exc:
            logger.error("Failed to start LSP server for %s: %s", language, exc)
            return False

    async def stop(self, language: str) -> None:
        """Stop an LSP server."""
        state = self._servers.pop(language, None)
        if state and state.client:
            await state.client.shutdown()

    async def stop_all(self) -> None:
        """Stop all running servers."""
        for language in list(self._servers.keys()):
            await self.stop(language)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    async def find_references(self, uri: str, line: int, character: int, language: str) -> list[Location]:
        """Find all references to a symbol."""
        client = self._get_client(language)
        if not client:
            return []
        try:
            result = await client.request(
                "textDocument/references",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": character},
                    "context": {"includeDeclaration": True},
                },
            )
            return [
                Location(
                    uri=loc["uri"],
                    line=loc["range"]["start"]["line"],
                    character=loc["range"]["start"]["character"],
                )
                for loc in (result or [])
            ]
        except Exception as exc:
            logger.debug("find_references failed: %s", exc)
            return []

    async def go_to_definition(self, uri: str, line: int, character: int, language: str) -> Location | None:
        """Go to the definition of a symbol."""
        client = self._get_client(language)
        if not client:
            return None
        try:
            result = await client.request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": character},
                },
            )
            if not result:
                return None
            # Result can be Location or Location[]
            loc = result[0] if isinstance(result, list) else result
            return Location(
                uri=loc["uri"],
                line=loc["range"]["start"]["line"],
                character=loc["range"]["start"]["character"],
            )
        except Exception as exc:
            logger.debug("go_to_definition failed: %s", exc)
            return None

    async def workspace_symbols(self, query: str, language: str) -> list[SymbolInfo]:
        """Search workspace symbols."""
        client = self._get_client(language)
        if not client:
            return []
        try:
            result = await client.request("workspace/symbol", {"query": query})
            return [
                SymbolInfo(
                    name=s["name"],
                    kind=s["kind"],
                    location=Location(
                        uri=s["location"]["uri"],
                        line=s["location"]["range"]["start"]["line"],
                        character=s["location"]["range"]["start"]["character"],
                    ),
                    container_name=s.get("containerName", ""),
                )
                for s in (result or [])
            ]
        except Exception as exc:
            logger.debug("workspace_symbols failed: %s", exc)
            return []

    async def document_symbols(self, uri: str, language: str) -> list[SymbolInfo]:
        """Get all symbols in a document."""
        client = self._get_client(language)
        if not client:
            return []
        try:
            result = await client.request(
                "textDocument/documentSymbol",
                {
                    "textDocument": {"uri": uri},
                },
            )
            # documentSymbol returns either SymbolInformation[] or DocumentSymbol[]
            symbols = []
            for s in result or []:
                if "location" in s:
                    # SymbolInformation format
                    symbols.append(
                        SymbolInfo(
                            name=s["name"],
                            kind=s["kind"],
                            location=Location(
                                uri=uri,
                                line=s["location"]["range"]["start"]["line"],
                                character=s["location"]["range"]["start"]["character"],
                            ),
                            container_name=s.get("containerName", ""),
                        )
                    )
                elif "range" in s:
                    # DocumentSymbol format
                    symbols.append(
                        SymbolInfo(
                            name=s["name"],
                            kind=s["kind"],
                            location=Location(
                                uri=uri,
                                line=s["range"]["start"]["line"],
                                character=s["range"]["start"]["character"],
                            ),
                        )
                    )
                    # Also extract children
                    for child in s.get("children", []):
                        symbols.append(
                            SymbolInfo(
                                name=child["name"],
                                kind=child["kind"],
                                location=Location(
                                    uri=uri,
                                    line=child["range"]["start"]["line"],
                                    character=child["range"]["start"]["character"],
                                ),
                                container_name=s["name"],
                            )
                        )
            return symbols
        except Exception as exc:
            logger.debug("document_symbols failed: %s", exc)
            return []

    async def notify_change(self, uri: str, content: str, language: str) -> None:
        """Notify server that a file changed."""
        client = self._get_client(language)
        if not client:
            return
        try:
            await client.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": language,
                        "version": 1,
                        "text": content,
                    },
                },
            )
        except Exception as exc:
            logger.debug("notify_change failed: %s", exc)

    def _get_client(self, language: str) -> LSPClient | None:
        state = self._servers.get(language)
        if state and state.initialized and state.client:
            return state.client
        return None

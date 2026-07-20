"""LSP server registry — data-driven config for language servers."""

from __future__ import annotations

SERVERS: dict[str, dict] = {
    "python": {
        "name": "pyright",
        "install_method": "pip",
        "package": "pyright",
        "binary": "pyright-langserver",
        "args": ["--stdio"],
        "init_options": {},
    },
    "typescript": {
        "name": "typescript-language-server",
        "install_method": "npm",
        "package": "typescript-language-server",
        "binary": "typescript-language-server",
        "args": ["--stdio"],
        "peer_deps": ["typescript"],
        "init_options": {},
    },
    "javascript": {
        "name": "typescript-language-server",
        "install_method": "npm",
        "package": "typescript-language-server",
        "binary": "typescript-language-server",
        "args": ["--stdio"],
        "peer_deps": ["typescript"],
        "init_options": {},
    },
    "go": {
        "name": "gopls",
        "install_method": "binary",
        "binary": "gopls",
        "args": ["serve"],
        "url_template": "https://github.com/golang/tools/releases/latest",
        "init_options": {},
    },
    "rust": {
        "name": "rust-analyzer",
        "install_method": "binary",
        "binary": "rust-analyzer",
        "args": [],
        "url_template": "https://github.com/rust-lang/rust-analyzer/releases/latest",
        "init_options": {},
    },
}

SUPPORTED_LANGUAGES = set(SERVERS.keys())


def get_server_config(language: str) -> dict | None:
    """Get LSP server config for a language."""
    return SERVERS.get(language)


def needs_server(language: str) -> bool:
    """Check if a language has an LSP server available."""
    return language in SERVERS

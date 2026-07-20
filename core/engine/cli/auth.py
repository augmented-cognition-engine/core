# engine/cli/auth.py
"""CLI authentication — JWT token storage."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(os.environ.get("ACE_CONFIG_DIR", Path.home() / ".ace"))
_TOKEN_FILE = _CONFIG_DIR / "token.json"
_DEFAULT_URL = "http://localhost:3000"


def get_config_path() -> Path:
    """Return the effective credential file path for user-facing diagnostics."""
    return _TOKEN_FILE


def _validate_url(url: str) -> str:
    """Validate ACE server URL format before using it for API calls.

    Enforces http:// or https:// scheme to prevent SSRF-style injection via
    the ACE_URL environment variable or the stored config file.

    Returns the URL with a trailing slash stripped.
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Invalid ACE URL (must start with http:// or https://): {url!r}")
    return url.rstrip("/")


def get_base_url() -> str:
    config = _load_config()
    url = config.get("url", _DEFAULT_URL)
    return _validate_url(url)


def get_token() -> str | None:
    config = _load_config()
    return config.get("token")


def get_headers() -> dict:
    token = get_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def save_config(url: str, token: str) -> None:
    validated_url = _validate_url(url)
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_DIR.chmod(0o700)
    payload = json.dumps({"url": validated_url, "token": token})
    # The file holds a live bearer credential. Create it 0600 FROM THE START
    # (os.open with an explicit mode, not write_text + a later chmod) so there
    # is no window in which it exists at the default umask — world-readable on
    # a shared machine or CI runner. O_CREAT's mode does not narrow an existing
    # file, so the explicit chmod below is kept as belt-and-suspenders in case
    # a prior looser-perm token file is being overwritten. This is Task 9b's
    # security bar; save_config is now the sanctioned writer, via `ace login`.
    fd = os.open(_TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    _TOKEN_FILE.chmod(0o600)
    logger.debug("ACE config saved: url=%s", validated_url)


def _load_config() -> dict:
    if _TOKEN_FILE.exists():
        try:
            return json.loads(_TOKEN_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

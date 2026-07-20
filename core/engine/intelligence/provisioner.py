"""Auto-provision LSP servers — download/install without user intervention.

Installs to ~/.ace/servers/<language>/ for isolation.
pip-based servers get their own venv. npm-based get their own prefix.
Binary servers are downloaded directly.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from core.engine.intelligence.servers import get_server_config

logger = logging.getLogger(__name__)


def get_server_dir() -> str:
    """Base directory for provisioned servers."""
    return str(Path.home() / ".ace" / "servers")


class ServerProvisioner:
    """Downloads and installs LSP servers."""

    def __init__(self) -> None:
        self._base_dir = get_server_dir()

    def is_provisioned(self, language: str) -> bool:
        """Check if the server for a language is already installed."""
        config = get_server_config(language)
        if not config:
            return False
        binary = self._find_binary(language)
        return binary is not None and os.path.exists(binary)

    def get_binary_path(self, language: str) -> str | None:
        """Get path to the server binary (installed or expected location)."""
        config = get_server_config(language)
        if not config:
            return None
        # Check active Python environment's bin dir first
        import sys

        venv_bin = os.path.join(os.path.dirname(sys.executable), config["binary"])
        if os.path.exists(venv_bin):
            return venv_bin
        # Check if already on PATH
        system_binary = shutil.which(config["binary"])
        if system_binary:
            return system_binary
        # Check provisioned location
        return self._expected_binary_path(language, config)

    def provision(self, language: str) -> str:
        """Install the LSP server for a language. Returns binary path.

        Raises RuntimeError if installation fails.
        """
        config = get_server_config(language)
        if not config:
            raise RuntimeError(f"No LSP server configured for {language}")

        # Check active Python environment's bin dir first (venv where ACE is installed)
        import sys

        venv_bin = os.path.join(os.path.dirname(sys.executable), config["binary"])
        if os.path.exists(venv_bin):
            logger.info("Using venv %s at %s", config["name"], venv_bin)
            return venv_bin

        # Check if already available on system PATH
        system_binary = shutil.which(config["binary"])
        if system_binary:
            logger.info("Using system %s at %s", config["name"], system_binary)
            return system_binary

        method = config["install_method"]
        if method == "pip":
            return self._provision_pip(language, config)
        elif method == "npm":
            return self._provision_npm(language, config)
        elif method == "binary":
            raise RuntimeError(
                f"Binary download for {config['name']} not yet implemented. "
                f"Install manually: {config.get('url_template', 'see docs')}"
            )
        else:
            raise RuntimeError(f"Unknown install method: {method}")

    def _provision_pip(self, language: str, config: dict) -> str:
        """Install a pip-based server into an isolated venv."""
        venv_dir = os.path.join(self._base_dir, language, "venv")
        os.makedirs(venv_dir, exist_ok=True)

        if not os.path.exists(os.path.join(venv_dir, "bin", "python")):
            logger.info("Creating venv for %s at %s", config["name"], venv_dir)
            subprocess.run(
                ["python3", "-m", "venv", venv_dir],
                check=True,
                capture_output=True,
                timeout=60,
            )

        pip = os.path.join(venv_dir, "bin", "pip")
        logger.info("Installing %s via pip...", config["package"])
        subprocess.run(
            [pip, "install", "--quiet", config["package"]],
            check=True,
            capture_output=True,
            timeout=120,
        )

        binary = os.path.join(venv_dir, "bin", config["binary"])
        if not os.path.exists(binary):
            # Some packages install with different names
            binary = os.path.join(venv_dir, "bin", config["package"])
        if not os.path.exists(binary):
            raise RuntimeError(f"Installed {config['package']} but binary not found at {binary}")

        logger.info("Provisioned %s at %s", config["name"], binary)
        return binary

    def _provision_npm(self, language: str, config: dict) -> str:
        """Install an npm-based server into an isolated prefix."""
        prefix = os.path.join(self._base_dir, language, "npm")
        os.makedirs(prefix, exist_ok=True)

        packages = [config["package"]] + config.get("peer_deps", [])
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("npm not found — install Node.js to use TypeScript language server")

        logger.info("Installing %s via npm...", config["package"])
        subprocess.run(
            [npm, "install", "--prefix", prefix] + packages,
            check=True,
            capture_output=True,
            timeout=120,
        )

        binary = os.path.join(prefix, "node_modules", ".bin", config["binary"])
        if not os.path.exists(binary):
            raise RuntimeError(f"Installed {config['package']} but binary not found at {binary}")

        logger.info("Provisioned %s at %s", config["name"], binary)
        return binary

    def _find_binary(self, language: str) -> str | None:
        """Find the binary for a language — venv, system PATH or provisioned."""
        config = get_server_config(language)
        if not config:
            return None
        # Check active Python environment's bin dir first
        import sys

        venv_bin = os.path.join(os.path.dirname(sys.executable), config["binary"])
        if os.path.exists(venv_bin):
            return venv_bin
        system = shutil.which(config["binary"])
        if system:
            return system
        expected = self._expected_binary_path(language, config)
        if expected and os.path.exists(expected):
            return expected
        return None

    def _expected_binary_path(self, language: str, config: dict) -> str:
        """Expected path if provisioned."""
        method = config["install_method"]
        if method == "pip":
            return os.path.join(self._base_dir, language, "venv", "bin", config["binary"])
        elif method == "npm":
            return os.path.join(self._base_dir, language, "npm", "node_modules", ".bin", config["binary"])
        else:
            return os.path.join(self._base_dir, language, config["binary"])

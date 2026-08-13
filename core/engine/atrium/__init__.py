"""Packaged Atrium application assets.

Atrium is the domain-neutral command center for an ACE installation.  Its
production bundle ships with ``ace-core`` so a user can open the application
without a JavaScript toolchain or a source checkout.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def static_dir() -> Path:
    """Return the installed filesystem directory containing the Atrium bundle."""

    resource = files(__package__).joinpath("static")
    # Wheels are installed as ordinary files by supported Python installers.
    # Serving an SPA requires a filesystem path, so deliberately fail clearly
    # for exotic zip-import loaders instead of extracting mutable assets.
    try:
        return Path(resource)
    except TypeError as exc:  # pragma: no cover - standard wheel installs are filesystem-backed
        raise RuntimeError("Atrium assets require a filesystem-backed ace-core installation") from exc


__all__ = ["static_dir"]

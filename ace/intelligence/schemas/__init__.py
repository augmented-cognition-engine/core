"""Installed machine-readable ACE Domain Pack schemas."""

from __future__ import annotations

from importlib.resources import files


def schema_text(name: str) -> str:
    """Read one packaged schema by exact filename without checkout assumptions."""

    if not name.endswith(".json") or "/" in name or "\\" in name:
        raise ValueError("schema name must be one JSON filename")
    return files(__package__).joinpath(name).read_text(encoding="utf-8")


__all__ = ["schema_text"]

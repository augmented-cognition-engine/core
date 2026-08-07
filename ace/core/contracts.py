"""Small, dependency-light primitives shared across public ACE contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict


class FrozenContract(BaseModel):
    """Base for immutable, fail-closed public contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible material deterministically for the alpha ACE compiler.

    Alpha identities are compiler-owned. Generated clients must not reproduce these hashes until
    ACE freezes a cross-language canonicalization specification before the beta contract.
    """

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_hash(value: Any) -> str:
    """Return a lowercase SHA-256 digest over canonical JSON."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    """Build a bounded content-derived identifier."""

    return f"{prefix}:{canonical_hash(value)[:32]}"

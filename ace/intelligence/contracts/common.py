"""Validation primitives for declarative Intelligence artifacts."""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

MAX_DECLARATIONS = 256
MAX_REFS = 256
MAX_RESOURCE_BYTES = 1_000_000
MAX_PACK_BYTES = 8_000_000
MAX_CANONICAL_VALUE_CHARS = 32_000

_SLUG = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_CONTRACT = re.compile(r"^ace\.[a-z0-9][a-z0-9._-]*/v[0-9]+(?:alpha[0-9]+|beta[0-9]+)?$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
_PRODUCT_ID = re.compile(r"^product:[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")

ItemT = TypeVar("ItemT", bound=BaseModel)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def parse_json_strict(value: str) -> Any:
    """Parse finite JSON while rejecting duplicate object keys."""

    return json.loads(
        value,
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


def validate_slug(value: str, *, name: str = "identifier") -> str:
    if len(value) > 120 or not _SLUG.fullmatch(value):
        raise ValueError(f"{name} must be a bounded lowercase slug")
    return value


def validate_version(value: str) -> str:
    if len(value) > 80 or not _VERSION.fullmatch(value):
        raise ValueError("version must use bounded semantic-version syntax")
    return value


def validate_product_id(value: str) -> str:
    if not _PRODUCT_ID.fullmatch(value):
        raise ValueError("product_id must be a non-empty product-scoped identifier")
    return value


def validate_contract(value: str) -> str:
    if len(value) > 160 or not _CONTRACT.fullmatch(value):
        raise ValueError("contract must be a versioned ace.* contract identifier")
    return value


def validate_reference(value: str, *, name: str = "reference") -> str:
    if not _REFERENCE.fullmatch(value):
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def validate_digest(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("digest must use lowercase sha256:<64-hex> syntax")
    return value


def validate_resource_path(value: str) -> str:
    if not value or len(value) > 240 or "\\" in value or ":" in value:
        raise ValueError("resource path must be a bounded POSIX-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("resource path must be normalized and may not traverse")
    if str(path) != value:
        raise ValueError("resource path must already be normalized")
    return value


def sorted_unique(
    values: tuple[ItemT, ...],
    *,
    key: Callable[[ItemT], str],
    label: str,
    maximum: int = MAX_DECLARATIONS,
) -> tuple[ItemT, ...]:
    if len(values) > maximum:
        raise ValueError(f"{label} exceed the {maximum}-item bound")
    keys = [key(value) for value in values]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} must use unique identifiers")
    return tuple(sorted(values, key=key))


def normalized_strings(values: Any, *, label: str, maximum: int = MAX_REFS) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError(f"{label} must be a collection")
    if any(not isinstance(value, str) for value in values):
        raise ValueError(f"{label} must contain strings")
    result = tuple(sorted(set(values)))
    if len(result) > maximum:
        raise ValueError(f"{label} exceed the {maximum}-item bound")
    return result

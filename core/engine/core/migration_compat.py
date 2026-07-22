"""Audited compatibility policy for replaying historical schema migrations.

Fresh databases replay migrations authored across several SurrealDB releases.
Only the exact legacy version/error pairs below may continue after an error;
current migrations remain fail-closed. Both the standalone installer and API
startup import this module so they cannot silently disagree about bootstrap.
"""

from __future__ import annotations

STRICT_FROM_VERSION = 142

_ALREADY_EXISTS_VERSIONS = {6, 12, 19, 20, 25, 29, 31, 32, 35, 37, 40, 44, 55, 83, 84}
_FLEXIBLE_SCHEMALESS_VERSIONS = {44, 52}
_NUMERIC_SCHEMA_VERSION_VERSIONS = {81, 83, 84, 85}


def is_known_legacy_compatibility_error(version: int, error: str) -> bool:
    """Return true only for an audited pre-strict migration incompatibility."""
    if version >= STRICT_FROM_VERSION:
        return False
    if version in _ALREADY_EXISTS_VERSIONS and "already exists" in error:
        return True
    if version in _FLEXIBLE_SCHEMALESS_VERSIONS and "FLEXIBLE can only be used" in error:
        return True
    if version in _NUMERIC_SCHEMA_VERSION_VERSIONS and "Expected `string`" in error:
        return True
    if version == 54 and (
        "Cannot execute statement using value" in error or "The table 'graph_instance' does not exist" in error
    ):
        return True
    return False

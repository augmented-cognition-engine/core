"""Strict behavior for the standalone schema installer."""

from unittest.mock import AsyncMock

import pytest

from scripts.schema_apply import (
    _is_known_legacy_compatibility_error,
    apply_file,
    validate_schema,
)


def test_legacy_compatibility_allowlist_is_narrow():
    assert _is_known_legacy_compatibility_error(6, "The table 'x' already exists")
    assert _is_known_legacy_compatibility_error(44, "An error occurred: FLEXIBLE can only be used in SCHEMAFULL tables")
    assert not _is_known_legacy_compatibility_error(7, "The table 'x' already exists")
    assert not _is_known_legacy_compatibility_error(44, "permission denied")


@pytest.mark.asyncio
async def test_apply_file_fails_closed_on_unknown_legacy_error():
    db = AsyncMock()
    db.query.return_value = "permission denied"

    with pytest.raises(RuntimeError, match="fail-closed"):
        await apply_file(db, 44, "v044.surql", "DEFINE TABLE example;")


@pytest.mark.asyncio
async def test_apply_file_accepts_only_audited_legacy_event():
    db = AsyncMock()
    db.query.return_value = "The table 'example' already exists"

    events = await apply_file(db, 6, "v006.surql", "DEFINE TABLE example;")

    assert len(events) == 1


@pytest.mark.asyncio
async def test_validate_schema_requires_version_and_runtime_tables(monkeypatch):
    db = AsyncMock()
    db.query.return_value = [
        {
            "tables": {
                name: "definition"
                for name in {
                    "config_entry",
                    "decision",
                    "discipline",
                    "insight",
                    "observation",
                    "product",
                    "reasoning_event",
                    "specialty",
                    "task",
                    "workspace",
                }
            }
        }
    ]
    monkeypatch.setattr("scripts.schema_apply.get_current_version", AsyncMock(return_value=141))

    await validate_schema(db, 141)


@pytest.mark.asyncio
async def test_validate_schema_rejects_missing_runtime_table(monkeypatch):
    db = AsyncMock()
    db.query.return_value = [{"tables": {}}]
    monkeypatch.setattr("scripts.schema_apply.get_current_version", AsyncMock(return_value=141))

    with pytest.raises(RuntimeError, match="missing required tables"):
        await validate_schema(db, 141)

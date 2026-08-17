"""`ace recovery` — native full-store backup and clean-target restore."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

import click
from surrealdb import AsyncSurreal

from core.engine.core.config import settings
from core.engine.core.recovery import (
    DatabaseRecoveryError,
    create_database_backup,
    restore_database_backup,
    target_from_settings,
)
from core.engine.core.surreal32_upgrade import Surreal32UpgradeError, prepare_surreal32_upgrade
from core.engine.graph.assertion_history_upgrade import (
    AssertionHistoryUpgradeError,
    apply_assertion_history_upgrade,
    load_assertion_history_inventory,
    load_mapping_document,
)


@click.group("recovery")
def recovery() -> None:
    """Back up or restore the complete ACE database for single-user recovery.

    These commands do not export environment configuration, connector credentials,
    external secret stores, or source bodies that ACE did not persist.
    """


async def _database() -> AsyncSurreal:
    db = AsyncSurreal(settings.surreal_url)
    await db.connect()
    await db.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
    await db.use(settings.surreal_ns, settings.surreal_db)
    return db


@recovery.command("backup")
@click.argument("output", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--manifest", type=click.Path(path_type=Path, dir_okay=False))
def backup(output: Path, manifest: Path | None) -> None:
    """Write a native full-database export and checksum manifest to new files."""

    try:
        result = asyncio.run(
            create_database_backup(
                output,
                manifest_path=manifest,
                target=target_from_settings(),
            )
        )
    except DatabaseRecoveryError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@recovery.command("restore")
@click.argument("export", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.option("--manifest", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.option("--target-namespace", required=True, help="Explicit empty destination namespace.")
@click.option("--target-database", required=True, help="Explicit empty destination database.")
def restore(
    export: Path,
    manifest: Path | None,
    target_namespace: str,
    target_database: str,
) -> None:
    """Verify and import EXPORT only into a clean explicit destination."""

    try:
        result = asyncio.run(
            restore_database_backup(
                export,
                manifest_path=manifest,
                target=target_from_settings(
                    namespace=target_namespace,
                    database=target_database,
                ),
            )
        )
    except DatabaseRecoveryError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@recovery.command("prepare-surreal32")
@click.option("--apply", is_flag=True, help="Remove only reported dangling org indexes.")
def prepare_surreal32(apply: bool) -> None:
    """Inspect SurrealDB 3.2 export compatibility; dry-run by default."""

    async def run() -> dict:
        db = await _database()
        try:
            return (await prepare_surreal32_upgrade(db, apply=apply)).as_dict()
        finally:
            await db.close()

    try:
        click.echo(json.dumps(asyncio.run(run()), indent=2, sort_keys=True))
    except Surreal32UpgradeError as exc:
        raise click.ClickException(str(exc)) from exc


@recovery.command("upgrade-assertion-history")
@click.option("--mapping", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.option("--apply", is_flag=True, help="Copy explicitly mapped components; omit for inventory.")
@click.option("--max-rows-per-table", type=click.IntRange(min=1), default=10_000, show_default=True)
def upgrade_assertion_history(mapping: Path | None, apply: bool, max_rows_per_table: int) -> None:
    """Inventory or explicitly map legacy assertion history; dry-run by default."""

    if apply and mapping is None:
        raise click.UsageError("--apply requires --mapping")
    try:
        mapping_payload = json.loads(mapping.read_text(encoding="utf-8")) if mapping else None
        if mapping_payload is not None and not isinstance(mapping_payload, dict):
            raise AssertionHistoryUpgradeError("mapping document must be a JSON object")
        mappings = load_mapping_document(mapping_payload) if mapping_payload is not None else {}
    except (OSError, json.JSONDecodeError, AssertionHistoryUpgradeError) as exc:
        raise click.ClickException(str(exc)) from exc

    async def run() -> dict:
        db = await _database()
        try:
            inventory, rows = await load_assertion_history_inventory(
                db,
                mappings=mappings,
                max_rows_per_table=max_rows_per_table,
            )
            payload: dict = {"mode": "dry_run", "inventory": inventory.as_dict()}
            if apply:
                payload = {
                    "mode": "apply",
                    "inventory": inventory.as_dict(),
                    "apply_report": (
                        await apply_assertion_history_upgrade(db, inventory=inventory, rows_by_table=rows)
                    ).as_dict(),
                }
            return payload
        finally:
            await db.close()

    try:
        click.echo(json.dumps(asyncio.run(run()), indent=2, sort_keys=True, default=str))
    except AssertionHistoryUpgradeError as exc:
        raise click.ClickException(str(exc)) from exc


__all__ = ["recovery"]


if __name__ == "__main__":
    recovery()

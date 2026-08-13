"""`ace recovery` — native full-store backup and clean-target restore."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

import click

from core.engine.core.recovery import (
    DatabaseRecoveryError,
    create_database_backup,
    restore_database_backup,
    target_from_settings,
)


@click.group("recovery")
def recovery() -> None:
    """Back up or restore the complete ACE database for single-user recovery.

    These commands do not export environment configuration, connector credentials,
    external secret stores, or source bodies that ACE did not persist.
    """


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


__all__ = ["recovery"]


if __name__ == "__main__":
    recovery()

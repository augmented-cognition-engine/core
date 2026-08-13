"""Personal Intelligence ownership through the authenticated HTTP API."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


def _request(ctx: click.Context, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = httpx.post(
            f"{ctx.obj['url']}{path}",
            headers=get_headers(),
            json=payload,
            timeout=60,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise click.ClickException(
            "ACE is unavailable. Run `ace service start`, then `ace doctor`, and retry."
        ) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        reason = str(detail) if detail else "Personal Intelligence ownership request failed"
        raise click.ClickException(f"{response.status_code}: {reason}")
    value = response.json()
    if not isinstance(value, dict):
        raise click.ClickException("ACE returned an invalid personal ownership response.")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise click.ClickException(f"Ownership file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Ownership file is not valid JSON: {path} ({exc.msg})") from exc
    if not isinstance(value, dict):
        raise click.ClickException("Ownership file must contain one JSON object.")
    return value


def _write_sensitive_json(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise click.ClickException(f"Refusing to overwrite {path}; pass --overwrite intentionally.") from exc
    except OSError as exc:
        raise click.ClickException(f"Could not create ownership file {path}: {exc}") from exc
    try:
        os.fchmod(fd, 0o600)
        material = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"{material}\n")
        fd = -1
    finally:
        if fd >= 0:
            os.close(fd)
    path.chmod(0o600)


@click.group("ownership")
def ownership() -> None:
    """Export or deliberately delete your personal Intelligence records."""


@ownership.command("export")
@click.option("--authority-grant-ref", required=True, help="Current deliver-export grant reference.")
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path, dir_okay=False),
    help="Write canonical export evidence to this private JSON file.",
)
@click.option("--overwrite", is_flag=True, help="Replace an existing output file intentionally.")
@click.pass_context
def export_ownership(
    ctx: click.Context,
    authority_grant_ref: str,
    output: Path,
    overwrite: bool,
) -> None:
    """Export canonical evidence; the artifact is not a runnable restore."""

    artifact = _request(
        ctx,
        "/v1/intelligence/ownership/export",
        {"authority_grant_ref": authority_grant_ref},
    )
    _write_sensitive_json(output, artifact, overwrite=overwrite)
    console.print(
        f"Exported {artifact.get('record_count', 0)} canonical record(s) to {output}.\n"
        "This artifact is portability evidence, not a runnable restore."
    )


@ownership.command("delete-preview")
@click.option("--authority-grant-ref", required=True, help="Current lifecycle-administration grant reference.")
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path, dir_okay=False),
    help="Write the exact expiring deletion preview to this private JSON file.",
)
@click.option(
    "--window-seconds",
    type=click.IntRange(min=60, max=3600),
    default=900,
    show_default=True,
)
@click.option("--overwrite", is_flag=True, help="Replace an existing preview file intentionally.")
@click.pass_context
def preview_deletion(
    ctx: click.Context,
    authority_grant_ref: str,
    output: Path,
    window_seconds: int,
    overwrite: bool,
) -> None:
    """Create the exact snapshot and digest required before deletion."""

    preview = _request(
        ctx,
        "/v1/intelligence/ownership/deletion/preview",
        {
            "authority_grant_ref": authority_grant_ref,
            "confirmation_window_seconds": window_seconds,
        },
    )
    _write_sensitive_json(output, preview, overwrite=overwrite)
    console.print(
        f"Previewed {preview.get('record_count', 0)} record(s) in {output}.\n"
        f"Confirmation digest: {preview.get('confirmation_digest')}\n"
        "Review the file and backup limitation before running delete-confirm."
    )


@ownership.command("delete-confirm")
@click.argument("preview_file", type=click.Path(path_type=Path, dir_okay=False, exists=True))
@click.option("--authority-grant-ref", required=True, help="Current lifecycle-administration grant reference.")
@click.option(
    "--confirmation-digest",
    required=True,
    help="Exact digest shown by delete-preview after reviewing the preview file.",
)
@click.pass_context
def confirm_deletion(
    ctx: click.Context,
    preview_file: Path,
    authority_grant_ref: str,
    confirmation_digest: str,
) -> None:
    """Confirm one reviewed preview; backups and external copies are not purged."""

    result = _request(
        ctx,
        "/v1/intelligence/ownership/deletion/confirm",
        {
            "authority_grant_ref": authority_grant_ref,
            "preview": _read_json(preview_file),
            "confirmation_digest": confirmation_digest,
        },
    )
    console.print_json(json.dumps(result, sort_keys=True, default=str))


__all__ = ["ownership"]

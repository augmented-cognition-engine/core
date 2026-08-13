from __future__ import annotations

import json
import stat
from pathlib import Path

from click.testing import CliRunner

from core.engine.cli.commands import ownership as ownership_module
from core.engine.cli.main import cli


class _Response:
    def __init__(self, *, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_cli_registers_personal_ownership_group() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ownership" in result.output


def test_export_writes_private_canonical_file_and_states_non_restore_scope(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "ownership-export.json"
    calls: list[dict] = []

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _Response(
            status_code=200,
            payload={
                "record_count": 1,
                "runnable_restore_supported": False,
                "records": [{"payload": {"secret": "owned"}}],
                "artifact_digest": f"sha256:{'a' * 64}",
            },
        )

    monkeypatch.setattr(ownership_module.httpx, "post", post)
    monkeypatch.setattr(ownership_module, "get_headers", lambda: {"Authorization": "Bearer test"})
    result = CliRunner().invoke(
        cli,
        [
            "--url",
            "http://ace.test",
            "ownership",
            "export",
            "--authority-grant-ref",
            "authority_grant:export",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "not a runnable restore" in result.output
    assert calls[0]["url"] == "http://ace.test/v1/intelligence/ownership/export"
    assert calls[0]["headers"] == {"Authorization": "Bearer test"}
    assert calls[0]["json"] == {"authority_grant_ref": "authority_grant:export"}
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    material = output.read_text(encoding="utf-8")
    assert (
        material == json.dumps(json.loads(material), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    )


def test_preview_file_is_required_for_explicit_digest_confirmation(monkeypatch, tmp_path: Path) -> None:
    preview_file = tmp_path / "delete-preview.json"
    digest = f"sha256:{'b' * 64}"
    preview = {
        "contract": "ace.core.personal-intelligence-delete-preview/v1alpha1",
        "record_count": 2,
        "confirmation_digest": digest,
        "backup_non_reappearance_proven": False,
        "backup_limitation": "primary store only",
    }
    calls: list[dict] = []

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if url.endswith("/preview"):
            return _Response(status_code=200, payload=preview)
        return _Response(
            status_code=200,
            payload={
                "proof": {
                    "removed_count": 2,
                    "backup_non_reappearance_proven": False,
                },
                "transaction_receipt_ref": "append_only_receipt:proof",
            },
        )

    monkeypatch.setattr(ownership_module.httpx, "post", post)
    monkeypatch.setattr(ownership_module, "get_headers", lambda: {})
    runner = CliRunner()
    preview_result = runner.invoke(
        cli,
        [
            "--url",
            "http://ace.test",
            "ownership",
            "delete-preview",
            "--authority-grant-ref",
            "authority_grant:delete",
            "--output",
            str(preview_file),
            "--window-seconds",
            "600",
        ],
    )
    assert preview_result.exit_code == 0, preview_result.output
    assert digest in preview_result.output
    assert stat.S_IMODE(preview_file.stat().st_mode) == 0o600

    missing_digest = runner.invoke(
        cli,
        [
            "ownership",
            "delete-confirm",
            str(preview_file),
            "--authority-grant-ref",
            "authority_grant:delete",
        ],
    )
    assert missing_digest.exit_code != 0
    assert "--confirmation-digest" in missing_digest.output

    confirmed = runner.invoke(
        cli,
        [
            "--url",
            "http://ace.test",
            "ownership",
            "delete-confirm",
            str(preview_file),
            "--authority-grant-ref",
            "authority_grant:delete",
            "--confirmation-digest",
            digest,
        ],
    )
    assert confirmed.exit_code == 0, confirmed.output
    assert calls[-1]["url"].endswith("/v1/intelligence/ownership/deletion/confirm")
    assert calls[-1]["json"] == {
        "authority_grant_ref": "authority_grant:delete",
        "preview": preview,
        "confirmation_digest": digest,
    }
    assert "backup_non_reappearance_proven" in confirmed.output


def test_overwrite_tightens_existing_file_permissions(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "existing-export.json"
    output.write_text("old", encoding="utf-8")
    output.chmod(0o644)
    monkeypatch.setattr(
        ownership_module.httpx,
        "post",
        lambda *args, **kwargs: _Response(
            status_code=200,
            payload={"record_count": 0, "runnable_restore_supported": False},
        ),
    )
    result = CliRunner().invoke(
        cli,
        [
            "ownership",
            "export",
            "--authority-grant-ref",
            "authority_grant:export",
            "--output",
            str(output),
            "--overwrite",
        ],
    )

    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.read_text(encoding="utf-8").startswith('{"record_count":0')


def test_cli_preserves_server_conflict_and_does_not_write_artifact(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "not-created.json"
    monkeypatch.setattr(
        ownership_module.httpx,
        "post",
        lambda *args, **kwargs: _Response(
            status_code=409,
            payload={"detail": "Personal Intelligence ownership request is stale or conflicted"},
        ),
    )
    result = CliRunner().invoke(
        cli,
        [
            "ownership",
            "export",
            "--authority-grant-ref",
            "authority_grant:export",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code != 0
    assert "409" in result.output
    assert not output.exists()

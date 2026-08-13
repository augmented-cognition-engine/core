"""Checkout-free Atrium package and CLI contract."""

from pathlib import Path

from click.testing import CliRunner

from core.engine.atrium import static_dir
from core.engine.cli.commands import atrium as atrium_module


def test_packaged_atrium_has_an_entrypoint_and_hashed_assets() -> None:
    assets = static_dir()

    assert (assets / "index.html").is_file()
    assert any((assets / "assets").glob("*.js"))
    assert any((assets / "assets").glob("*.css"))


def test_atrium_command_serves_packaged_assets_and_the_configured_api(monkeypatch) -> None:
    launched: dict[str, object] = {}

    def run(app, **kwargs):
        launched.update({"app": app, **kwargs})

    monkeypatch.setattr(atrium_module.uvicorn, "run", run)
    result = CliRunner().invoke(
        atrium_module.atrium,
        ["--no-open", "--port", "6123"],
        obj={"url": "http://127.0.0.1:3000", "token": "test-token"},
    )

    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:6123/atrium" in result.output
    assert launched["host"] == "127.0.0.1"
    assert launched["port"] == 6123
    assert launched["app"].state.dist == static_dir()
    assert launched["app"].state.core_api_url == "http://127.0.0.1:3000"


def test_atrium_command_refuses_to_serve_without_a_login() -> None:
    result = CliRunner().invoke(
        atrium_module.atrium,
        ["--no-open"],
        obj={"url": "http://127.0.0.1:3000", "token": None},
    )

    assert result.exit_code != 0
    assert "ace setup" in result.output


def test_pyproject_declares_atrium_package_data() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()

    assert '"core.engine.atrium"' in pyproject
    assert '"static/index.html"' in pyproject

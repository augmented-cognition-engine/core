from __future__ import annotations

import json
from unittest.mock import patch

import httpx
from click.testing import CliRunner

from core.engine.cli.main import cli
from core.engine.product.living_graph import PROJECTION_VERSION


def _response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "http://ace.test/product/landscape"),
    )


def test_landscape_cli_uses_only_the_authenticated_read_endpoint():
    payload = {
        "schema_version": "ace.living-product-snapshot.v1",
        "projection_version": PROJECTION_VERSION,
        "projection_state": {"status": "complete"},
        "product": {"id": "product:alpha", "name": "Alpha"},
    }
    with patch("core.engine.cli.commands.landscape.httpx.get", return_value=_response(200, payload)) as get:
        result = CliRunner().invoke(cli, ["--url", "http://ace.test", "landscape"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["product"]["id"] == "product:alpha"
    get.assert_called_once()
    _args, kwargs = get.call_args
    assert kwargs["params"] == {"projection_version": PROJECTION_VERSION}
    assert get.call_args.args == ("http://ace.test/product/landscape",)


def test_landscape_cli_reports_version_recovery_without_raw_response_body():
    response = _response(
        409,
        {
            "detail": {
                "code": "unsupported_projection_version",
                "recovery": f"Retry with projection_version={PROJECTION_VERSION}.",
                "private": "must-not-render",
            }
        },
    )
    with patch("core.engine.cli.commands.landscape.httpx.get", return_value=response):
        result = CliRunner().invoke(
            cli,
            ["--url", "http://ace.test", "landscape", "--projection-version", "v999"],
        )

    assert result.exit_code == 1
    assert "unsupported_projection_version" in result.output
    assert PROJECTION_VERSION in result.output
    assert "must-not-render" not in result.output


def test_landscape_cli_connection_failure_is_actionable():
    request = httpx.Request("GET", "http://ace.test/product/landscape")
    with patch(
        "core.engine.cli.commands.landscape.httpx.get",
        side_effect=httpx.ConnectError("private transport detail", request=request),
    ):
        result = CliRunner().invoke(cli, ["--url", "http://ace.test", "landscape"])

    assert result.exit_code == 1
    assert "ace doctor" in result.output
    assert "private transport detail" not in result.output

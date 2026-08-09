"""Builder-facing governed-cognition CLI tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
from click.testing import CliRunner

from core.engine.cli.main import cli


def _response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=httpx.Request("GET", "http://ace.test"))


def test_cognition_command_is_promoted_on_main_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "cognition" in result.output
    assert "Teach, inspect, govern, use, and retire reusable cognition." in result.output


def test_cognition_teach_posts_one_non_selectable_proposal() -> None:
    payload = {
        "proposal": {"proposal_id": "cognition_proposal:abc"},
        "semantic_diff": {"changes": [{"path": "$.name", "operation": "add"}]},
        "selectable": False,
    }
    with (
        patch("core.engine.cli.commands.cognition.get_headers", return_value={"Authorization": "Bearer test"}),
        patch("core.engine.cli.commands.cognition.httpx.request", return_value=_response(201, payload)) as request,
    ):
        result = CliRunner().invoke(
            cli,
            [
                "--url",
                "http://ace.test",
                "cognition",
                "teach",
                "task:source",
                "--stable-key",
                "market_signal_review",
                "--name",
                "Market Signal Review",
                "--description",
                "Review a market signal with explicit counterevidence.",
                "--intent",
                "Reuse an accepted market-intelligence reasoning pattern.",
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["selectable"] is False
    assert request.call_args.args[:3] == ("POST", "http://ace.test/cognition/proposals/from-task")
    body = request.call_args.kwargs["json"]
    assert body["task_id"] == "task:source"
    assert body["stable_key"] == "market_signal_review"


def test_cognition_review_surfaces_human_authority_failure_without_mutation() -> None:
    with (
        patch("core.engine.cli.commands.cognition.get_headers", return_value={}),
        patch(
            "core.engine.cli.commands.cognition.httpx.request",
            return_value=_response(403, {"detail": {"code": "human_authority_required"}}),
        ),
    ):
        result = CliRunner().invoke(
            cli,
            [
                "--url",
                "http://ace.test",
                "cognition",
                "review",
                "cognition_proposal:abc",
                "--review-request-id",
                "review:one",
                "--disposition",
                "approve",
                "--rationale",
                "Reviewed exact semantic change.",
            ],
        )

    assert result.exit_code != 0
    assert "human_authority_required" in result.output


def test_cognition_use_requires_exact_stable_key_and_prints_attribution() -> None:
    task = {
        "id": "task:fresh",
        "status": "completed",
        "cognition_selection_receipt": {"selected_revision_ids": ["cognition_revision:exact"]},
        "cognition_use_receipt": {
            "selected_revision_ids": ["cognition_revision:exact"],
            "state": "used",
            "material_use_hash": "a" * 64,
        },
    }
    with (
        patch("core.engine.cli.commands.cognition.get_headers", return_value={}),
        patch("core.engine.cli.commands.cognition._submit_and_wait", return_value=(task, None)) as submit,
    ):
        result = CliRunner().invoke(
            cli,
            [
                "--url",
                "http://ace.test",
                "cognition",
                "use",
                "market_signal_review",
                "Re-evaluate this new market signal.",
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["cognition_use_receipt"]["selected_revision_ids"] == ["cognition_revision:exact"]
    assert submit.call_args.args[1]["force_skill"] == "market_signal_review"


def test_cognition_use_fails_closed_without_material_use_attribution() -> None:
    task = {
        "id": "task:fresh",
        "status": "completed",
        "cognition_selection_receipt": {"selected_revision_ids": ["cognition_revision:exact"]},
        "cognition_use_receipt": {
            "selected_revision_ids": ["cognition_revision:exact"],
            "state": "selected_not_used",
            "material_use_hash": "a" * 64,
        },
    }
    with (
        patch("core.engine.cli.commands.cognition.get_headers", return_value={}),
        patch("core.engine.cli.commands.cognition._submit_and_wait", return_value=(task, None)),
    ):
        result = CliRunner().invoke(
            cli,
            [
                "--url",
                "http://ace.test",
                "cognition",
                "use",
                "market_signal_review",
                "Re-evaluate this new market signal.",
            ],
        )

    assert result.exit_code != 0
    assert "cognition_use_attribution_incomplete" in result.output


def test_cognition_lifecycle_posts_generation_checked_retirement() -> None:
    receipt = {
        "lifecycle_receipt": {
            "action": "retire",
            "expected_generation": 2,
            "result_generation": 3,
            "result_lifecycle": "retired",
        }
    }
    with (
        patch("core.engine.cli.commands.cognition.get_headers", return_value={}),
        patch("core.engine.cli.commands.cognition.httpx.request", return_value=_response(200, receipt)) as request,
    ):
        result = CliRunner().invoke(
            cli,
            [
                "--url",
                "http://ace.test",
                "cognition",
                "lifecycle",
                "cognition_head:abc",
                "--review-request-id",
                "review:retire",
                "--action",
                "retire",
                "--rationale",
                "No longer eligible for selection.",
                "--expected-generation",
                "2",
            ],
        )

    assert result.exit_code == 0, result.output
    body = request.call_args.kwargs["json"]
    assert body == {
        "review_request_id": "review:retire",
        "action": "retire",
        "rationale": "No longer eligible for selection.",
        "expected_head_generation": 2,
    }

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.unit


def _event_stream_events(fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        event["native_event_coordinate"]: {
            "participant": event["native_participant_coordinate"],
            "role": event["role"],
            "kind": event["kind"],
            "body": event["body"],
            "world_time": event["world_time"],
            "order": event["native_order"],
            "span": event["source_span"],
        }
        for event in fixture["adapter_inputs"][0]["events"]
    }


def _transcript_events(fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for message in fixture["adapter_inputs"][1]["messages"]:
        locator = message["locator"]
        span = (
            {"kind": "unavailable", "reason": "adapter_unsupported"}
            if locator is None
            else {
                "kind": "byte_range",
                "start_byte": locator["utf8_start"],
                "end_byte": locator["utf8_end"],
            }
        )
        normalized[message["message_key"]] = {
            "participant": message["speaker"]["key"],
            "role": message["speaker"]["type"],
            "kind": message["payload"]["type"],
            "body": message["payload"]["text"],
            "world_time": message["occurred_at"],
            "order": message["position"],
            "span": span,
        }
    return normalized


def test_frozen_inputs_are_materially_distinct_but_semantically_identical(
    am1_fixture: dict[str, Any],
) -> None:
    event_stream, transcript = am1_fixture["adapter_inputs"]

    assert event_stream["adapter_ref"] != transcript["adapter_ref"]
    assert set(event_stream) != set(transcript)
    assert [event["native_event_coordinate"] for event in event_stream["events"]] == [
        "event-001",
        "event-002",
        "event-003",
    ]
    assert [message["message_key"] for message in transcript["messages"]] == [
        "event-003",
        "event-001",
        "event-002",
    ]
    assert _event_stream_events(am1_fixture) == _transcript_events(am1_fixture)


def test_frozen_byte_spans_are_exact_utf8_ranges(am1_fixture: dict[str, Any]) -> None:
    for event in am1_fixture["adapter_inputs"][0]["events"]:
        span = event["source_span"]
        if span["kind"] == "unavailable":
            assert event["role"] == "tool"
            assert span == {"kind": "unavailable", "reason": "adapter_unsupported"}
            continue
        assert span["end_byte"] - span["start_byte"] == len(event["body"].encode("utf-8"))


def test_fixture_scope_is_core_authenticated_not_adapter_supplied(am1_fixture: dict[str, Any]) -> None:
    authenticated_scope = am1_fixture["authenticated_scope"]
    assert authenticated_scope["product_id"].startswith("product:")
    assert authenticated_scope["actor_id"].startswith("principal:")
    for adapter_input in am1_fixture["adapter_inputs"]:
        assert "authenticated_scope" not in adapter_input
        assert "product_id" not in adapter_input
        assert "actor_id" not in adapter_input
        assert "authority_receipt_ref" not in adapter_input


def test_fixture_freezes_the_required_fail_closed_matrix(am1_fixture: dict[str, Any]) -> None:
    assert set(am1_fixture["required_cases"]) == {
        "cross_product_read",
        "divergent_replay",
        "duplicate_exact_event",
        "exact_replay",
        "hostile_payload_scope",
        "indeterminate_append",
        "lifecycle_restricted_read",
        "missing_native_session_coordinate",
        "missing_source_time",
        "out_of_order_with_coordinates",
        "out_of_order_without_coordinates",
        "partial_write",
        "private_body_projection",
        "restart_replay",
        "unknown_adapter_version",
    }
    relations = am1_fixture["expected_canonical_relations"]
    assert relations["same_processing_order"] == ["event-001", "event-002", "event-003"]
    assert relations["missing_world_time_remains_unknown"] == ["event-002", "event-003"]
    assert relations["tool_result_grants_authority"] is False
    assert relations["public_receipt_contains_body"] is False

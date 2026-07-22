from __future__ import annotations

from core.engine.core.access import access_profile_for
from core.engine.core.provider_runtime import (
    attach_resolution,
    note_provider_attempt,
    provider_attempt_scope,
    provider_resolution,
)


def test_resolution_provenance_is_attached_without_wrapping_provider() -> None:
    class CLIProvider:
        pass

    provider = CLIProvider()
    resolved = attach_resolution(
        provider,
        9,
        "forced_cli_provider",
        "FORCE_CLI_PROVIDER selected Claude CLI",
    )

    assert resolved is provider
    resolution = provider_resolution(provider)
    assert resolution is not None
    assert resolution.public_dict() == {
        "slot": 9,
        "selected_by": "forced_cli_provider",
        "reason": "FORCE_CLI_PROVIDER selected Claude CLI",
    }


def test_access_profile_exposes_resolution_without_secrets() -> None:
    class CLIProvider:
        pass

    provider = attach_resolution(
        CLIProvider(),
        9,
        "available_cli",
        "Claude CLI was the first available subscription route",
    )
    payload = access_profile_for(provider).public_dict()

    assert payload["resolver_slot"] == 9
    assert payload["selected_by"] == "available_cli"
    assert payload["resolution_reason"] == "Claude CLI was the first available subscription route"
    assert "token" not in str(payload).lower()


def test_attempt_scope_counts_nested_physical_attempts() -> None:
    with provider_attempt_scope() as attempts:
        note_provider_attempt()
        note_provider_attempt()
        note_provider_attempt()

    assert attempts.count == 3


def test_attempt_outside_scope_is_a_noop() -> None:
    note_provider_attempt()

"""Startup configuration regressions found by clean onboarding trials."""

from pathlib import Path

from core.engine.api.main import _optional_numeric_id


def test_example_discord_credentials_are_inactive():
    env_example = (Path(__file__).parents[1] / ".env.example").read_text()

    assert "\nACE_DISCORD_BOT_TOKEN=" not in env_example
    assert "\nACE_DISCORD_USER_ID=" not in env_example
    assert "\nACE_DISCORD_CHANNEL_ID=" not in env_example


def test_invalid_optional_discord_id_does_not_block_startup(caplog):
    assert _optional_numeric_id("your-discord-user-id", "ACE_DISCORD_USER_ID") is None
    assert "Discord notifications are disabled" in caplog.text


def test_valid_optional_discord_id_is_parsed():
    assert _optional_numeric_id("123456789", "ACE_DISCORD_USER_ID") == 123456789

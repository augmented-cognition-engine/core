# tests/test_cli_briefing.py
def test_briefing_command_exists():
    from core.engine.cli.commands.briefing import briefing, list_briefings

    assert briefing is not None
    assert list_briefings is not None
    assert briefing.name == "briefing"

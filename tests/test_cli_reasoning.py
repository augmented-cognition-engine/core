# tests/test_cli_reasoning.py
def test_frameworks_command_exists():
    from core.engine.cli.commands.reasoning import frameworks, get_framework

    assert frameworks is not None
    assert get_framework is not None
    assert frameworks.name == "frameworks"

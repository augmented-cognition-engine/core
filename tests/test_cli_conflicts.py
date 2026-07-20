# tests/test_cli_conflicts.py
def test_conflicts_command_exists():
    from core.engine.cli.commands.conflicts import conflicts, resolve_conflict

    assert conflicts is not None
    assert resolve_conflict is not None
    assert conflicts.name == "conflicts"

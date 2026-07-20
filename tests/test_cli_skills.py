# tests/test_cli_skills.py
def test_skills_command_exists():
    from core.engine.cli.commands.skills import get_skill, skills

    assert skills is not None
    assert get_skill is not None
    assert skills.name == "skills"

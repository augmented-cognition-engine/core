"""ACE was being asked to modify code it had never read.

Build #3 finished cleanly and refused to do the work, and it was RIGHT to:

    concerns: ['Blocker: Cannot write accurate docstring without access to
               core/engine/arms/registry.py — must document the actual registration
               mechanism, routing logic and thread-safety guarantees as implemented,
               not hypothetical']

The code arm's context is ace_load (graph knowledge) plus ace_blast_radius (dependencies). Neither
reads a single line of the file being changed. So the arm was asked to write a docstring for a file
it had never seen — and the no-slop bar did its job: it declined to fabricate rather than inventing
a plausible-sounding docstring about code it could not read.

Which exposes something worse, latent this whole time: write_file writes WHOLE-FILE content. An arm
modifying a file it has not read could emit a stub and TRUNCATE the real file to nothing. The only
reason that has never happened is that the model kept refusing to guess. "It never fired" is not a
safety property.

So: read the target before writing it, demand COMPLETE content when modifying, and guard the
catastrophic case where a file comes back mysteriously smaller than it went in.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_the_arm_reads_the_files_the_intent_names(tmp_path, monkeypatch):
    """The fix for the blocker: if the intent names a file, its SOURCE reaches the model."""
    import core.engine.arms.code_planner as cp

    target = tmp_path / "registry.py"
    target.write_text("def register_arm(cls):\n    _registry.append(cls)\n    return cls\n")
    monkeypatch.chdir(tmp_path)

    out = await cp.default_read_targets("Add a module-level docstring to registry.py explaining registration")

    assert "registry.py" in out, "the file named in the intent must be read"
    assert "def register_arm" in out["registry.py"], "and its ACTUAL SOURCE must be what we carry"


@pytest.mark.asyncio
async def test_reading_is_bounded_and_never_explodes(tmp_path, monkeypatch):
    """A huge file must not blow the context, and a missing one must not blow the build."""
    import core.engine.arms.code_planner as cp

    (tmp_path / "big.py").write_text("x = 1\n" * 100_000)
    monkeypatch.chdir(tmp_path)

    out = await cp.default_read_targets("refactor big.py and also nonexistent_file.py")

    assert len(out["big.py"]) <= 60_000, "a huge file must be truncated, not swallowed whole"
    assert "nonexistent_file.py" not in out, "a file that is not there is simply not context"


@pytest.mark.asyncio
async def test_no_paths_in_the_intent_is_not_an_error(tmp_path, monkeypatch):
    import core.engine.arms.code_planner as cp

    monkeypatch.chdir(tmp_path)
    assert await cp.default_read_targets("make the thing faster") == {}


def test_the_codegen_prompt_demands_COMPLETE_content_when_modifying():
    """write_file writes whole files. A fragment returned for an existing path DESTROYS it."""
    from core.engine.arms.code_planner import _CODEGEN_PROMPT

    p = _CODEGEN_PROMPT.lower()
    assert "complete" in p or "entire" in p, "modifying a file requires its COMPLETE new content"
    assert "truncat" in p or "fragment" in p or "snippet" in p, (
        "and it must say why: a fragment written to an existing path truncates the file"
    )


@pytest.mark.asyncio
async def test_a_write_that_would_gut_an_existing_file_is_REFUSED(tmp_path):
    """The guard that should have existed all along. An arm that never read a file could emit a stub
    and silently destroy it. The workspace is reversible, so this is not fatal — but a build that
    'passed' while deleting a module is exactly the silent catastrophe this codebase keeps finding."""
    from core.engine.arms.execution.executors import write_file

    original = "def a():\n    pass\n" * 200  # a substantial existing module
    (tmp_path / "mod.py").write_text(original)

    with pytest.raises(Exception) as exc:
        write_file(str(tmp_path), {"path": "mod.py", "content": "# TODO: implement\n"})

    assert "truncat" in str(exc.value).lower() or "shrink" in str(exc.value).lower(), (
        "gutting an existing file must be refused loudly, not written silently"
    )
    assert (tmp_path / "mod.py").read_text() == original, "and the file must be untouched"


def test_a_legitimate_large_edit_is_still_allowed(tmp_path):
    """The guard must not block real work: adding a docstring GROWS the file, and a genuine
    refactor that halves a file is still legal — only a catastrophic gutting is refused."""
    from core.engine.arms.execution.executors import write_file

    (tmp_path / "mod.py").write_text("def a():\n    pass\n" * 100)

    grown = '"""A module docstring."""\n\n' + ("def a():\n    pass\n" * 100)
    write_file(str(tmp_path), {"path": "mod.py", "content": grown})
    assert (tmp_path / "mod.py").read_text().startswith('"""A module docstring."""')

    # A real refactor that removes half the file is still permitted.
    halved = "def a():\n    pass\n" * 50
    write_file(str(tmp_path), {"path": "mod.py", "content": halved})
    assert (tmp_path / "mod.py").read_text() == halved


def test_creating_a_brand_new_file_is_untouched(tmp_path):
    """Nothing to truncate — a new file has no prior content to protect."""
    from core.engine.arms.execution.executors import write_file

    write_file(str(tmp_path), {"path": "new.py", "content": "x = 1\n"})
    assert (tmp_path / "new.py").read_text() == "x = 1\n"

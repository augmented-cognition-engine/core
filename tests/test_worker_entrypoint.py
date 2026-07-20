"""The worker's entrypoint must actually resolve.

The `core/` reorg moved the tree from `engine/` to `core/engine/` and broke start.py in
two places at once, both silent:

  - `sys.path.insert(...)` walked up one level too few, landing on `.../ace/core` — the
    INSIDE of the package instead of its parent.
  - `uvicorn.run("engine.worker.app:app")` still named the old module.

The pair is nastier than either alone. With `core` on the path, `engine.worker.app`
half-resolves (there IS a `core/engine/worker/app.py`), so uvicorn finds a module and the
failure surfaces later and elsewhere — inside the app's own `from core.engine…` imports —
looking like an unrelated import bug rather than a broken entrypoint.

Meanwhile the MCP tool that auto-restarts a dead worker shelled out to it on every
failure, so the restart could never succeed, and the tool's advice to the human ("run:
python engine/worker/start.py") pointed at a path that no longer existed. Sixteen failed
attempts sat in /tmp/ace-worker.log and nothing surfaced.

Nothing here imports the worker at test time (it binds a port and opens a DB pool). These
assert the WIRING — which is what broke.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
START = REPO / "core" / "engine" / "worker" / "start.py"


def test_the_start_script_is_where_everything_says_it_is() -> None:
    assert START.is_file(), f"{START} — the entrypoint the MCP restart path shells out to"


def test_the_uvicorn_target_is_a_real_importable_module() -> None:
    """The regression, stated exactly: `engine.worker.app` is NOT importable; the module
    lives at `core.engine.worker.app`."""
    src = START.read_text()
    m = re.search(r'uvicorn\.run\(\s*["\']([^"\':]+):(\w+)["\']', src)
    assert m, "start.py no longer calls uvicorn.run with a module:attr target"
    module, attr = m.group(1), m.group(2)

    assert module == "core.engine.worker.app", (
        f"start.py targets {module!r}. After the core/ reorg the module is "
        f"`core.engine.worker.app` — the old name half-resolves and fails later, elsewhere."
    )
    assert importlib.util.find_spec(module) is not None, f"{module} is not importable"

    tree = ast.parse((REPO / "core/engine/worker/app.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assigned = {t.id for s in tree.body if isinstance(s, ast.Assign) for t in s.targets if isinstance(t, ast.Name)}
    assert attr in (names | assigned), f"{module} defines no `{attr}`"


def test_the_path_insert_reaches_the_repo_root_not_the_package_inside() -> None:
    """`core.engine.*` only resolves if the REPO ROOT is on sys.path. Inserting
    `.../ace/core` puts the package's inside on the path and resolves nothing."""
    src = START.read_text()
    assert "parents[3]" in src, (
        "start.py must insert the repo root. From core/engine/worker/start.py that is "
        "parents[3]: worker -> engine -> core -> <repo>."
    )
    # Prove it, rather than trusting the index.
    assert START.resolve().parents[3] == REPO, f"parents[3] of {START} is {START.resolve().parents[3]}, expected {REPO}"


def test_nothing_still_tells_a_human_to_run_the_dead_path() -> None:
    """The MCP tool's own failure message advised a command that could not work — the one
    moment a person is most likely to copy it verbatim."""
    stale = []
    for path in REPO.glob("core/**/*.py"):
        if "test" in path.parts:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"(?<!core/)engine/worker/start\.py", line):
                stale.append(f"{path.relative_to(REPO)}:{i}")
    assert not stale, f"stale `engine/worker/start.py` references (path is core/…): {stale}"

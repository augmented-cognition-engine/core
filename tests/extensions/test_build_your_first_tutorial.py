"""The tutorial IS the test: run docs/build-your-first-extension.md's
scaffold flow exactly as written and prove the result is discovered."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "build-your-first-extension.md"


def test_tutorial_names_the_scaffold_command():
    text = DOC.read_text(encoding="utf-8")
    assert "python -m scripts.scaffold_extension" in text
    assert "extension-api.md" in text
    assert "flavor" not in text.lower()


def test_tutorial_dev_loop_teaches_server_side_loading():
    """Review fix (Task 9): the `ace` CLI is an HTTP client — extensions load
    in the ENGINE process (recipe loader / instrument registry / sentinel
    scheduler call ensure_loaded there). The dev-loop section must show (1)
    the in-process verification command and (2) exporting the env in the
    shell that launches `make dev` — never an env-prefixed one-off `ace`
    client call, which has zero effect on a separately-launched engine."""
    text = DOC.read_text(encoding="utf-8")
    # (1) the quick in-process check — mirrored by test_tutorial_flow_end_to_end
    assert "from core.engine.extensions.loader import load_extensions; print(load_extensions())" in text
    # (2) the live loop: env exported in the shell that LAUNCHES the engine
    assert 'export ACE_EXTENSIONS="green_energy_extension.extension:GreenEnergyExtension"' in text
    assert "make dev" in text
    assert 'ace run "' in text
    # the broken form must never come back: ACE_EXTENSIONS=... prefixing a
    # one-off `ace` client invocation
    assert re.search(r'ACE_EXTENSIONS="[^"]*"\s+ace\b', text) is None


def test_tutorial_documents_ace_login_before_first_ace_run():
    """OSS Task 8c: `ace login` replaces Task 9b's 12-line manual
    curl/python/chmod token bootstrap. `ace run` calls POST /tasks, which
    requires a bearer token — the dev-loop section must show `ace login`
    minting one via POST /auth/token and writing it where the CLI's own
    get_token() reads it (~/.ace/token.json), BEFORE the first `ace run`
    line — verified by execution, not just doc presence (see
    test_tutorial_flow_end_to_end / manual proof in the task report)."""
    text = DOC.read_text(encoding="utf-8")
    assert "POST /auth/token" in text
    assert "~/.ace/token.json" in text
    assert "core.engine.cli.auth.get_token" in text
    assert "ace login" in text
    login_idx = text.index("ace login")
    first_ace_run_idx = text.index('ace run "')
    assert login_idx < first_ace_run_idx, "`ace login` must appear before the first `ace run` invocation"
    # Security hardening: the token file holds a live bearer credential — the
    # doc must say it's locked down (save_config chmods it 0600), and the
    # stale "no ace login subcommand yet" disclaimer must not come back.
    assert "0600" in text
    assert "there's no `ace login` subcommand yet" not in text


def test_tutorial_flow_end_to_end(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    run = subprocess.run(
        [sys.executable, "-m", "scripts.scaffold_extension", "green_energy", "--dir", str(tmp_path)],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    root = tmp_path / "ace-ext-green-energy"
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "from core.engine.extensions.loader import load_extensions;"
            "l = load_extensions();"
            "assert 'green_energy_extension.extension:GreenEnergyExtension' in l, l;"
            "print('ok')",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(root),
            "ACE_EXTENSIONS": "green_energy_extension.extension:GreenEnergyExtension",
            "HOME": str(tmp_path),
            # core/engine/core/config.py's Settings() is instantiated at import time and
            # requires jwt_secret/llm_api_key. tests/conftest.py sets these via
            # os.environ.setdefault for the pytest PROCESS, but this scrubbed env={}
            # dict starts a child process with none of that — on the dev box it still
            # worked because pydantic's env_file=".env" found a real (gitignored) .env;
            # the export tree ships no .env, so the child's Settings() raised
            # ValidationError and this probe failed with "extension failed to register".
            # Obviously-fake test values, mirroring conftest.py's.
            "JWT_SECRET": "test-secret-for-pytest-only",
            "LLM_API_KEY": "sk-test",
        },
    )
    assert probe.returncode == 0, probe.stderr
    assert "ok" in probe.stdout

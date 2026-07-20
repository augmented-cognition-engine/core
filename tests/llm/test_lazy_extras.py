# tests/llm/test_lazy_extras.py
"""Lazy-import discipline for the optional router extras (litellm, any-llm).

The base install must NEVER import litellm/any_llm at module-import time —
these tests run REGARDLESS of whether the extras are installed, by poisoning
`sys.modules` (None entry → `import x` raises ImportError, the documented
import-blocker pattern), so they keep guarding the seam even on a machine
where someone installed the extras.

Two layers:
- Subprocess test: a FRESH interpreter with both SDKs poisoned imports
  core.engine.core.llm and both adapter modules cleanly, and provider
  construction raises the actionable install hint. Subprocess isolation
  avoids re-importing already-loaded ACE modules in-process, which would
  fork module identities out from under every other test's monkeypatching.
- In-process tests: the constructors' actionable errors, exercised against
  the already-imported modules with only the SDK names poisoned (safe — no
  ACE module is re-imported).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Runs in a fresh interpreter: poison BOTH SDK imports before anything else,
# then prove the base install's LLM stack imports and fails actionably.
_SUBPROCESS_PROBE = """
import sys
sys.modules["litellm"] = None   # import blocker: `import litellm` now raises ImportError
sys.modules["any_llm"] = None

import core.engine.core.llm  # the kernel module must import with no router SDKs
import core.engine.core.llm_litellm as llm_litellm   # adapter MODULES import lazily too
import core.engine.core.llm_anyllm as llm_anyllm

try:
    llm_litellm.LiteLLMProvider(default_model="anthropic/claude-sonnet-4-6")
except RuntimeError as exc:
    assert "ace[litellm]" in str(exc), f"install hint missing: {exc}"
else:
    raise AssertionError("LiteLLMProvider constructed without the litellm extra")

try:
    llm_anyllm.AnyLLMProvider(default_model="anthropic/claude-sonnet-4-6")
except RuntimeError as exc:
    assert "ace[any-llm]" in str(exc), f"install hint missing: {exc}"
else:
    raise AssertionError("AnyLLMProvider constructed without the any-llm extra")

print("LAZY_IMPORT_OK")
"""


def test_base_install_imports_cleanly_without_router_sdks():
    """The whole seam in one hermetic interpreter: base llm module + both
    adapter modules import with the SDKs absent; constructors raise the
    actionable pip-install hints."""
    # Scrub the router activation knobs: an ambient LITELLM_MODEL in the host
    # env would (correctly!) make the module-bottom get_llm() raise the install
    # hint — but this test pins the import seam, not that behavior.
    env = {k: v for k, v in os.environ.items() if k not in ("LITELLM_MODEL", "ANYLLM_MODEL")}
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_PROBE],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "LAZY_IMPORT_OK" in proc.stdout


def test_litellm_provider_raises_actionable_error_when_extra_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "litellm", None)
    from core.engine.core.llm_litellm import LiteLLMProvider

    with pytest.raises(RuntimeError, match=r"ace\[litellm\]") as excinfo:
        LiteLLMProvider(default_model="anthropic/claude-sonnet-4-6")
    # Chained from the real ImportError, and the security floor is named.
    assert isinstance(excinfo.value.__cause__, ImportError)
    assert "1.83.7" in str(excinfo.value)


def test_anyllm_provider_raises_actionable_error_when_extra_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "any_llm", None)
    from core.engine.core.llm_anyllm import AnyLLMProvider

    with pytest.raises(RuntimeError, match=r"ace\[any-llm\]") as excinfo:
        AnyLLMProvider(default_model="anthropic/claude-sonnet-4-6")
    assert isinstance(excinfo.value.__cause__, ImportError)


def test_get_llm_surfaces_install_hint_when_litellm_model_set_but_extra_absent(monkeypatch):
    """Explicit config + missing dependency = loud fail with the install hint —
    never a silent fall-through to a different (differently-billed) backend."""
    import core.engine.core.llm as llm_mod

    monkeypatch.setitem(sys.modules, "litellm", None)
    monkeypatch.setattr(llm_mod.settings, "litellm_model", "groq/llama-3.3-70b-versatile", raising=False)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", None, raising=False)

    with pytest.raises(RuntimeError, match=r"ace\[litellm\]"):
        llm_mod.get_llm()


def test_get_llm_surfaces_install_hint_when_anyllm_model_set_but_extra_absent(monkeypatch):
    import core.engine.core.llm as llm_mod

    monkeypatch.setitem(sys.modules, "any_llm", None)
    monkeypatch.setattr(llm_mod.settings, "litellm_model", None, raising=False)
    monkeypatch.setattr(llm_mod.settings, "anyllm_model", "anthropic/claude-sonnet-4-6", raising=False)

    with pytest.raises(RuntimeError, match=r"ace\[any-llm\]"):
        llm_mod.get_llm()

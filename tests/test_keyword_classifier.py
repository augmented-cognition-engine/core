"""The keyword classifier is ONE canonical implementation in core, shared by the
hook and the worker, so their instant-classify behavior can never drift.

Before unification the map was copied in .claude/hooks/ace-intelligence.py and
core/engine/worker/classifier.py — two sources of truth to keep in sync by hand.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

_HOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude", "hooks")
_HAS_PRIVATE_HOOKS = os.path.isdir(_HOOKS_DIR)
_skip_no_hooks = pytest.mark.skipif(
    not _HAS_PRIVATE_HOOKS, reason="requires private .claude/hooks/ (not shipped in the public export)"
)

_PROMPTS = [
    "add a pytest fixture with coverage",
    "harden the auth token validation against injection",
    "define the surrealdb schema migration and index",
    "design the rest api endpoints and openapi",
    "refactor the module architecture and imports",
    "fix the crash traceback and the broken exception",
    "good morning to you all",  # no keyword hit → None
    "just a quick note",  # no confident hit → None
]


def _load_hook():
    hook_path = os.path.join(_HOOKS_DIR, "ace-intelligence.py")
    spec = importlib.util.spec_from_file_location("ace_intelligence", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_canonical_classifies():
    from core.engine.keyword_classifier import keyword_classify

    assert keyword_classify("add a pytest fixture with coverage")["discipline"] == "testing"
    assert keyword_classify("good morning to you all") is None


def test_worker_reexports_canonical_not_a_copy():
    from core.engine.keyword_classifier import keyword_classify as canonical
    from core.engine.worker.classifier import keyword_classify as worker_kc

    assert worker_kc is canonical, "worker must re-export the canonical classifier, not keep its own copy"


@_skip_no_hooks
def test_hook_delegates_to_canonical():
    from core.engine.keyword_classifier import keyword_classify as canonical

    hook = _load_hook()
    for p in _PROMPTS:
        assert hook.keyword_classify(p) == canonical(p), f"hook keyword_classify drifted from canonical on: {p!r}"

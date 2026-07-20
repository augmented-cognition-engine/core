"""Voice-rule sentinel for onboarding conversation copy.

Verifies the canonical conversation_copy.json passes the rules currently
implemented in engine/voice/rules.py + does not contain EmptyState's forbidden
strings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine.voice.rules import find_forbidden_strings, has_we_voice

COPY_PATH = Path("core/engine/onboarding/conversation_copy.json")


@pytest.fixture(scope="module")
def copy():
    return json.loads(COPY_PATH.read_text(encoding="utf-8"))


def test_no_forbidden_strings(copy):
    """No FORBIDDEN_STRINGS in any conversation text."""
    texts = [copy["opening"], copy["closing_template"]]
    for q in copy["questions"]:
        texts.append(q["prompt"])
        texts.append(q["ack_template"])
    for t in texts:
        forbidden = find_forbidden_strings(t)
        assert forbidden == [], f"forbidden strings in {t!r}: {forbidden}"


def test_opening_has_we_voice(copy):
    """Opening must have we-voice (long-form partner intro). Closing is a one-line summary, exempt."""
    assert has_we_voice(copy["opening"])


def test_no_engine_runs_summarized_leakage(copy):
    """The seeded-history sentinel: no engine_runs_summarized substring anywhere."""
    serialized = json.dumps(copy)
    assert "engine_runs_summarized" not in serialized.lower()


def test_does_not_match_empty_state_forbidden_texts(copy):
    """The 7 strings in EmptyState's FORBIDDEN_TEXTS must not appear in any copy text."""
    # Mirror of portal/src/components/workspace/EmptyState.tsx FORBIDDEN_TEXTS
    # (canonical source: portal/src/components/workspace/EmptyState.tsx exports EMPTY_STATE_FORBIDDEN_TEXTS)
    empty_state_forbidden = [
        "Welcome!",
        "Get started",
        "Tutorial",
        "Sign up",
        "Click here to begin",
        "Click to continue",
        "Onboarding",
    ]
    serialized = json.dumps(copy).lower()
    for s in empty_state_forbidden:
        assert s.lower() not in serialized, f"EmptyState forbidden text {s!r} appears in copy"


def test_4_questions_with_unique_indexes(copy):
    """Exactly 4 questions with indexes 1..4."""
    qs = copy["questions"]
    assert len(qs) == 4
    indexes = sorted(q["index"] for q in qs)
    assert indexes == [1, 2, 3, 4]

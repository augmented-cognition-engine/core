"""ACE failed a build three times because a docstring did not implement spoofing prevention.

The first build to run to completion:

    BUILD DONE in 21.8 min with 37 llm calls
    passed=False   changed=[]   diff=(empty)
    reason: unresolved after 3 repair(s): uncovered=['security - Documented unauthenticated
            registration model, spoofing prevention via handler interface validation ...']

The intent was "add a module-level docstring to registry.py".

The causal chain:
  1. The systems-thinking prompt UNCONDITIONALLY orders: "enumerate and address security,
     error-handling, retries, tests, observability, caching, deployment concerns."
  2. A docstring has none of those. So the model INVENTS them — it was told to.
  3. The no-slop critic then checks the code addresses every surfaced concern.
  4. A docstring cannot implement authentication. Uncovered -> repair -> regenerate -> still
     cannot -> three repairs -> FAIL. 37 calls, 22 minutes, an empty diff.

The quality bar became so aggressive that small work was STRUCTURALLY IMPOSSIBLE. That is not
rigor; rigor is enforcing the concerns that are REAL. Demanding a docstring solve spoofing is
fabrication, and fabricated concerns are slop wearing a high-vis jacket.

So the bar does not move: a concern that genuinely applies must still be covered, and a build that
ignores a real security surface must still fail. What changes is that "this change has no security
surface" becomes a legal — and expected — answer.
"""

from __future__ import annotations

import pytest


def test_the_reasoning_prompt_forbids_inventing_concerns():
    from core.engine.arms.code_planner import _SYSTEMS_PROMPT

    p = _SYSTEMS_PROMPT.lower()
    assert "apply" in p or "applies" in p, "it must ask which concerns APPLY, not demand all of them"
    assert "invent" in p or "fabricat" in p or "do not manufacture" in p, (
        "it must explicitly forbid inventing concerns. Told to enumerate security concerns for a "
        "docstring, a model will obey — and the no-slop gate will then enforce the fiction."
    )
    # The bar itself must survive: the categories are still named, so real ones are still hunted.
    assert "security" in p and "error" in p and "observability" in p


def test_the_codegen_prompt_allows_an_empty_concern_list():
    from core.engine.arms.code_planner import _CODEGEN_PROMPT

    p = _CODEGEN_PROMPT.lower()
    assert "empty" in p, "for a trivial change, NO concerns is the correct answer and must be sayable"
    assert "must address every concern" in p or "address every concern" in p, (
        "and the bar stays: a concern that IS listed must actually be covered by the code"
    )


@pytest.mark.asyncio
async def test_the_critic_passes_a_change_with_no_real_concerns():
    """The gate must accept 'nothing applies here' — otherwise trivial work can never pass."""
    from core.engine.arms.code_planner import default_critic

    class _WS:
        path = "/tmp/does-not-matter"

    ok, uncovered = await default_critic([], _WS())

    assert ok is True and uncovered == [], "no concerns => nothing to cover => the gate passes"


@pytest.mark.asyncio
async def test_the_critic_still_fails_a_change_that_ignores_a_REAL_concern(monkeypatch, tmp_path):
    """The bar does not move. A genuine, applicable concern left unaddressed still fails the build —
    that is the entire reason the gate exists."""
    import core.engine.arms.code_planner as cp

    (tmp_path / "handler.py").write_text(
        'def handle(req):\n    return db.query(f"SELECT * FROM t WHERE id={req.id}")\n'
    )

    class _LLM:
        async def complete_json(self, prompt, **kw):
            return {"uncovered": ["security - SQL built by f-string interpolation of request input"]}

    monkeypatch.setattr(cp, "get_llm", lambda: _LLM())

    class _WS:
        path = str(tmp_path)

    ok, uncovered = await cp.default_critic(["security - parameterise the query"], _WS())

    assert ok is False, "a REAL uncovered concern must still fail — the bar is not for sale"
    assert any("sql" in u.lower() for u in uncovered)

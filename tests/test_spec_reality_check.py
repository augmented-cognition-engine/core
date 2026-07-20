"""Never send an autonomous builder to build something that already exists.

Audited the 16 draft specs against the actual codebase before approving any of them. FIVE were
already fully implemented:

    "Create synthesizer layer (engine/orchestrator/synthesizer.py)"  -> it exists. 11 test files.
    "Implement seven memory layer enhancements"                      -> all seven exist.
    "Forkable foresight"                                             -> shipped, with schema v134.
    "Phase 3 systems design depth"                                   -> systems_map.py has all four.
    "MSP ops: discovery / multi-tenant / retainer"                   -> all three exist.

Had they been approved and left to run overnight, ACE would have faithfully, durably, and with an
excellent audit trail spent the night REBUILDING a synthesizer it already had — quite possibly
overwriting working code with a worse reimplementation of itself.

The backlog is the last lying instrument, and the most expensive: a green-looking record sitting
directly upstream of an autonomous builder. And ACE already had the antidote — ace_verify_implementation
queries the code graph for ground truth — it just never ran at the moment that mattered.

Two signals, and they are NOT equal:

  DETERMINISTIC   the spec names a file, and that file exists on disk. You cannot "create" a file
                  that is already there. This is fact, not inference, and it is free.
  GRAPH EVIDENCE  ace_verify_implementation says 'implemented'. Strong, but it is inference over a
                  scanned graph, and it can be wrong.

So the check reports BOTH, with its confidence and its evidence, and the loop SKIPS rather than
burning 20 minutes and 12 model calls — but it never silently deletes the spec. It says what it
found and hands the decision back. A gate may only refuse for what it has established
(the preflight lesson, learned the expensive way).
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_a_spec_naming_a_file_that_EXISTS_is_already_built(tmp_path, monkeypatch):
    """The deterministic signal, and the cheapest: you cannot create a file that is already there."""
    from core.engine.arms import spec_reality

    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "synthesizer.py").write_text("class Synthesizer: ...\n")
    monkeypatch.chdir(tmp_path)

    async def _no_graph(topic, product_id="product:platform"):
        return {"verdict": "not_found", "evidence": []}

    monkeypatch.setattr(spec_reality, "_graph_verdict", _no_graph)

    r = await spec_reality.check_spec_reality("Create synthesizer layer (engine/synthesizer.py) that aggregates")

    assert r.already_exists is True
    assert r.confidence == "certain", "a file on disk is a fact, not an inference"
    assert any("engine/synthesizer.py" in e for e in r.evidence)


@pytest.mark.asyncio
async def test_a_spec_naming_a_file_that_does_NOT_exist_is_real_work(tmp_path, monkeypatch):
    from core.engine.arms import spec_reality

    monkeypatch.chdir(tmp_path)

    async def _no_graph(topic, product_id="product:platform"):
        return {"verdict": "not_found", "evidence": []}

    monkeypatch.setattr(spec_reality, "_graph_verdict", _no_graph)

    r = await spec_reality.check_spec_reality("Create engine/does_not_exist.py to do the thing")

    assert r.already_exists is False


@pytest.mark.asyncio
async def test_a_spec_naming_no_file_is_judged_on_the_EVIDENCE_not_on_keyword_hits(tmp_path, monkeypatch):
    """ "Implement seven memory layer enhancements" names no path, so the graph has to catch it — and
    COUNTING KEYWORD HITS CANNOT DO THAT. Both failure modes were measured against the five specs
    that really were stale:

        multi-word topic  -> the graph CONTAINS-matches nothing  -> caught 1 of 5
        one word at a time -> 'seven', 'three', 'Phase' all match -> flagged 4 of 4 REAL specs as built

    The second is the dangerous one: it would skip every spec as "already built" and silently kill
    all the real work. So a model reads the evidence and judges whether the SPECIFIC work exists.
    """
    from core.engine.arms import spec_reality

    monkeypatch.chdir(tmp_path)

    async def _graph(topic, product_id="product:platform"):
        # The REAL shape ace_verify_implementation returns: files / functions / decisions.
        # There is no `evidence` key — reading one is what handed the judge an empty list and made
        # it answer "not built" for everything. A fake that lies about the contract tests nothing.
        return {
            "verdict": "implemented",
            "files": [
                {"path": "core/engine/capture/consolidator.py", "purpose": "memory consolidation"},
                {"path": "core/engine/sentinel/decay_manager.py", "purpose": "knowledge decay"},
            ],
            "functions": [{"name": "consolidate_memories"}],
        }

    judged = {}

    async def _judge(objective, evidence):
        judged["evidence"] = evidence
        from core.engine.arms.spec_reality import SpecReality

        return SpecReality(already_exists=True, confidence="likely", evidence=evidence[:2])

    monkeypatch.setattr(spec_reality, "_graph_verdict", _graph)
    monkeypatch.setattr(spec_reality, "_judge", _judge)

    r = await spec_reality.check_spec_reality("Implement seven memory layer enhancements: decay, consolidation")

    assert r.already_exists is True
    assert r.confidence == "likely", "the graph is inference, not fact — never claim 'certain'"
    assert any("decay_manager" in e for e in judged["evidence"]), "the JUDGE must see the real evidence"


@pytest.mark.asyncio
async def test_the_judge_is_strict_a_keyword_overlap_is_not_implementation(tmp_path, monkeypatch):
    """The guard that stops it flagging everything. A model that says "false" when the evidence is
    merely adjacent is the whole reason this is a judgement and not a word count."""
    from core.engine.arms import spec_reality

    monkeypatch.chdir(tmp_path)

    async def _graph(topic, product_id="product:platform"):
        # adjacent, not the thing — the judge must see this and still say no
        return {"verdict": "implemented", "files": [{"path": "utils/memory_helpers.py", "purpose": "helpers"}]}

    class _StrictJudge:
        async def complete_structured(self, prompt, schema, **kw):
            assert "keyword overlap is NOT implementation" in prompt.lower() or "keyword" in prompt.lower(), (
                "the judge must be TOLD that a keyword match is not implementation"
            )
            return schema(already_implemented=False, evidence=[], reasoning="only adjacent files")

    monkeypatch.setattr(spec_reality, "_graph_verdict", _graph)
    monkeypatch.setattr("core.engine.core.llm.get_llm", lambda: _StrictJudge())

    r = await spec_reality.check_spec_reality("Sleeptime consolidation (between-run rewrite)")

    assert r.already_exists is False, "adjacent evidence is NOT implementation — build it"


@pytest.mark.asyncio
async def test_the_check_never_raises_and_never_blocks_on_failure(monkeypatch):
    """A broken reality check must never stop a build. Fail OPEN here, deliberately: the cost of a
    false 'not built' is 20 wasted minutes; the cost of a false 'already built' is real work
    silently never happening. Those are not symmetric."""
    from core.engine.arms import spec_reality

    async def _boom(topic, product_id="product:platform"):
        raise RuntimeError("graph is down")

    monkeypatch.setattr(spec_reality, "_graph_verdict", _boom)

    r = await spec_reality.check_spec_reality("do something")

    assert r.already_exists is False, "when we cannot tell, we BUILD — never skip real work on a guess"
    assert "could not" in r.note.lower() or "unavailable" in r.note.lower()


@pytest.mark.asyncio
async def test_the_session_SKIPS_a_spec_that_is_already_built(monkeypatch):
    """The whole point: do not burn 20 minutes and 12 model calls rebuilding what exists."""
    import core.engine.arms.session as session
    from core.engine.arms.spec_reality import SpecReality

    built: list[str] = []
    queue = ["agent_spec:already_built", "agent_spec:real_work"]

    async def _next(product_id, pool=None, exclude=None):
        for s in queue:
            if s not in (exclude or set()):
                return s
        return None

    async def _reality(objective, product_id="product:platform"):
        if "already_built" in objective:
            return SpecReality(
                already_exists=True,
                confidence="certain",
                evidence=["core/engine/orchestrator/synthesizer.py exists"],
            )
        return SpecReality(already_exists=False, confidence="none", evidence=[])

    async def _objective(spec_id, pool=None):
        return spec_id  # the id doubles as the objective in this fake

    async def _build(spec_id, product_id="product:platform", pool=None):
        built.append(spec_id)
        return {"built": True, "branch": "arm/x"}

    async def _zero(*a, **kw):
        return 0

    monkeypatch.setattr(session, "_next_buildable_spec", _next)
    monkeypatch.setattr(session, "check_spec_reality", _reality)
    monkeypatch.setattr(session, "_spec_objective", _objective)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "reconcile_stale_runs", _zero)
    monkeypatch.setattr(session, "reconcile_stranded_specs", _zero)
    monkeypatch.setattr(session, "_count_unapproved_specs", _zero)

    out = await session.run_build_session(product_id="product:platform", max_builds=5)

    assert "agent_spec:already_built" not in built, "it must NOT rebuild what already exists"
    assert "agent_spec:real_work" in built, "and it must still do the work that IS real"
    assert out["already_built"], "and it must TELL you, with the evidence, so you can close the spec"
    assert "synthesizer.py" in str(out["already_built"])

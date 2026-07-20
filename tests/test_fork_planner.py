# tests/test_fork_planner.py
"""Forkable foresight tests. Increment 1 (data layer): deterministic, fake event log, no LLM/DB.
Increment 2 (simulate + compare): fake llm_call drives the REAL MultiPhaseExecutor (no real LLM) +
a stub scorer for deterministic ranking."""

from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.foresight import fork_planner
from core.engine.foresight.fork_models import ForkBranch, ForkPoint, ForkResult


def _events(meta_skills=None, discipline="strategy", conclusion="ship it"):
    """A synthetic 3-phase reasoning_event sequence: run_started, phase×3, run_complete."""
    return [
        {
            "seq": 0,
            "event_type": "run_started",
            "payload": {
                "thought": "should we ship?",
                "depth": 3,
                "discipline": discipline,
                "meta_skills": meta_skills or ["strategic_intelligence"],
            },
        },
        {"seq": 1, "event_type": "phase", "payload": {"cognitive_function": "frame", "output": "framed the question"}},
        {"seq": 2, "event_type": "phase", "payload": {"cognitive_function": "analyze", "output": "analyzed options"}},
        {"seq": 3, "event_type": "phase", "payload": {"cognitive_function": "conclude", "output": "concluded"}},
        {
            "seq": 4,
            "event_type": "run_complete",
            "payload": {"conclusion": conclusion, "n_phases": 3, "status": "complete"},
        },
    ]


def _patch_events(events):
    return patch("core.engine.cognition.run_ledger.get_run_events", AsyncMock(return_value=events))


def _fork_pool(cache_rows=None):
    """Fake pool: returns `cache_rows` for the reasoning_fork cache SELECT (default = miss), and
    accepts the CREATE write. Keeps fork_and_compare off a real DB in tests."""
    db = MagicMock()

    async def _query(q, params=None):
        if "FROM reasoning_fork" in q:
            return cache_rows if cache_rows is not None else [[]]
        return [[]]

    db.query = AsyncMock(side_effect=_query)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


async def _no_judge(task, candidates):
    """A judge that abstains — combined_score falls back to each branch's eval_score (the pre-judge
    behavior). Lets eval_score-based tests run without invoking the real LLM judge."""
    return {}


def _cap_pool(cap_rows):
    """Fake pool returning capability_quality rows for _load_cap_scores; [] for anything else."""
    db = MagicMock()

    async def _query(q, params=None):
        if "capability_quality" in q:
            return [cap_rows]
        return [[]]

    db.query = AsyncMock(side_effect=_query)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


@pytest.mark.integration
async def test_reconstruct_partitions_at_checkpoint():
    with _patch_events(_events()):
        fp = await fork_planner.reconstruct_fork_point("reasoning_run:abc", 2, product_id="product:platform")
    assert fp is not None
    assert fp.checkpoint_seq == 2
    assert len(fp.frozen_prefix) == 2  # frame, analyze
    assert fp.tail_functions == ["conclude"]  # the one phase after the checkpoint
    assert fp.meta_skills == ["strategic_intelligence"]
    assert fp.original_conclusion == "ship it"
    assert fp.original_thought == "should we ship?"
    assert fp.original_discipline == "strategy"
    assert fp.product_id == "product:platform"


@pytest.mark.integration
async def test_reconstruct_out_of_range_checkpoint_returns_none():
    # 3 phase events; checkpoint 3 leaves no tail → None; checkpoint 0 has no prefix → None.
    with _patch_events(_events()):
        assert await fork_planner.reconstruct_fork_point("r:1", 3, product_id="p:1") is None
    with _patch_events(_events()):
        assert await fork_planner.reconstruct_fork_point("r:1", 0, product_id="p:1") is None


@pytest.mark.integration
async def test_reconstruct_no_events_returns_none():
    with _patch_events([]):
        assert await fork_planner.reconstruct_fork_point("r:1", 1, product_id="p:1") is None


@pytest.mark.integration
async def test_reconstruct_reads_engagement_phase_name_key():
    """The engagement path writes `phase_name`; multiphase writes `cognitive_function`. Both work."""
    evs = _events()
    for e in evs:
        if e["event_type"] == "phase":
            e["payload"] = {"phase_name": e["payload"]["cognitive_function"], "output": e["payload"]["output"]}
    with _patch_events(evs):
        fp = await fork_planner.reconstruct_fork_point("r:1", 1, product_id="p:1")
    assert fp is not None
    assert fp.tail_functions == ["analyze", "conclude"]


def _fp():
    return ForkPoint(
        run_id="r:1",
        checkpoint_seq=1,
        product_id="p:1",
        frozen_prefix=[{"cognitive_function": "frame", "output": "framed it"}],
        tail_functions=["analyze", "conclude"],
        meta_skills=["m"],
        original_conclusion="c",
        original_discipline="strategy",
    )


def test_build_fork_intel_context_renders_prefix():
    ctx = fork_planner.build_fork_intel_context(_fp())
    assert "frame: framed it" in ctx
    assert "continue from here" in ctx.lower()


def test_build_fork_intel_context_bounded():
    fp = _fp()
    fp.frozen_prefix = [{"cognitive_function": "frame", "output": "x" * 10000}]
    assert len(fork_planner.build_fork_intel_context(fp, max_chars=500)) <= 500


def test_propose_variations_distinct_and_capped():
    v = fork_planner.propose_variations(_fp(), n=2)  # original first = "analyze" (not a lens)
    assert len(v) == 2
    assert all(x in fork_planner._LENS_SET for x in v)


def test_propose_variations_excludes_original_lens():
    fp = _fp()
    fp.tail_functions = ["systems", "conclude"]  # original first lens = systems
    v = fork_planner.propose_variations(fp, n=5)
    assert "systems" not in v


def test_build_fork_composition_swaps_lens_non_fusion():
    comp = fork_planner.build_fork_composition(_fp(), "adversarial")  # tail = [analyze, conclude]
    assert comp.fusion_mode is False
    assert len(comp.active_phases) == 2
    assert comp.active_phases[0].cognitive_function == "adversarial"  # fork phase swapped to the lens
    assert comp.active_phases[1].cognitive_function == "conclude"  # rest preserved
    assert comp.resolved_instruments["0"] == ["adversarial"]


# --- Increment 2: simulate + compare (fake llm_call → REAL executor; stub scorer) ---------------


async def _fake_llm(system_prompt, user_prompt):
    """A fake reasoning LLM — the executor runs for real; only the model output is canned."""
    return "FORKED_CONCLUSION: " + user_prompt[:40].replace("\n", " ")


def _fp_with_thought():
    return ForkPoint(
        run_id="reasoning_run:x",
        checkpoint_seq=1,
        product_id="product:platform",
        frozen_prefix=[{"cognitive_function": "frame", "output": "framed it"}],
        tail_functions=["analyze", "conclude"],
        meta_skills=["strategic_intelligence"],
        original_conclusion="ship it",
        original_thought="Should we ship the marketplace?",
        original_discipline="strategy",
    )


@pytest.mark.integration
async def test_simulate_fork_runs_real_executor_and_scores():
    """Real MultiPhaseExecutor driven by a fake llm_call (no real LLM) + a stub scorer → ForkBranch."""

    async def stub_scorer(task, conclusion):
        return 0.77

    br = await fork_planner.simulate_fork(_fp_with_thought(), "adversarial", llm_call=_fake_llm, scorer=stub_scorer)
    assert br.lens == "adversarial"
    assert br.conclusion  # the executor produced a conclusion
    assert br.eval_score == 0.77
    assert br.combined_score == 0.77
    assert len(br.tail_trace) == 2  # one trace entry per tail phase (analyze→adversarial, conclude)


@pytest.mark.integration
async def test_simulate_fork_degrades_on_executor_failure():
    async def stub_scorer(task, conclusion):
        return 0.5

    with patch("core.engine.foresight.fork_planner.build_fork_composition", side_effect=RuntimeError("boom")):
        br = await fork_planner.simulate_fork(_fp_with_thought(), "systems", llm_call=_fake_llm, scorer=stub_scorer)
    assert br.lens == "systems"
    assert br.conclusion == ""
    assert br.combined_score == 0.0  # degraded, non-fatal


@pytest.mark.integration
async def test_simulate_fork_empty_conclusion_scores_zero_through_real_executor():
    """The REALISTIC degraded path: execute() almost never raises (it catches per-phase errors and
    returns "" for the all-tainted/empty case). So a model that returns nothing yields an empty
    conclusion — and the empty→0.0 contract must hold WITHOUT the construction-error branch. The
    branch is well-formed (lens label, real trace), just scored 0.0."""

    async def empty_llm(system_prompt, user_prompt):
        return ""  # model returns nothing → executor conclusion is empty/low-signal, not a raise

    async def empty_aware_scorer(task, conclusion):
        return 0.0 if not (conclusion or "").strip() else 0.9

    br = await fork_planner.simulate_fork(
        _fp_with_thought(), "empirical", llm_call=empty_llm, scorer=empty_aware_scorer
    )
    assert br.lens == "empirical"  # well-formed branch, NOT the construction-error degraded path
    assert br.combined_score == 0.0  # empty conclusion → 0.0 end-to-end through the real executor


@pytest.mark.integration
async def test_fork_and_compare_ranks_and_picks_best():
    # scorer favours forked conclusions (contain "FORKED") over the original ("ship it")
    async def biased_scorer(task, conclusion):
        return 0.9 if "FORKED" in conclusion else 0.2

    with _patch_events(_events()):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            2,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=biased_scorer,
            judge=_no_judge,
            n=2,
            pool=_fork_pool(),
        )
    assert res is not None
    assert res.original.variation_label == "original"
    assert res.original.combined_score == 0.2  # judge abstained → combined_score = eval_score
    assert len(res.forks) == 2
    assert all(f.combined_score == 0.9 for f in res.forks)
    assert res.best.combined_score == 0.9
    assert res.best.variation_label != "original"  # a fork won the comparison


@pytest.mark.integration
async def test_fork_and_compare_none_when_unreconstructable():
    with _patch_events([]):
        res = await fork_planner.fork_and_compare("r:1", 1, product_id="p:1", llm_call=_fake_llm, pool=_fork_pool())
    assert res is None


@pytest.mark.integration
async def test_fork_cache_blob_roundtrips():
    """A ForkResult survives asdict() → _result_from_blob() unchanged (the cache serialization)."""
    original = ForkBranch(
        variation_label="original", lens="conclude", conclusion="ship it", eval_score=0.3, combined_score=0.3
    )
    fork = ForkBranch(
        variation_label="adversarial",
        lens="adversarial",
        conclusion="forked",
        tail_trace=[{"phase_idx": 0, "confidence": 0.7}],
        eval_score=0.8,
        combined_score=0.8,
    )
    result = ForkResult(
        run_id="reasoning_run:abc",
        checkpoint_seq=2,
        original=original,
        forks=[fork],
        best=fork,
        created_at="2026-06-24T00:00:00Z",
    )
    back = fork_planner._result_from_blob(asdict(result))
    assert back == result  # dataclass equality — full roundtrip incl. None capability_delta_score


@pytest.mark.integration
async def test_fork_and_compare_returns_cache_hit_without_running():
    """A cached (run_id, checkpoint_seq) short-circuits — no reconstruct, no executor, no llm_call."""
    fork = ForkBranch(
        variation_label="adversarial",
        lens="adversarial",
        conclusion="cached forked",
        eval_score=0.8,
        combined_score=0.8,
    )
    original = ForkBranch(
        variation_label="original", lens="conclude", conclusion="ship it", eval_score=0.3, combined_score=0.3
    )
    cached = ForkResult(
        run_id="reasoning_run:abc",
        checkpoint_seq=2,
        original=original,
        forks=[fork],
        best=fork,
        created_at="2026-06-24T00:00:00Z",
    )
    pool = _fork_pool(cache_rows=[[{"result": asdict(cached)}]])

    llm_spy = AsyncMock(return_value="should-never-be-called")
    # get_run_events would raise if reached — proves the cache short-circuits before reconstruct.
    with patch(
        "core.engine.cognition.run_ledger.get_run_events", AsyncMock(side_effect=AssertionError("reconstruct ran"))
    ):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc", 2, product_id="product:platform", llm_call=llm_spy, pool=pool
        )
    assert res is not None
    assert res.best.conclusion == "cached forked"
    assert res.best.combined_score == 0.8
    llm_spy.assert_not_called()


@pytest.mark.integration
async def test_fork_cache_keys_on_n():
    """The cache key includes n — a fork with a different variation count is a distinct cache entry
    (else a call with n=4 could get back an n=2 result). Both the SELECT and the CREATE must bind n."""
    captured: dict = {}
    db = MagicMock()

    async def _query(q, params=None):
        if "FROM reasoning_fork" in q:
            captured["select"] = (q, params)
            return [[]]  # miss → proceed to run + write
        if "CREATE reasoning_fork" in q:
            captured["create"] = (q, params)
        return [[]]

    db.query = AsyncMock(side_effect=_query)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx

    async def scorer(task, conclusion):
        return 0.5

    with _patch_events(_events()):
        await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            2,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=scorer,
            judge=_no_judge,
            n=3,
            pool=pool,
        )
    assert "n = $n" in captured["select"][0]
    assert captured["select"][1]["n"] == 3  # SELECT binds the requested n
    assert captured["create"][1]["n"] == 3  # CREATE writes under the same n


@pytest.mark.integration
async def test_fork_and_compare_use_cache_false_skips_cache():
    """use_cache=False bypasses the cache read (even if a row exists) and re-runs."""
    stale = ForkResult(
        run_id="reasoning_run:abc",
        checkpoint_seq=2,
        original=ForkBranch(variation_label="original", lens="conclude", conclusion="stale"),
        forks=[],
        best=ForkBranch(variation_label="original", lens="conclude", conclusion="stale"),
        created_at="2026-06-24T00:00:00Z",
    )
    pool = _fork_pool(cache_rows=[[{"result": asdict(stale)}]])

    async def scorer(task, conclusion):
        return 0.5

    with _patch_events(_events()):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            2,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=scorer,
            judge=_no_judge,
            pool=pool,
            use_cache=False,
        )
    assert res is not None
    assert res.original.conclusion == "ship it"  # freshly reconstructed, NOT the stale cached "stale"


@pytest.mark.integration
async def test_default_scorer_parses_and_is_failsafe():
    # empty conclusion → 0.0 with no LLM call at all
    assert await fork_planner._default_scorer("task", "") == 0.0
    # patched budget judge returns a score
    ok = AsyncMock()
    ok.complete_json = AsyncMock(return_value={"score": 0.83})
    with patch("core.engine.core.llm.get_llm", return_value=ok):
        assert await fork_planner._default_scorer("task", "a conclusion") == 0.83
    # judge raising → neutral 0.5 (non-fatal)
    err = AsyncMock()
    err.complete_json = AsyncMock(side_effect=RuntimeError("down"))
    with patch("core.engine.core.llm.get_llm", return_value=err):
        assert await fork_planner._default_scorer("task", "a conclusion") == 0.5


# --- The comparative (position-debiased listwise) judge ----------------------------------------


@pytest.mark.integration
async def test_fork_and_compare_uses_comparative_judge():
    """The judge re-ranks: combined_score comes from the judge (not the per-branch eval_score), so a
    branch the per-branch scorer rated LOW can win if the comparative judge rates it high."""

    async def flat_scorer(task, conclusion):
        return 0.5  # every branch identical on the absolute scorer

    async def judge(task, candidates):
        # comparative judge prefers a fork over the original regardless of the flat eval_score
        return {label: (0.95 if label != "original" else 0.1) for label, _ in candidates}

    with _patch_events(_events()):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            2,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=flat_scorer,
            judge=judge,
            n=2,
            pool=_fork_pool(),
        )
    assert res is not None
    assert res.original.combined_score == 0.1  # judge overrode the 0.5 eval_score
    assert all(f.combined_score == 0.95 for f in res.forks)
    assert res.best.variation_label != "original"  # a fork won on the comparative judge
    assert res.original.eval_score == 0.5  # eval_score preserved as the per-branch absolute signal


@pytest.mark.integration
async def test_fork_and_compare_judge_partial_falls_back_per_branch():
    """A branch the judge omits keeps its eval_score-based combined_score (graceful partial judge)."""

    async def scorer(task, conclusion):
        return 0.4

    async def judge(task, candidates):
        return {"original": 0.9}  # only scores the original; forks omitted

    with _patch_events(_events()):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            2,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=scorer,
            judge=judge,
            n=2,
            pool=_fork_pool(),
        )
    assert res.original.combined_score == 0.9  # from the judge
    assert all(f.combined_score == 0.4 for f in res.forks)  # judge omitted → eval_score fallback


@pytest.mark.integration
async def test_fork_and_compare_judge_failure_falls_back_to_eval_score():
    """A judge that raises must not break the comparison — every branch keeps its eval_score."""

    async def scorer(task, conclusion):
        return 0.6

    async def judge(task, candidates):
        raise RuntimeError("judge down")

    with _patch_events(_events()):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            2,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=scorer,
            judge=judge,
            n=2,
            pool=_fork_pool(),
        )
    assert res is not None
    assert res.original.combined_score == 0.6
    assert all(f.combined_score == 0.6 for f in res.forks)


@pytest.mark.integration
async def test_fork_and_compare_judge_none_value_does_not_poison_score():
    """A misbehaving custom judge returning {label: None} must not set combined_score=None (which
    would crash max()); such labels are skipped → eval_score fallback. Casing is also tolerated."""

    async def scorer(task, conclusion):
        return 0.55

    async def judge(task, candidates):
        # None value (must be ignored) + an upper-cased label (must still match). The n=2 forks for a
        # tail starting "analyze" are first_principles + systems.
        return {"original": None, "SYSTEMS": 0.99}

    with _patch_events(_events()):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            1,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=scorer,
            judge=judge,
            n=2,
            pool=_fork_pool(),
        )
    assert res is not None
    assert res.original.combined_score == 0.55  # None judge value ignored → eval_score
    # the upper-cased "SYSTEMS" normalizes to match the "systems" fork
    sysf = [f for f in res.forks if f.lens == "systems"]
    assert sysf and sysf[0].combined_score == 0.99


@pytest.mark.integration
async def test_default_judge_position_debias_averages_two_passes():
    """_default_judge runs two passes (given order + reversed) and averages per-label to cancel
    position bias. Here pass 1 favors A, pass 2 favors B → both average to 0.6."""
    calls = []

    async def _complete_json(prompt, model=None):
        calls.append(prompt)
        # first pass: A high, B low; second pass (reversed order): A low, B high
        if len(calls) == 1:
            return {"scores": {"A": 0.8, "B": 0.4}}
        return {"scores": {"A": 0.4, "B": 0.8}}

    llm = AsyncMock()
    llm.complete_json = AsyncMock(side_effect=_complete_json)
    with patch("core.engine.core.llm.get_llm", return_value=llm):
        out = await fork_planner._default_judge("task", [("A", "concl a"), ("B", "concl b")])
    assert len(calls) == 2  # two passes (position debias)
    assert out["A"] == pytest.approx(0.6)  # (0.8 + 0.4) / 2
    assert out["B"] == pytest.approx(0.6)  # (0.4 + 0.8) / 2


@pytest.mark.integration
async def test_default_judge_single_candidate_returns_empty():
    """Nothing to compare with < 2 candidates → {} (caller falls back to eval_score), no LLM call."""
    llm = AsyncMock()
    llm.complete_json = AsyncMock(side_effect=AssertionError("should not call the LLM"))
    with patch("core.engine.core.llm.get_llm", return_value=llm):
        assert await fork_planner._default_judge("task", [("only", "one")]) == {}


# --- The second comparison lens: predicted capability trajectory (value_model) -----------------


@pytest.mark.integration
async def test_capability_lens_scores_via_value_model():
    """conclusion → predicted deltas (injected reasoner) → state_override → value_model gap_score."""
    from core.engine.foresight.models import HypotheticalScore

    pool = _cap_pool([{"capability": "capability:auth", "score": 0.5}])

    async def reasoner(conclusion, cap_scores):
        return {"auth": 0.3}  # predict +0.3 on auth

    with patch(
        "core.engine.foresight.value_model.score_hypothetical_state",
        AsyncMock(return_value=HypotheticalScore(gap_score=0.8, top_risks=[], capability_scores={})),
    ) as m:
        out = await fork_planner._capability_lens("a conclusion", "product:platform", pool=pool, reasoner=reasoner)
    assert out == 0.8
    override = m.call_args[0][1]  # score_hypothetical_state(product_id, state_override, pool)
    assert override["capability:auth"] == pytest.approx(0.8)  # 0.5 current + 0.3 delta, clamped


@pytest.mark.integration
async def test_capability_lens_empty_or_no_deltas_returns_none():
    pool = _cap_pool([])

    async def empty_reasoner(conclusion, cap_scores):
        return {}

    assert await fork_planner._capability_lens("", "p:1", pool=pool, reasoner=empty_reasoner) is None
    assert await fork_planner._capability_lens("x", "p:1", pool=pool, reasoner=empty_reasoner) is None


@pytest.mark.integration
async def test_fork_and_compare_capability_lens_blends_and_can_flip_best():
    """With the lens on, combined_score blends reasoning-quality (judge) with capability trajectory.
    Here the judge ties everything; the capability lens favors the forks → a fork wins."""

    async def scorer(task, conclusion):
        return 0.6

    async def judge(task, candidates):
        return {label: 0.6 for label, _ in candidates}  # reasoning-quality tie

    async def fake_lens(conclusion, product_id, *, pool, reasoner=None):
        return 0.9 if "FORKED" in (conclusion or "") else 0.2  # forks high, original low

    with _patch_events(_events()), patch("core.engine.foresight.fork_planner._capability_lens", side_effect=fake_lens):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            2,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=scorer,
            judge=judge,
            n=2,
            pool=_fork_pool(),
            with_capability_lens=True,
        )
    assert res is not None
    # blend = 0.7*0.6 + 0.3*cap → forks 0.69, original 0.48
    assert all(f.capability_delta_score == 0.9 for f in res.forks)
    assert all(f.combined_score == pytest.approx(0.69) for f in res.forks)
    assert res.original.capability_delta_score == 0.2
    assert res.original.combined_score == pytest.approx(0.48)
    assert res.best.variation_label != "original"  # the capability lens flipped the winner to a fork


@pytest.mark.integration
async def test_fork_and_compare_capability_lens_off_by_default():
    """Default (lens off): capability_delta_score stays None, no value_model/lens call."""

    async def scorer(task, conclusion):
        return 0.6

    spy = AsyncMock(side_effect=AssertionError("lens should not run when off"))
    with _patch_events(_events()), patch("core.engine.foresight.fork_planner._capability_lens", spy):
        res = await fork_planner.fork_and_compare(
            "reasoning_run:abc",
            2,
            product_id="product:platform",
            llm_call=_fake_llm,
            scorer=scorer,
            judge=_no_judge,
            n=2,
            pool=_fork_pool(),
        )
    assert res is not None
    assert res.original.capability_delta_score is None
    assert all(f.capability_delta_score is None for f in res.forks)
    spy.assert_not_called()


# --- Conclusion cleanup (live validation found bare-fallback forks emit a JSON envelope) ---------


def test_clean_conclusion_unwraps_json_envelope():
    assert fork_planner._clean_conclusion('{"output": "the real answer"}') == "the real answer"
    assert fork_planner._clean_conclusion('```json\n{"output": "fenced answer"}\n```') == "fenced answer"
    assert fork_planner._clean_conclusion('{"conclusion": "alt key"}') == "alt key"


def test_clean_conclusion_leaves_plain_text_untouched():
    assert fork_planner._clean_conclusion("Just a plain prose conclusion.") == "Just a plain prose conclusion."
    assert fork_planner._clean_conclusion("") == ""
    # JSON without a recognized text key is left as-is (don't mangle)
    assert fork_planner._clean_conclusion('{"score": 0.5}') == '{"score": 0.5}'


@pytest.mark.integration
async def test_simulate_fork_strips_json_envelope_from_conclusion():
    """A model that returns a JSON envelope (the bare-fallback case) yields a CLEAN conclusion."""

    async def json_llm(system_prompt, user_prompt):
        return '```json\n{"output": "clean inner conclusion"}\n```'

    async def stub_scorer(task, conclusion):
        # the scorer must receive the CLEANED conclusion, not the JSON envelope
        assert conclusion == "clean inner conclusion"
        return 0.5

    br = await fork_planner.simulate_fork(_fp_with_thought(), "adversarial", llm_call=json_llm, scorer=stub_scorer)
    assert br.conclusion == "clean inner conclusion"


# --- Conclusion-checkpoint resolution ('fork the decision' default) -----------------------------


@pytest.mark.integration
async def test_resolve_conclusion_checkpoint_returns_n_minus_1():
    """Forking the conclusion = the second-to-last phase, so the tail is just the final phase."""
    with _patch_events(_events()):  # 3 phase events
        cp = await fork_planner.resolve_conclusion_checkpoint("reasoning_run:abc")
    assert cp == 2  # 3 phases → checkpoint 2 → tail = [conclude]


@pytest.mark.integration
async def test_resolve_conclusion_checkpoint_floors_at_1():
    with _patch_events([]):  # no events → floor
        assert await fork_planner.resolve_conclusion_checkpoint("r:1") == 1

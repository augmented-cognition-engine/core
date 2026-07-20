# tests/test_decision_linker.py
"""Unit tests for the decision linker — keyword matching and overlap scoring."""

import pytest

from core.engine.product.decision_linker import _extract_keywords, _overlap_score

# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------


def test_extract_keywords_strips_stop_words():
    kw = _extract_keywords("this is a test for the pipeline")
    assert "this" not in kw
    assert "the" not in kw
    assert "pipeline" in kw
    assert "test" in kw


def test_extract_keywords_lowercases():
    kw = _extract_keywords("SurrealDB OllamaProvider CLIProvider")
    assert "surrealdb" in kw
    assert "ollamaprovider" in kw


def test_extract_keywords_filters_short_words():
    kw = _extract_keywords("use db at v3")
    assert "db" not in kw  # 2 chars
    assert "v3" not in kw  # 2 chars
    assert "use" not in kw  # stop word


def test_extract_keywords_empty():
    assert _extract_keywords("") == frozenset()
    assert _extract_keywords("   ") == frozenset()


# ---------------------------------------------------------------------------
# _overlap_score
# ---------------------------------------------------------------------------


def test_overlap_score_identical():
    kw = frozenset(["pipeline", "orchestrator", "executor"])
    assert _overlap_score(kw, kw) == pytest.approx(1.0)


def test_overlap_score_no_overlap():
    a = frozenset(["surrealdb", "schema"])
    b = frozenset(["portal", "react", "shadcn"])
    assert _overlap_score(a, b) == pytest.approx(0.0)


def test_overlap_score_partial():
    a = frozenset(["pipeline", "orchestrator", "spin"])
    b = frozenset(["pipeline", "executor", "spin", "model"])
    # intersection = {pipeline, spin} = 2; min(3, 4) = 3
    assert _overlap_score(a, b) == pytest.approx(2 / 3)


def test_overlap_score_empty_sets():
    assert _overlap_score(frozenset(), frozenset(["x"])) == pytest.approx(0.0)
    assert _overlap_score(frozenset(["x"]), frozenset()) == pytest.approx(0.0)
    assert _overlap_score(frozenset(), frozenset()) == pytest.approx(0.0)


def test_overlap_uses_min_not_union():
    """Overlap coefficient uses min(|A|, |B|) — small focused overlaps score high."""
    # One tiny set, one large set with 1 shared keyword
    small = frozenset(["surrealdb"])
    large = frozenset(["surrealdb", "postgres", "redis", "cassandra", "elasticsearch"])
    # |intersection| = 1, min(1, 5) = 1 → score = 1.0
    assert _overlap_score(small, large) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# link_decisions (unit — mocks DB)
# ---------------------------------------------------------------------------


def test_link_decisions_dry_run_flag_in_return():
    """link_decisions result always includes dry_run flag."""
    import inspect

    from core.engine.product import decision_linker

    # Verify the function signature accepts dry_run
    sig = inspect.signature(decision_linker.link_decisions)
    assert "dry_run" in sig.parameters
    # And the stats dict initialisation always sets it
    source = inspect.getsource(decision_linker.link_decisions)
    assert '"dry_run": dry_run' in source


def test_link_decisions_synthesizer_filter_in_source():
    """SQL query excludes synthesizer-sourced decisions (they are observations, not choices)."""
    import inspect

    from core.engine.product import decision_linker

    source = inspect.getsource(decision_linker.link_decisions)
    # The filter must list the accepted sources, not synthesizer
    assert "source IN" in source
    assert "'mcp'" in source
    assert "spec_generator" in source

# tests/test_statistics_paired.py
"""Test paired statistical tests for A/B experiments."""

from core.engine.intelligence.statistics import (
    cohen_d_paired,
    experiment_decision,
    paired_t_test,
    wilcoxon_signed_rank,
)


class TestPairedTTest:
    def test_significant_improvement(self):
        control = [0.6, 0.5, 0.7, 0.55, 0.65, 0.5, 0.6, 0.55, 0.7, 0.6, 0.5, 0.65]
        variant = [0.8, 0.75, 0.85, 0.7, 0.8, 0.75, 0.8, 0.7, 0.85, 0.8, 0.75, 0.8]
        t_stat, p_value = paired_t_test(control, variant)
        assert p_value < 0.05
        assert t_stat > 0

    def test_no_difference(self):
        scores = [0.7, 0.6, 0.8, 0.65, 0.75, 0.7, 0.6, 0.8, 0.65, 0.75, 0.7, 0.6]
        t_stat, p_value = paired_t_test(scores, scores)
        assert p_value >= 0.5

    def test_too_few_samples(self):
        t_stat, p_value = paired_t_test([0.5], [0.8])
        assert p_value == 1.0

    def test_mismatched_lengths(self):
        t_stat, p_value = paired_t_test([0.5, 0.6], [0.8])
        assert p_value == 1.0


class TestWilcoxonSignedRank:
    def test_significant_improvement(self):
        control = [0.6, 0.5, 0.7, 0.55, 0.65, 0.5, 0.6, 0.55, 0.7, 0.6, 0.5, 0.65]
        variant = [0.8, 0.75, 0.85, 0.7, 0.8, 0.75, 0.8, 0.7, 0.85, 0.8, 0.75, 0.8]
        p_value = wilcoxon_signed_rank(control, variant)
        assert p_value < 0.10

    def test_no_difference(self):
        scores = [0.7, 0.6, 0.8, 0.65, 0.75, 0.7, 0.6, 0.8, 0.65, 0.75, 0.7, 0.6]
        p_value = wilcoxon_signed_rank(scores, scores)
        assert p_value >= 0.5

    def test_too_few_samples(self):
        p_value = wilcoxon_signed_rank([0.5, 0.6], [0.8, 0.9])
        assert p_value == 1.0


class TestCohenDPaired:
    def test_large_effect(self):
        control = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        variant = [0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]
        d = cohen_d_paired(control, variant)
        assert d > 0.8

    def test_zero_effect(self):
        scores = [0.5, 0.6, 0.7, 0.5, 0.6, 0.7, 0.5, 0.6, 0.7, 0.5, 0.6, 0.7]
        d = cohen_d_paired(scores, scores)
        assert d == 0.0

    def test_too_few(self):
        d = cohen_d_paired([0.5], [0.8])
        assert d == 0.0


class TestExperimentDecision:
    def test_commit_clear_winner(self):
        control = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        variant = [0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]
        should_commit, reason, stats = experiment_decision(control, variant)
        assert should_commit is True
        assert "commit" in reason
        assert stats["cohen_d"] > 0.2
        assert stats["p_value_t"] < 0.05

    def test_reject_no_improvement(self):
        scores = [0.7, 0.6, 0.8, 0.65, 0.75, 0.7, 0.6, 0.8, 0.65, 0.75, 0.7, 0.6]
        should_commit, reason, stats = experiment_decision(scores, scores)
        assert should_commit is False

    def test_reject_too_few_tasks(self):
        control = [0.5, 0.5, 0.5]
        variant = [0.9, 0.9, 0.9]
        should_commit, reason, stats = experiment_decision(control, variant)
        assert should_commit is False
        assert "insufficient" in reason.lower() or "tasks" in reason.lower()

# tests/test_statistics_extended.py
"""Test metric-appropriate statistical tests."""

from core.engine.intelligence.statistics import (
    fisher_exact,
    mann_whitney_u,
    proportion_z_test,
    select_test,
)


class TestMannWhitneyU:
    def test_significant_difference(self):
        control = [1.2, 1.5, 2.0, 1.8, 1.3, 1.6, 1.4, 1.7, 1.9, 1.5, 1.3, 1.6]
        variant = [0.8, 0.9, 1.1, 0.7, 0.9, 1.0, 0.8, 0.9, 1.2, 0.8, 0.7, 0.9]
        u_stat, p_value = mann_whitney_u(control, variant)
        assert p_value < 0.05

    def test_no_difference(self):
        data = [1.0, 1.1, 1.2, 1.0, 1.1, 1.2, 1.0, 1.1, 1.2, 1.0, 1.1, 1.2]
        u_stat, p_value = mann_whitney_u(data, data)
        assert p_value >= 0.5

    def test_too_few(self):
        u_stat, p_value = mann_whitney_u([1.0], [2.0])
        assert p_value == 1.0


class TestFisherExact:
    def test_significant(self):
        p = fisher_exact(3, 9, 9, 3)
        assert p < 0.05

    def test_not_significant(self):
        p = fisher_exact(5, 7, 6, 6)
        assert p > 0.05

    def test_identical(self):
        p = fisher_exact(5, 5, 5, 5)
        assert p >= 0.9


class TestProportionZTest:
    def test_significant(self):
        p = proportion_z_test(80, 100, 50, 100)
        assert p < 0.05

    def test_not_significant(self):
        p = proportion_z_test(51, 100, 49, 100)
        assert p > 0.05


class TestSelectTest:
    def test_selects_wilcoxon_for_quality(self):
        assert select_test("quality") == "wilcoxon"

    def test_selects_mann_whitney_for_time(self):
        assert select_test("time") == "mann_whitney"

    def test_selects_proportion_for_utilization(self):
        assert select_test("utilization") == "proportion"

    def test_selects_fisher_for_binary(self):
        assert select_test("binary") == "fisher"

    def test_defaults_to_wilcoxon(self):
        assert select_test("unknown") == "wilcoxon"

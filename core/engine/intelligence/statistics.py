"""Statistical tests for experiment evaluation.

Welch's t-test implementation using only stdlib math.
No scipy dependency.
"""

from __future__ import annotations

import math


def _mean(data: list[float]) -> float:
    if not data:
        return 0.0
    return sum(data) / len(data)


def _variance(data: list[float]) -> float:
    if len(data) < 2:
        return 0.0
    m = _mean(data)
    return sum((x - m) ** 2 for x in data) / (len(data) - 1)


def _t_cdf_approx(t_val: float, df: float) -> float:
    """Approximate the CDF of the t-distribution using a normal approximation.

    For df >= 30, the t-distribution is close to normal. For smaller df,
    this uses Abramowitz & Stegun's approximation of the normal CDF.
    """
    if df <= 0:
        return 0.5
    # Adjusted t for degrees of freedom (Cornish-Fisher expansion)
    x = t_val * (1 - 1 / (4 * df)) if df > 1 else t_val
    # Normal CDF approximation (Abramowitz & Stegun 26.2.17)
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x_abs = abs(x) / math.sqrt(2)
    t_val_local = 1.0 / (1.0 + p * x_abs)
    y = 1.0 - (
        ((((a5 * t_val_local + a4) * t_val_local) + a3) * t_val_local + a2) * t_val_local + a1
    ) * t_val_local * math.exp(-x_abs * x_abs)
    return 0.5 * (1.0 + sign * y)


def welch_t_test(group_a: list[float], group_b: list[float]) -> tuple[float, float]:
    """Welch's t-test for two independent samples with unequal variances.

    Args:
        group_a: Control group scores.
        group_b: Variant group scores.

    Returns:
        (t_statistic, p_value) tuple. Two-tailed p-value.
        Returns (0.0, 1.0) for degenerate cases.
    """
    n_a = len(group_a)
    n_b = len(group_b)

    if n_a < 2 or n_b < 2:
        return (0.0, 1.0)

    mean_a = _mean(group_a)
    mean_b = _mean(group_b)
    var_a = _variance(group_a)
    var_b = _variance(group_b)

    # Handle zero variance
    if var_a == 0 and var_b == 0:
        if mean_a == mean_b:
            return (0.0, 1.0)
        # Identical within groups but different means — significant
        return (float("inf") if mean_b > mean_a else float("-inf"), 0.0)

    se = math.sqrt(var_a / n_a + var_b / n_b)
    if se == 0:
        return (0.0, 1.0)

    t_stat = (mean_b - mean_a) / se

    # Welch-Satterthwaite degrees of freedom
    numerator = (var_a / n_a + var_b / n_b) ** 2
    denom = ((var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)) if (n_a > 1 and n_b > 1) else 1
    df = numerator / denom if denom > 0 else 1

    # Two-tailed p-value
    cdf_val = _t_cdf_approx(abs(t_stat), df)
    p_value = 2 * (1 - cdf_val)
    p_value = max(0.0, min(1.0, p_value))

    return (round(t_stat, 4), round(p_value, 4))


def is_significant(
    group_a: list[float],
    group_b: list[float],
    threshold: float = 0.05,
    min_effect: float = 0.02,
) -> bool:
    """Check if the difference between groups is statistically significant.

    Requires BOTH p < threshold AND improvement > min_effect.
    """
    if not group_a or not group_b:
        return False

    _, p_value = welch_t_test(group_a, group_b)
    improvement = _mean(group_b) - _mean(group_a)

    return p_value < threshold and improvement > min_effect


def paired_t_test(control: list[float], variant: list[float]) -> tuple[float, float]:
    """Paired t-test for matched samples.

    Args:
        control: Control group scores (paired with variant by index).
        variant: Variant group scores.

    Returns:
        (t_statistic, p_value). Two-tailed.
        Returns (0.0, 1.0) for degenerate cases.
    """
    if len(control) != len(variant) or len(control) < 2:
        return (0.0, 1.0)

    diffs = [v - c for c, v in zip(control, variant)]
    n = len(diffs)
    mean_diff = _mean(diffs)
    var_diff = _variance(diffs)

    if var_diff == 0:
        if mean_diff == 0:
            return (0.0, 1.0)
        return (float("inf") if mean_diff > 0 else float("-inf"), 0.0)

    se = math.sqrt(var_diff / n)
    t_stat = mean_diff / se
    df = n - 1

    cdf_val = _t_cdf_approx(abs(t_stat), df)
    p_value = 2 * (1 - cdf_val)
    p_value = max(0.0, min(1.0, p_value))

    return (round(t_stat, 4), round(p_value, 4))


def wilcoxon_signed_rank(control: list[float], variant: list[float]) -> float:
    """Wilcoxon signed-rank test for paired samples (non-parametric).

    Approximates p-value using normal approximation for n >= 10.
    Returns 1.0 for insufficient data.

    Returns:
        p_value (two-tailed).
    """
    if len(control) != len(variant) or len(control) < 5:
        return 1.0

    diffs = [v - c for c, v in zip(control, variant)]
    nonzero = [(abs(d), d) for d in diffs if d != 0]
    if len(nonzero) < 5:
        return 1.0

    nonzero.sort(key=lambda x: x[0])
    n = len(nonzero)

    ranks = []
    i = 0
    while i < n:
        j = i
        while j < n and nonzero[j][0] == nonzero[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2
        for k in range(i, j):
            ranks.append(avg_rank)
        i = j

    w_plus = sum(r for r, (_, d) in zip(ranks, nonzero) if d > 0)

    mean_w = n * (n + 1) / 4
    std_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if std_w == 0:
        return 1.0

    z = (w_plus - mean_w) / std_w
    cdf_val = _t_cdf_approx(abs(z), 1000)
    p_value = 2 * (1 - cdf_val)
    return round(max(0.0, min(1.0, p_value)), 4)


def cohen_d_paired(control: list[float], variant: list[float]) -> float:
    """Cohen's d for paired samples (effect size).

    Uses the standard deviation of differences as the denominator.

    Returns:
        Effect size (positive = variant better). 0.0 for degenerate cases.
    """
    if len(control) != len(variant) or len(control) < 2:
        return 0.0

    diffs = [v - c for c, v in zip(control, variant)]
    mean_diff = _mean(diffs)
    sd_diff = math.sqrt(_variance(diffs))

    if sd_diff == 0:
        if mean_diff == 0:
            return 0.0
        # Constant nonzero differences — very large effect
        return 1e9 if mean_diff > 0 else -1e9

    return round(mean_diff / sd_diff, 4)


def experiment_decision(
    control: list[float],
    variant: list[float],
) -> tuple[bool, str, dict]:
    """Full experiment commit decision using protected constants.

    Returns:
        (should_commit, reason, stats_dict)
    """
    min_tasks = 12
    min_effect = 0.02
    min_cohen = 0.2
    sig_threshold = 0.05

    stats = {
        "control_mean": _mean(control),
        "variant_mean": _mean(variant),
        "improvement": _mean(variant) - _mean(control),
        "task_count": min(len(control), len(variant)),
        "p_value_t": 1.0,
        "p_value_w": 1.0,
        "cohen_d": 0.0,
    }

    n = stats["task_count"]
    if n < min_tasks:
        return False, f"insufficient_stable_tasks (n={n}, need {min_tasks})", stats

    _, p_t = paired_t_test(control, variant)
    p_w = wilcoxon_signed_rank(control, variant)
    d = cohen_d_paired(control, variant)

    stats["p_value_t"] = p_t
    stats["p_value_w"] = p_w
    stats["cohen_d"] = d

    if p_t >= sig_threshold:
        return False, f"not_significant_t (p={p_t:.3f})", stats

    if p_w >= 0.10:
        return False, f"not_significant_wilcoxon (p={p_w:.3f})", stats

    if d < min_cohen:
        return False, f"effect_too_small (d={d:.2f})", stats

    if stats["improvement"] < min_effect:
        return False, f"practical_significance_too_low ({stats['improvement']:.3f})", stats

    return True, f"commit (d={d:.2f}, p={p_t:.3f}, improvement={stats['improvement']:.3f})", stats


def mann_whitney_u(group_a: list[float], group_b: list[float]) -> tuple[float, float]:
    """Mann-Whitney U test for independent samples (non-parametric).
    Better than t-test for time/cost data with heavy tails.
    Returns (u_statistic, p_value). Uses normal approximation.
    """
    if len(group_a) < 2 or len(group_b) < 2:
        return (0.0, 1.0)
    n1, n2 = len(group_a), len(group_b)
    combined = [(v, "a") for v in group_a] + [(v, "b") for v in group_b]
    combined.sort(key=lambda x: x[0])
    ranks = []
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2
        for k in range(i, j):
            ranks.append((avg_rank, combined[k][1]))
        i = j
    r1 = sum(r for r, g in ranks if g == "a")
    u1 = r1 - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    mu = n1 * n2 / 2
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    if sigma == 0:
        return (u, 1.0)
    z = (u - mu) / sigma
    p_value = 2 * (1 - _t_cdf_approx(abs(z), 1000))
    return (round(u, 4), round(max(0.0, min(1.0, p_value)), 4))


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Fisher's exact test for 2x2 contingency table [[a,b],[c,d]].
    Returns two-tailed p-value.
    """
    n = a + b + c + d
    if n == 0:
        return 1.0

    def _log_factorial(k):
        return sum(math.log(i) for i in range(1, k + 1)) if k > 0 else 0.0

    def _hypergeom_prob(a0, b0, c0, d0):
        n0 = a0 + b0 + c0 + d0
        log_p = (
            _log_factorial(a0 + b0)
            + _log_factorial(c0 + d0)
            + _log_factorial(a0 + c0)
            + _log_factorial(b0 + d0)
            - _log_factorial(n0)
            - _log_factorial(a0)
            - _log_factorial(b0)
            - _log_factorial(c0)
            - _log_factorial(d0)
        )
        return math.exp(log_p)

    p_observed = _hypergeom_prob(a, b, c, d)
    row1, col1 = a + b, a + c
    p_total = 0.0
    for a_i in range(min(row1, col1) + 1):
        b_i, c_i = row1 - a_i, col1 - a_i
        d_i = n - a_i - b_i - c_i
        if b_i < 0 or c_i < 0 or d_i < 0:
            continue
        p_i = _hypergeom_prob(a_i, b_i, c_i, d_i)
        if p_i <= p_observed + 1e-10:
            p_total += p_i
    return round(max(0.0, min(1.0, p_total)), 4)


def proportion_z_test(successes_a: int, total_a: int, successes_b: int, total_b: int) -> float:
    """Two-proportion z-test. Returns two-tailed p-value."""
    if total_a == 0 or total_b == 0:
        return 1.0
    p1, p2 = successes_a / total_a, successes_b / total_b
    p_pool = (successes_a + successes_b) / (total_a + total_b)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / total_a + 1 / total_b))
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    p_value = 2 * (1 - _t_cdf_approx(abs(z), 1000))
    return round(max(0.0, min(1.0, p_value)), 4)


def select_test(metric_type: str) -> str:
    """Select appropriate statistical test for a metric type."""
    return {
        "quality": "wilcoxon",
        "time": "mann_whitney",
        "cost": "mann_whitney",
        "tokens": "mann_whitney",
        "utilization": "proportion",
        "binary": "fisher",
        "proportion": "proportion",
    }.get(metric_type, "wilcoxon")

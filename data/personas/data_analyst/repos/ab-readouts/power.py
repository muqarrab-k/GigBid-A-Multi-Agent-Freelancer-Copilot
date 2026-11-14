from __future__ import annotations

from math import ceil
from typing import Optional

import statsmodels.stats.power as smp


def required_sample_size(
    effect_size: float,
    alpha: float = 0.05,
    power: float = 0.8,
    ratio: float = 1.0,
    alternative: str = "two-sided",
) -> int:
    """
    Return the per-group sample size needed for a two-sample power check.
    """
    analysis = smp.TTestIndPower()
    n = analysis.solve_power(
        effect_size=effect_size,
        alpha=alpha,
        power=power,
        ratio=ratio,
        alternative=alternative,
    )
    return int(ceil(n))


def minimum_detectable_effect(
    n_per_group: int,
    alpha: float = 0.05,
    power: float = 0.8,
    ratio: float = 1.0,
    alternative: str = "two-sided",
) -> float:
    """
    Return the smallest standardized effect size detectable at target power.
    """
    analysis = smp.TTestIndPower()
    return float(
        analysis.solve_power(
            nobs1=n_per_group,
            alpha=alpha,
            power=power,
            ratio=ratio,
            alternative=alternative,
        )
    )


def check_power_plan(
    baseline_rate: float,
    mde_absolute: float,
    sample_size: int,
    alpha: float = 0.05,
    power: float = 0.8,
) -> dict:
    """
    Convenience helper for readouts that use a rate metric.
    """
    if baseline_rate <= 0:
        raise ValueError("baseline_rate must be positive")
    if sample_size <= 1:
        raise ValueError("sample_size must be greater than 1")

    effect_size = mde_absolute / baseline_rate
    needed = required_sample_size(effect_size=effect_size, alpha=alpha, power=power)
    detectable = minimum_detectable_effect(sample_size, alpha=alpha, power=power)

    return {
        "effect_size": effect_size,
        "required_n_per_group": needed,
        "minimum_detectable_effect": detectable,
        "is_powered": sample_size >= needed,
    }

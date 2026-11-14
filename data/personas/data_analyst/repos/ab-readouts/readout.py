import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest


@dataclass
class ReadoutResult:
    control_rate: float
    treatment_rate: float
    lift: float
    lift_ci_low: float
    lift_ci_high: float
    p_value: float


def _safe_rate(successes: int, nobs: int) -> float:
    if nobs <= 0:
        return float("nan")
    return successes / nobs


def compute_conversion_readout(
    control_successes: int,
    control_nobs: int,
    treatment_successes: int,
    treatment_nobs: int,
    alpha: float = 0.05,
) -> ReadoutResult:
    # Point estimates
    control_rate = _safe_rate(control_successes, control_nobs)
    treatment_rate = _safe_rate(treatment_successes, treatment_nobs)

    if not np.isfinite(control_rate) or control_rate <= 0:
        lift = float("nan")
        lift_ci_low = float("nan")
        lift_ci_high = float("nan")
    else:
        lift = (treatment_rate / control_rate) - 1.0

        # CI on absolute difference, then scale to relative lift
        diff_low, diff_high = confint_proportions_2indep(
            count1=treatment_successes,
            nobs1=treatment_nobs,
            count2=control_successes,
            nobs2=control_nobs,
            compare="diff",
            alpha=alpha,
        )
        lift_ci_low = diff_low / control_rate
        lift_ci_high = diff_high / control_rate

    # Two-sided z-test for conversion rates
    counts = np.array([treatment_successes, control_successes])
    nobs = np.array([treatment_nobs, control_nobs])
    stat, p_value = proportions_ztest(counts, nobs, alternative="two-sided")

    return ReadoutResult(
        control_rate=control_rate,
        treatment_rate=treatment_rate,
        lift=lift,
        lift_ci_low=lift_ci_low,
        lift_ci_high=lift_ci_high,
        p_value=p_value,
    )


def readout_frame(result: ReadoutResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "control_rate": result.control_rate,
                "treatment_rate": result.treatment_rate,
                "lift": result.lift,
                "lift_ci_low": result.lift_ci_low,
                "lift_ci_high": result.lift_ci_high,
                "p_value": result.p_value,
            }
        ]
    )

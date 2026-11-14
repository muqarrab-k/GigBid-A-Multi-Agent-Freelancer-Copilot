# A/B test readouts

Utilities for sample size checks and post-test readouts for in-app store tests.

## Setup

Python 3 environment with `SQL`, `Python`, and `statsmodels` available.

Install dependencies used by the helper scripts:

```bash
pip install statsmodels
```

## Usage

`power.py` is for pre-launch sizing checks and minimum detectable effect calculations.

`readout.py` computes conversion lift and confidence intervals for a single test readout.

```python
from power import sample_size, mde
from readout import conversion_lift

# pre-launch sizing
n = sample_size(baseline_rate=0.12, lift=0.05, alpha=0.05, power=0.8)

# readout
result = conversion_lift(
    control_conversions=120,
    control_users=1000,
    treatment_conversions=138,
    treatment_users=1000,
)

print(n)
print(result)
```

## Notes

Built as a repeatable template for in-app store test reporting with power checks before launch.

Used across a small set of readouts, with a couple of underpowered tests stopped early.

The repo is limited to the helper pieces here: sizing in `power.py` and lift readouts in `readout.py`.

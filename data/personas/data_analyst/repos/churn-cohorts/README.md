# Subscription churn cohorts

Monthly retention curves by signup cohort and plan, plus an onboarding-step funnel.

## Setup

- PostgreSQL for the SQL query in `cohorts.sql`
- Python with `pandas` for `cohort_plot.py`
- Optional: Looker Studio for downstream reporting

## Usage

Run the Postgres query to produce monthly retention by signup cohort and plan, then feed the output into the Python script for pivoting and heatmap generation.

```bash
psql -f cohorts.sql
python cohort_plot.py
```

`cohorts.sql` builds the retention dataset. `cohort_plot.py` reshapes the result with `pandas` and plots a retention heatmap.

## Notes

- The repo covers a subscription churn workflow for a SaaS product.
- The onboarding funnel is included alongside the retention view.
- One onboarding step lines up with a large share of first-month churn.
- The work was delivered on an hourly engagement between 2022-01 and 2022-03.

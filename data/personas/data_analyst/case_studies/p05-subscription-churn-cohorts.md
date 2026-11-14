# Subscription churn cohorts

I worked with a client in SaaS (name withheld) on an hourly engagement from 2022-01 to 2022-03 to help them understand where subscribers were dropping off and how retention varied across signup groups. The main challenge was to turn raw product and subscription data into something the team could use to spot churn patterns early, especially across different plans and the first steps of onboarding.

My approach started in PostgreSQL, where I pulled together subscription, signup, and onboarding event tables into analysis-ready datasets. I used SQL to define each user’s signup month, plan, and follow-up activity, then shaped the output in Python with pandas so I could calculate month-over-month retention by signup group. That allowed me to build monthly retention curves that made it easy to compare behavior across plans and see how new users progressed after joining.

I also built a funnel view of onboarding steps to identify where users were getting stuck. For this, I organized event sequences, counted completion rates at each step, and aligned those results with first-month retention. The combination of retention curves and onboarding flow made it possible to connect product behavior with subscription outcomes rather than looking at them separately.

A simplified version of the retention logic looked like this:

```python
import pandas as pd

df["signup_month"] = pd.to_datetime(df["signup_date"]).dt.to_period("M")
df["activity_month"] = pd.to_datetime(df["activity_date"]).dt.to_period("M")
df["months_since_signup"] = (df["activity_month"] - df["signup_month"]).apply(lambda x: x.n)
retention = (
    df.groupby(["signup_month", "plan", "months_since_signup"])["user_id"]
      .nunique()
      .reset_index(name="active_users")
)
```

After the modeling work, I published the outputs in Looker Studio so the client could explore retention by plan and signup month without having to query the source data directly. The dashboards combined the retention curves with the onboarding funnel, giving the team a practical reporting layer for recurring review.

One of the clearest findings was that a single onboarding step was associated with 40% of first-month churn. That gave the client a concrete place to focus product and lifecycle improvements, and it turned the reporting into something actionable rather than just descriptive.

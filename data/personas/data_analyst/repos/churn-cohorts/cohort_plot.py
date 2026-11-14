import pandas as pd


def build_cohort_matrix(events: pd.DataFrame) -> pd.DataFrame:
    """
    Build a monthly retention matrix from cohort activity rows.
    Expected columns: signup_month, activity_month, users
    """
    if events.empty:
        return pd.DataFrame()

    df = events.copy()
    df["signup_month"] = pd.to_datetime(df["signup_month"]).dt.to_period("M").dt.to_timestamp()
    df["activity_month"] = pd.to_datetime(df["activity_month"]).dt.to_period("M").dt.to_timestamp()

    df["month_offset"] = (
        (df["activity_month"].dt.year - df["signup_month"].dt.year) * 12
        + (df["activity_month"].dt.month - df["signup_month"].dt.month)
    )

    pivot = (
        df.pivot_table(
            index=["signup_month"],
            columns="month_offset",
            values="users",
            aggfunc="sum",
            fill_value=0,
        )
        .sort_index()
        .sort_index(axis=1)
    )

    if 0 in pivot.columns:
        base = pivot[0].replace(0, pd.NA)
        pivot = pivot.div(base, axis=0).fillna(0)

    pivot.index.name = "cohort_month"
    pivot.columns = [f"m{int(c)}" for c in pivot.columns]
    return pivot.reset_index()


def build_plan_retention(events: pd.DataFrame) -> pd.DataFrame:
    # Plan-level retention table for Looker Studio
    required = {"cohort_month", "plan", "month_offset", "users"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    df = events.copy()
    df["cohort_month"] = pd.to_datetime(df["cohort_month"]).dt.to_period("M").dt.to_timestamp()

    pivot = df.pivot_table(
        index=["cohort_month", "plan"],
        columns="month_offset",
        values="users",
        aggfunc="sum",
        fill_value=0,
    ).sort_index()

    return pivot.reset_index()


def build_onboarding_funnel(step_counts: pd.DataFrame) -> pd.DataFrame:
    # Simple step funnel for onboarding
    if step_counts.empty:
        return pd.DataFrame(columns=["step", "users", "conversion"])

    df = step_counts.copy()
    df = df.sort_values("step_order").reset_index(drop=True)
    df["users"] = df["users"].astype(float)

    first = df.loc[0, "users"] if len(df) else 0
    df["conversion"] = df["users"].div(first).fillna(0) if first else 0
    return df[["step", "users", "conversion"]]

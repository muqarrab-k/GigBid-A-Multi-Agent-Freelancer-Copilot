from __future__ import annotations

import pandas as pd


def add_calendar_features(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col])

    iso = out[date_col].dt.isocalendar()
    out["weekofyear"] = iso.week.astype(int)
    out["month"] = out[date_col].dt.month.astype(int)
    out["year"] = out[date_col].dt.year.astype(int)
    out["quarter"] = out[date_col].dt.quarter.astype(int)
    out["is_month_start"] = out[date_col].dt.is_month_start.astype(int)
    out["is_month_end"] = out[date_col].dt.is_month_end.astype(int)
    return out


def add_lag_features(
    df: pd.DataFrame,
    group_cols: list[str],
    target_col: str = "sales",
    lags: tuple[int, ...] = (1, 2, 4, 8, 13, 26, 52),
) -> pd.DataFrame:
    out = df.sort_values(group_cols + ["date"]).copy()
    for lag in lags:
        out[f"{target_col}_lag_{lag}"] = out.groupby(group_cols)[target_col].shift(lag)
    return out


def add_rolling_features(
    df: pd.DataFrame,
    group_cols: list[str],
    target_col: str = "sales",
    windows: tuple[int, ...] = (4, 8, 13, 26),
) -> pd.DataFrame:
    out = df.sort_values(group_cols + ["date"]).copy()
    g = out.groupby(group_cols)[target_col]
    for window in windows:
        out[f"{target_col}_roll_mean_{window}"] = (
            g.shift(1).rolling(window=window, min_periods=1).mean().reset_index(level=group_cols, drop=True)
        )
        out[f"{target_col}_roll_std_{window}"] = (
            g.shift(1).rolling(window=window, min_periods=2).std().reset_index(level=group_cols, drop=True)
        )
    return out


def add_holiday_features(
    df: pd.DataFrame,
    date_col: str = "date",
    holiday_dates: pd.DataFrame | None = None,
) -> pd.DataFrame:
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    out["is_holiday"] = 0
    out["days_to_holiday"] = -1
    out["days_since_holiday"] = -1

    if holiday_dates is None or holiday_dates.empty:
        return out

    holidays = pd.to_datetime(holiday_dates[date_col]).drop_duplicates().sort_values()
    holiday_set = set(holidays.dt.normalize())

    dates = out[date_col].dt.normalize()
    out["is_holiday"] = dates.isin(holiday_set).astype(int)

    next_holiday = pd.Series(index=holidays.index, data=holidays.values)
    out["days_to_holiday"] = dates.apply(lambda d: (holidays[holidays >= d].min() - d).days if (holidays >= d).any() else -1)
    out["days_since_holiday"] = dates.apply(lambda d: (d - holidays[holidays <= d].max()).days if (holidays <= d).any() else -1)
    return out


def build_features(df: pd.DataFrame, holiday_dates: pd.DataFrame | None = None) -> pd.DataFrame:
    out = add_calendar_features(df)
    out = add_lag_features(out, group_cols=["store_id", "sku_id"])
    out = add_rolling_features(out, group_cols=["store_id", "sku_id"])
    out = add_holiday_features(out, holiday_dates=holiday_dates)
    return out

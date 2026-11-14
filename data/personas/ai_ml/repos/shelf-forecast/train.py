import os
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error

BQ_PROJECT = os.getenv("BQ_PROJECT", "shelf-forecast")
BQ_DATASET = os.getenv("BQ_DATASET", "forecasting")
BQ_TABLE = os.getenv("BQ_TABLE", "weekly_features")
TRAIN_END_DATE = os.getenv("TRAIN_END_DATE", "2024-06-30")
VALIDATION_WEEKS = int(os.getenv("VALIDATION_WEEKS", "8"))


def wape(y_true, y_pred):
    denom = abs(y_true).sum()
    if denom == 0:
        return 0.0
    return abs(y_true - y_pred).sum() / denom


def load_data():
    # In production this is read from BigQuery by the Airflow task.
    path = os.getenv("TRAINING_DATA_PATH", "")
    if path and os.path.exists(path):
        return pd.read_parquet(path)
    return pd.DataFrame()


def prepare_frame(df):
    df = df.copy()
    df["week"] = pd.to_datetime(df["week"])
    df = df.sort_values(["store_id", "sku_id", "week"])
    return df


def split_time_based(df):
    end_date = pd.to_datetime(TRAIN_END_DATE)
    train_mask = df["week"] <= end_date - pd.Timedelta(weeks=VALIDATION_WEEKS)
    valid_mask = (df["week"] > end_date - pd.Timedelta(weeks=VALIDATION_WEEKS)) & (df["week"] <= end_date)
    return df.loc[train_mask], df.loc[valid_mask]


def train():
    df = load_data()
    if df.empty:
        return None

    df = prepare_frame(df)
    train_df, valid_df = split_time_based(df)

    target = "sales"
    drop_cols = ["sales", "week"]
    feature_cols = [c for c in df.columns if c not in drop_cols]

    X_train, y_train = train_df[feature_cols], train_df[target]
    X_valid, y_valid = valid_df[feature_cols], valid_df[target]

    model = LGBMRegressor(
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=63,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)

    valid_pred = model.predict(X_valid)
    score = wape(y_valid.values, valid_pred)
    mae = mean_absolute_error(y_valid, valid_pred)

    print(f"validation_wape={score:.4f}")
    print(f"validation_mae={mae:.4f}")

    return model


if __name__ == "__main__":
    train()

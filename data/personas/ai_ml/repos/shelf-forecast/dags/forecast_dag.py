from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from shelf_forecast.pipeline import build_forecasts, load_data, write_forecasts_to_bigquery

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

def _train_and_forecast(**context):
    # Load weekly sales and store/SKU history
    data = load_data()
    # Train the forecast models and generate predictions
    forecasts = build_forecasts(data)
    context["ti"].xcom_push(key="forecasts", value=forecasts)

def _write_to_bq(**context):
    # Persist forecast output for downstream reporting
    forecasts = context["ti"].xcom_pull(task_ids="train_and_forecast", key="forecasts")
    write_forecasts_to_bigquery(forecasts)

with DAG(
    dag_id="weekly_store_sku_forecast",
    default_args=default_args,
    description="Weekly store-by-SKU forecasting pipeline",
    schedule="0 3 * * 1",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["forecasting", "bigquery", "lightgbm", "prophet"],
) as dag:
    train_and_forecast = PythonOperator(
        task_id="train_and_forecast",
        python_callable=_train_and_forecast,
    )

    write_to_bq = PythonOperator(
        task_id="write_to_bigquery",
        python_callable=_write_to_bq,
    )

    train_and_forecast >> write_to_bq

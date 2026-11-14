# shelf-forecast

Weekly grocery demand forecasting pipeline for store-by-SKU predictions.

## Setup

Python project using:
- Python
- LightGBM
- Prophet
- Airflow
- BigQuery

Repo files:
- `features.py` for lag, rolling mean, and holiday features per store and SKU
- `train.py` for LightGBM training with a time-based split and WAPE evaluation
- `dags/forecast_dag.py` for the weekly Airflow DAG that trains, predicts, and writes outputs to BigQuery

## Usage

```bash
python features.py
python train.py
airflow dags trigger forecast_dag
```

## Notes

- Built for a retail demand use case.
- Produces weekly forecasts for 420 SKUs across 31 stores.
- The pipeline is scheduled in Airflow and writes results back to BigQuery.
- Time-based validation is used in training.
- The model stack combines LightGBM with Prophet-based feature work in the broader forecasting workflow.
- Pilot store results showed lower forecast error and reduced spoilage write-offs.

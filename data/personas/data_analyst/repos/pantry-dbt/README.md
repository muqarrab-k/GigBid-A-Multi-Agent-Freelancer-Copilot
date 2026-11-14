Warehouse models for a DTC e-commerce brand, built in dbt on BigQuery with Fivetran and SQL.

## Setup

Install dbt and configure a BigQuery profile for this project.

Clone the repo, set your environment variables or profile values, and run:

```bash
dbt deps
dbt debug
dbt build
```

## Usage

This project is organized into staging, intermediate, and mart layers for orders, subscriptions, and marketing.

The main mart in this repo is `models/marts/fct_orders.sql`, which joins orders, refunds, and subscriptions. Column descriptions and tests for that mart live in `models/marts/schema.yml`.

Typical local workflow:

```bash
dbt run --select models/marts/fct_orders.sql
dbt test --select models/marts/schema.yml
```

Use `dbt build` when you want to run models and tests together.

## Notes

The project includes 38 models and tests across 120 columns.

It was set up to support faster dashboard updates, moving refreshes from daily to hourly.

Files in this repo cover the mart layer only; the broader project also includes staging and intermediate models.

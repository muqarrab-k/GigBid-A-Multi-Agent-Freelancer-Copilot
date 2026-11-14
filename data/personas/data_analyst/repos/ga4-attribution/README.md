# ga4-attribution

Marketing attribution analysis for GA4 session paths and channel credit comparison.

## Setup

- Requires access to Google Analytics data in BigQuery
- Uses SQL in `attribution.sql`
- Uses Python in `channel_weights.py`
- No package manifest is included; run the scripts in your own environment

## Usage

Run the BigQuery query to build user paths and assign position-based credit:

```bash
bq query --use_legacy_sql=false < attribution.sql
```

Then run the Python script to compare first-click, last-click, and position-based models:

```bash
python channel_weights.py
```

## Notes

This repository joins ad platform spend with GA4 sessions in BigQuery, then compares credit allocation across three models: first-click, last-click, and position-based.

The SQL focuses on event-level path construction from GA4 data. The Python script is a small helper for reviewing the model outputs side by side.

In the original engagement, the analysis supported a budget shift across channels and a later reduction in acquisition cost the following quarter.

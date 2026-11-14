Sales KPI dashboard built as a Power BI semantic model on SQL Server and Excel sources.

## Setup

- Load the SQL views in `model.sql` into SQL Server.
- Open the Power BI file that consumes the fact and dimension tables produced by those views.
- Import or copy the measures from `measures.dax` into the report model.
- Confirm the model follows a star schema with sales as the central fact table.

## Usage

```text
1. Create the SQL views from model.sql.
2. Refresh the Power BI model against SQL Server.
3. Add the DAX measures from measures.dax.
4. Build visuals for sales, margin, year-over-year, and rolling 12 months.
5. Publish or share the report.
```

## Notes

- The repository contains only the SQL and DAX layer for the semantic model.
- The report was built to replace a set of separate Excel sales reports with one Power BI report.
- This setup was used to shorten monthly close reporting from several days to a few hours.
- File contents are split by role: SQL for table shaping, DAX for calculations.

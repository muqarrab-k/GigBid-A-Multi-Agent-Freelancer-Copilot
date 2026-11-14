# Inventory Reconciliation Automation for Coastline Hardware

At Coastline Hardware, the weekly stock reconciliation process was slowing the team down. Warehouse counts had to be compared against the ERP by hand, and the work took hours every week. It was also difficult to spot and follow up on mismatches quickly, which meant variances could sit unnoticed.

I built a Power Query workbook that pulls together the warehouse counts and ERP data, matches them on a weekly basis, and flags anything that does not line up. I used Excel, Power Query, and SQL to shape the data and make the comparison repeatable. The goal was not just to speed up the process, but to make it easier for the team to trust the output and act on it immediately.

A simple part of the logic looked like this:

```sql
SELECT
    item_id,
    warehouse_count,
    erp_quantity,
    warehouse_count - erp_quantity AS variance
FROM inventory_recon
WHERE warehouse_count <> erp_quantity;
```

Before this, the reconciliation work was a manual routine that demanded a lot of attention each week. After the workbook was in place, Coastline Hardware’s team had a clear weekly process: load the latest counts, review the flagged variances, and investigate the exceptions. Instead of spending most of the time comparing records, they could focus on resolving the differences that mattered.

The impact was immediate. I helped surface $86k of stock variance, giving the client a much clearer view of where inventory records were not matching reality. Just as importantly, the weekly reconciliation cycle dropped from 6 hours to 20 minutes. That changed the rhythm of the work for the team: reconciliation became a quick review step rather than a time-consuming task.

The project ran from 2021-10 to 2021-12 on a fixed engagement. For Coastline Hardware, the result was a reliable weekly process that fits naturally into how the team works now—fast, repeatable, and centered on exceptions instead of manual comparison.

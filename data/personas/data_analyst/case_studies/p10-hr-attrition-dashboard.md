# HR Attrition Dashboard

In 2023, I worked with a client in manufacturing (name withheld) to improve how their HR team and plant managers tracked attrition and absence across multiple sites. The business needed a clearer way to understand where people were leaving, how absence patterns were shifting, and what each plant manager should be able to see without exposing information from other locations.

I built an attrition and absence dashboard using Power BI, Excel, and SQL. A key part of the project was making sure access was limited by plant, so each plant manager could only view the data for their own site. That meant the dashboard supported shared reporting while still keeping the views relevant and appropriately separated for day-to-day management.

The reporting model was designed around the questions the team actually needed to answer: where are we seeing the highest turnover, how does absence vary by plant, and which sites need attention first? I used SQL to shape the source data, Excel where it helped with review and validation, and Power BI to bring everything together into a dashboard that could be refreshed and used consistently by the team.

```sql
SELECT
  plant_id,
  employee_id,
  status,
  absence_days,
  exit_date
FROM hr_facts
WHERE plant_id IN (
  SELECT plant_id
  FROM manager_access
  WHERE manager_id = @ManagerId
);
```

The dashboard covered 1,900 employees and quickly helped the team identify attrition hotspots in 2 plants. Just as importantly, it changed how the client’s team works now: plant managers no longer have to wait for manual reports or request separate extracts to understand their own site. They can open the dashboard, view the information relevant to them, and use the same reporting structure across plants.

This engagement ran hourly from March 2023 to May 2023. The final result was a more practical reporting setup for HR and operations: one that supports faster review, clearer ownership at the plant level, and more focused conversations about workforce retention and absence trends.

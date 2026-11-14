# Parent survey analysis for Riverbend Education Fund

In 2021, Riverbend Education Fund needed a clearer way to understand what parents were saying about its work and where future funding should go. The raw survey data was broad, but it wasn’t yet ready for board-level decision-making. My role was to turn a large response set into a clean, defensible analysis that leadership could trust.

I worked on a fixed engagement from August to September 2021 and focused on cleaning, structuring, and analyzing a 4,200-response parent survey. Using Python, pandas, Excel, and statistical analysis, I prepared the dataset for review and then shaped the findings into a concise written report for the board. A key part of the work was adjusting the analysis so the results reflected the survey population more accurately, rather than simply mirroring the raw response mix.

The project was not just about data hygiene. It was about making the evidence usable. I organized the analysis around the questions that mattered most to Riverbend Education Fund: what parents valued, where the biggest concerns were, and what themes should influence the next funding plan. I then translated the results into plain language so board members could quickly understand the implications and act on them.

A small example of the kind of analysis prep I used:

```python
import pandas as pd

df = pd.read_excel("parent_survey.xlsx")
df = df.drop_duplicates(subset=["response_id"])
df["adjusted_score"] = df["raw_score"] * df["response_factor"]
summary = (
    df.groupby("topic")
      .agg(mean_score=("adjusted_score", "mean"),
           responses=("response_id", "count"))
      .reset_index()
)
```

The outcome was practical and visible: 4,200 responses were analyzed, and 3 findings were adopted in the next funding plan. For Riverbend Education Fund, that meant the survey moved from being a large pile of feedback to a decision tool that directly informed future priorities.

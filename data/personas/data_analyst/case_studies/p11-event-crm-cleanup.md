# Event CRM Cleanup for Northlight Events

When Northlight Events came to me, their contact data was spread across five ticketing exports, and the same people often appeared multiple times with slightly different names, email formats, or other details. That made their CRM noisy, inflated the list size, and created avoidable problems in outreach. I was brought in on a fixed engagement to consolidate the data into one reliable Airtable base and make the contacts usable again.

My approach was to treat the project as a structured deduplication and normalization problem. I used Python and pandas to load each export, standardize the fields, and create a consistent schema before comparing records. From there, I built matching logic with rapidfuzz to find likely duplicates even when the text did not line up exactly. That let me catch near-matches that simple exact comparisons would have missed. I then reviewed the grouped candidates, merged the duplicate contacts, and loaded the cleaned set into Airtable so Northlight Events had a single source of truth.

```python
import pandas as pd
from rapidfuzz import fuzz

df = pd.read_csv("ticketing_export.csv")
df["name_clean"] = df["name"].str.lower().str.strip()
df["email_clean"] = df["email"].str.lower().str.strip()

score = fuzz.ratio(df.loc[0, "name_clean"], df.loc[1, "name_clean"])
if score >= 90:
    print("possible match")
```

The final result was a much cleaner CRM: 62k contacts were reduced to 41k unique records. That cleanup also improved deliverability, with the email bounce rate dropping from 14% to 3%. For Northlight Events, the biggest win was not just a smaller database, but a contact list they could trust for reporting and campaigns.

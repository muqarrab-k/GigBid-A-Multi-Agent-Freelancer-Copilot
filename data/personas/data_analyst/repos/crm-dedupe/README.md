Event CRM cleanup tools for normalizing contact data and deduplicating merged ticketing exports into a single Airtable base.

## Setup

Requires Python with `pandas`, `Airtable`, and `rapidfuzz`.

Install dependencies in your environment, then review the input/output paths in the scripts before running.

## Usage

```bash
python normalize.py
python dedupe.py
```

`normalize.py` prepares names, emails, and phone numbers for comparison.  
`dedupe.py` groups candidates by email domain and uses fuzzy name matching with `rapidfuzz`.

## Notes

This repository was used to merge duplicate contacts from five ticketing exports into one Airtable base.

The workflow reduced the contact set from 62k to 41k unique entries and lowered email bounce rate from 14% to 3%.

`normalize.py` should run before `dedupe.py` so the matching step works on cleaned fields.

The scripts are written for a fixed-scope cleanup task, not a general-purpose CRM pipeline.

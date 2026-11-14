# Data Card

The instructor did not provide GigSim or persona data. Per the instructor's note, GigBid builds
its market data from six public Kaggle datasets, adds synthetic data only where real data is
missing (next task), and keeps the two clearly separated. This card covers the **real-data
pipeline** (`make data`). Column-level details for every raw file are in
[data_profile.md](data_profile.md).

## Sources

| short name | Kaggle dataset | author | license | origin | rows used |
|---|---|---|---|---|---|
| jobs_2024_50k | [upwork-job-postings-dataset-2024-50k-records](https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records) | asaniczka | ODC-By | REAL | 52,977 of 53,058 |
| jobs_200k | [all-jobs-on-upwork-200k-plus](https://www.kaggle.com/datasets/asaniczka/all-jobs-on-upwork-200k-plus) | asaniczka | ODC-By | REAL | 679,033 of 826,328 |
| jobs_2023_60k | [upwork-freelance-jobs-60k](https://www.kaggle.com/datasets/ahmedmyalo/upwork-freelance-jobs-60k) | Ahmed Myalo | Apache 2.0 | REAL | 61,404 of 63,950 |
| contracts_1_3m | [freelance-contracts-dataset-1-3-million-entries](https://www.kaggle.com/datasets/asaniczka/freelance-contracts-dataset-1-3-million-entries) | asaniczka | ODC-By | REAL | 1,292,788 of 1,292,791 |
| freelancer_success | [freelancer-success-earnings-and-churn-prediction](https://www.kaggle.com/datasets/sarveshchhetri/freelancer-success-earnings-and-churn-prediction) | Sarvesh Chhetri | Apache 2.0 | **SYNTHETIC** (author's description) | 12,000 (distributions only) |
| fake_jobs | [trial-1](https://www.kaggle.com/datasets/adityammantri/trial-1) | Aditya_M_Mantri | Unknown on Kaggle | REAL + **generated** (see below) | 44,045 of 54,391 labelled |

Licenses were read from the Kaggle API (`licenseNameNullable`) by `data_pipeline/inspect.py`.

### Fields used

- **jobs_2024_50k / jobs_200k**: `title`, `link` (Upwork job key only), `description` (50k only),
  `published_date`, `is_hourly`, `hourly_low`, `hourly_high`, `budget`, `country`.
- **jobs_2023_60k**: `Job Title`, `Job_URL` (job key only), `Description`, `Category_1..9` (skill
  tags), `Search_Keyword` (stored as `category`), `EX_level_demand`, `Payment_type`, `Job_Cost`,
  `Hourly_Rate`, `Client_Country`, `New_Connects_Num` (real Connects cost). Client stats
  (`Spent($)`, `Rating`, `Feedback_Num`, `Payment_Situation`, `Applicants_Num`, `Freelancers_Num`,
  `Enterprise_Client`, `Time_Limitation`) feed `client_priors.json` only.
- **contracts_1_3m**: `job_title`, `start_date`, `end_date`, `total_hours`, `total_paid`,
  `hourly_rate`, `freelancer_id`, `job_id` (hashed into `contract_id`).
- **freelancer_success**: experience, skills count, profile flags, `primary_skill`, rate, jobs,
  success/repeat rates, response time, earnings, `churn_risk`, `earnings_tier`. Age, gender and
  country are not used.
- **fake_jobs**: `text` and `fraudulent` from the labelled file. The unlabelled file is not used.

## Outputs

| file | content | git |
|---|---|---|
| `data/raw/kaggle/<short_name>/` | downloaded files | ignored |
| `data/processed/jobs.parquet` | 793,414 `MarketJob` rows | ignored |
| `data/processed/contracts.parquet` | 1,292,788 `ContractRecord` rows | ignored |
| `data/processed/pricing_stats.json` | p10-p90 per persona x budget type (x experience) | ignored |
| `data/processed/client_priors.json` | client distributions (REAL) | ignored |
| `data/processed/freelancer_priors.json` | freelancer distributions (SYNTHETIC) | ignored |
| `data/processed/scam_examples.parquet` | 44,045 `ScamExample` rows | ignored |
| `data/processed/scam_signals.json` | top fake-leaning terms | ignored |
| `gigsim/seed/jobs_{history,stream,dev_pool}.jsonl` | 1,500 / 415 / 600 real job posts | **committed** |
| `docs/data_profile.md` | columns, nulls, 3 sample rows per file | committed |

The seed splits contain rows from `jobs_2024_50k` (ODC-By) and `jobs_2023_60k` (Apache 2.0) only.
Both licenses allow redistribution with attribution, which this card and `gigsim/seed/SPLITS.md`
provide. Nothing from `fake_jobs` (license unknown) is committed, except 120-character sample
excerpts in `data_profile.md`.

## Preprocessing (`data_pipeline/`)

1. **Same post, many scrapes.** Rows sharing an Upwork job key (`~01…` in the URL) are one post.
   2024: 147,375 repeat scrapes collapsed, keeping the row with a description (so the 50k set wins
   over its 200k twin; 52,452 of its keys also appear in the 200k set). 2023: 2,544 posts found
   under several search keywords collapsed. These are not reposts, so they are merged rather
   than marked.
2. **Text.** HTML stripped, entities unescaped, whitespace collapsed. 3 rows with no title dropped.
3. **Prices.** Fixed budget -> `budget_min = budget_max`; hourly ranges parsed from numbers or
   strings like `$15.00-$35.00`. Missing `is_hourly` (87,620 rows) inferred from which price field
   is present. Values `<= 0` or above the caps in `agent/config.yaml` (`max_fixed_budget`
   100,000, `max_hourly_rate` 500) are set to null and logged (313 budgets, 14 / 263 hourly
   values). Every price is USD; the 2023 cost strings were checked for other symbols.
4. **Skills.** 2023 rows keep their real tags. Other rows get skills by matching a vocabulary of
   1,275 real 2023 tags (seen 20+ times) against title and description (`skills_source`).
5. **Persona tags.** `ai_ml`, `fullstack`, `data_analyst` from `persona_keywords.yaml`
   (title/skill hit = 2, description hit = 1, tag at score 2). 106,003 jobs tagged, 6,811 with more
   than one tag.
6. **Duplicates kept, not deleted.** Union of an exact key (normalised title + description) and a
   near key (title + first 30 non-numeric description words). Title-only rows use title + country
   + prices, and title-only rows with no price are never grouped (too many generic titles).
   50,082 duplicate rows (6.3%), 4.1% among jobs with descriptions.
7. **Connects.** Real value for 2023 jobs (`connects_source = real`), else the
   `bidding_rules.connects_rule` in config. The fixed-price tiers were fitted on the 2023 jobs and
   match the real value for 49.2% of them: budget explains only part of the Connects cost.
8. **Contracts.** Type = hourly if `hourly_rate` exists, else fixed. Status = ongoing if no
   `end_date`. Dates outside 2000-01-01..2024-12-31 set to null (1 row).
9. **Pricing.** Jobs: fixed budget, or midpoint of the hourly range. Contracts: `total_paid` of
   ended fixed contracts, or `hourly_rate`. Zero values excluded, cells under 30 rows dropped.
10. **Scams.** Label 1 -> fake, 0 -> real; 10,346 rows without a label dropped. `templated` marks
    the generated pattern. Signals use smoothed log-odds on non-templated posts, counting each
    near-duplicate group once.
11. **Seed split.** Only jobs with 20+ description words. One representative per `dup_group`
    (longest description), shuffled with `data.seed` (4016). Each split is balanced over the three
    personas plus 15% off-topic; the stream keeps up to 3 reposts per group. Splits never share a
    `dup_group`. Re-running gives byte-identical files.

## Limitations

- **Scraped snapshots.** All job data comes from Upwork RSS/search scrapes by third parties.
  Upwork's own terms on reuse of post content are not covered by the Kaggle licenses.
- **Time window.** 2023 jobs: Feb-Mar 2023 (no absolute post date, only "x minutes ago").
  2024 jobs: Jul 2022 to Jul 2024, mostly Feb-Jul 2024. Prices and Connects rules have changed since.
- **Missing descriptions.** 679,033 of 793,414 jobs (the 200k set) have a title only, so their
  skills and persona tags are weaker. The seed splits use described jobs only.
- **No real category or client id** in the 2024 data. `category` is only set for 2023 jobs (the
  scraper's search keyword); pricing uses persona tags instead.
- **USD only.** No source has a currency column; Upwork shows USD. 11% of jobs have no budget type.
- **Sampling bias.** The 2023 set was scraped for four keywords (Developer, Marketing, 3D, Data
  science), so it over-represents those fields.
- **Client priors** are per job post, not per client (repeat posters count many times). The
  contracts set has no client fields, and each contract has its own `job_id`, so hire rate and
  hires per job cannot be measured.
- **freelancer_success is synthetic** and does not look like the real market: median hourly rate
  $280, capped at $280, versus a real contract median of $21. Use contracts for prices, and use
  this set only for shape (success rate, churn, response time).
- **fake_jobs is general employment ads**, not freelance gigs. 10,000 of its 12,523 fake rows
  (79.9%) follow one generated template ("… earn 5000week immediate hiring contact now at …"),
  so the fake class is mostly synthetic. Its text was already lowercased with punctuation removed,
  and location/industry are integer codes. Only 743 distinct organic fake posts remain after
  deduping, so `scam_signals.json` is noisy and includes company-specific phrasing.
- **Persona tagging is keyword based** and not validated against gold labels.

## Reproduce

```bash
make install
make data
```

Kaggle credentials (`~/.kaggle/kaggle.json`, `~/.kaggle/access_token`, or
`KAGGLE_USERNAME`/`KAGGLE_KEY`) let `make data` download missing sources; otherwise place each
dataset in `data/raw/kaggle/<short_name>/`.

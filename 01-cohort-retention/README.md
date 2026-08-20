# 01 — SQL Cohort Retention Report

**What it does:** Seeds a local SQLite database with 1 200 fake users across six monthly cohorts (Jan–Jun 2024), generates synthetic activity events, then runs a single CTE + window-function SQL query to compute month-over-month retention % per cohort. Outputs both a raw CSV and a pivot-table Markdown report.

## Key techniques

- Multi-step CTE (`cohorts → activity → cohort_sizes → retained`) keeps the logic readable and testable in isolation.
- `julianday()` arithmetic handles variable month lengths cleanly without application-side date math.
- `COUNT(DISTINCT user_id)` per `months_since_signup` bucket gives exact unique-user retention (not event-level counts).

## How to run

```bash
cd 01-cohort-retention
python seed_and_query.py
# → cohort.db (SQLite), retention_report.csv, retention_report.md
```

**Requirements:** Python 3.9+ (stdlib only — sqlite3, csv, datetime, random)

## Sample output (retention_report.md)

| Cohort  | Size | M+0   | M+1   | M+2   | M+3   | M+4   | M+5   |
|---------|------|-------|-------|-------|-------|-------|-------|
| 2024-01 | 200  | 100%  | 65.5% | 48.0% | 37.0% | 30.5% | 23.0% |
| 2024-02 | 200  | 100%  | 64.5% | 49.0% | 38.5% | 29.5% | 24.5% |
| …       | …    | …     | …     | …     | …     | …     | …     |

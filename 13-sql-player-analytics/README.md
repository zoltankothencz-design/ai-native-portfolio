# 13 - SQL Player Analytics (funnel, window functions, cohort LTV)

**What it does:** Seeds a local SQLite database with 2 000 synthetic online-casino players (six monthly registration cohorts, Jan to Jun 2024, five fictional acquisition channels), their deposits and gaming results, then runs three commented SQL files and writes CSV and Markdown outputs. It is the SQL companion to project 01: project 01 covers CTE cohort retention, this one covers funnel analysis, window functions, `LEFT JOIN` and conditional aggregation, and cohort LTV.

## Key techniques

Every technique below is checked by `test_queries.py`: the test fails if one of them does not appear in the `.sql` files (comments are ignored).

- `LEFT JOIN` keeps players who never deposited (funnel), and the anti-join pattern (`LEFT JOIN ... WHERE right.id IS NULL`) builds the KYC-passed-but-never-deposited list.
- `CASE WHEN` inside `COUNT(DISTINCT ...)` is the conditional aggregation that counts every funnel step in a single pass per channel.
- `LAG` returns the previous deposit date of the same player, giving the days between consecutive deposits.
- `ROW_NUMBER` ranks players inside each cohort (top 3 by GGR) and numbers each player's deposits.
- `NTILE` splits players into 10 GGR value tiers (deciles).
- `OVER` with `PARTITION BY` drives the window queries: running deposit total per player, cumulative GGR per cohort, and the decile share of total GGR.
- CTEs, a `CROSS JOIN` month grid and `UNION ALL` (total row) keep the queries readable.

## Queries

| File | Business question for CRM / affiliate teams | Output |
|---|---|---|
| `queries/01_funnel_by_channel.sql` | Where does each channel lose players between registration, KYC, first deposit (FTD) and second deposit? How many KYC-passed players never deposited (the reactivation list)? | `funnel_by_channel.csv`, `kyc_no_deposit_by_channel.csv` |
| `queries/02_window_functions.sql` | How fast do players re-deposit per channel (`LAG`)? Who are the top 3 players per cohort (`ROW_NUMBER`)? How concentrated is GGR (`NTILE` deciles)? When does a player cross a deposit threshold (running total)? | `deposit_gap_by_channel.csv`, `top3_players_per_cohort.csv`, `ggr_deciles.csv`, `running_deposit_total.csv` |
| `queries/03_cohort_ltv.sql` | How much cumulative GGR does an average player of each registration-month cohort bring by month since registration? | `cohort_ltv.csv` (pivot in the Markdown report) |

The revenue measure here is **GGR = stake - win** (gross gaming revenue). It is gross: NGR would also subtract bonus cost, taxes and fees, and none of that is modelled.

## How to run

```bash
cd 13-sql-player-analytics
python run_analytics.py     # builds player_analytics.db, writes output/*.csv and output/player_analytics_report.md
python test_queries.py      # plain asserts, no pytest needed
```

**Requirements:** Python 3.9+ (stdlib only: sqlite3, csv, datetime, random) and SQLite 3.25+ (window functions; the scripts stop with a clear message on older versions). No network. Runtime: about 0.1 s for data generation plus all queries. The data is deterministic (`random.Random(42)`), so two runs give identical outputs. `player_analytics.db` and the long `output/running_deposit_total.csv` are git-ignored; the other outputs are committed.

## How to read the output (sample from a real run)

### Funnel by channel

Counts per step, step-to-step conversion %, drop-off (players lost at each step) and overall registration-to-FTD %. Sorted by `reg_to_ftd_pct`; the last row is the total.

| channel     | registered | kyc_passed | ftd | second_deposit | reg_to_kyc_pct | kyc_to_ftd_pct | ftd_to_second_pct | reg_to_ftd_pct | dropoff_reg_to_kyc | dropoff_kyc_to_ftd | dropoff_ftd_to_second |
| ----------- | ---------- | ---------- | --- | -------------- | -------------- | -------------- | ----------------- | -------------- | ------------------ | ------------------ | --------------------- |
| crm_email   | 307        | 257        | 170 | 102            | 83.7           | 66.1           | 60.0              | 55.4           | 50                 | 87                 | 68                    |
| affiliate_a | 505        | 397        | 225 | 137            | 78.6           | 56.7           | 60.9              | 44.6           | 108                | 172                | 88                    |
| organic     | 508        | 388        | 215 | 106            | 76.4           | 55.4           | 49.3              | 42.3           | 120                | 173                | 109                   |
| affiliate_c | 297        | 201        | 113 | 60             | 67.7           | 56.2           | 53.1              | 38.0           | 96                 | 88                 | 53                    |
| affiliate_b | 383        | 248        | 110 | 47             | 64.8           | 44.4           | 42.7              | 28.7           | 135                | 138                | 63                    |
| ALL         | 2000       | 1491       | 833 | 452            | 74.5           | 55.9           | 54.3              | 41.6           | 509                | 658                | 381                   |

In this data `crm_email` converts best and `affiliate_b` worst (28.7 % registration-to-FTD vs 44.6 % for `affiliate_a`). The channel differences are set in the generator, so this shows how the query reads them, not a real-world finding.

### Reactivation list size (KYC passed, never deposited)

| channel     | kyc_passed | reactivation_list_size | pct_of_kyc_passed |
| ----------- | ---------- | ---------------------- | ----------------- |
| organic     | 388        | 173                    | 44.6              |
| affiliate_a | 397        | 172                    | 43.3              |
| affiliate_b | 248        | 138                    | 55.6              |
| affiliate_c | 201        | 88                     | 43.8              |
| crm_email   | 257        | 87                     | 33.9              |

### Days between consecutive deposits (`LAG`)

| channel     | gaps_measured | avg_gap_days |
| ----------- | ------------- | ------------ |
| affiliate_a | 323           | 13.4         |
| affiliate_b | 111           | 13.9         |
| crm_email   | 261           | 14.0         |
| organic     | 249           | 14.1         |
| affiliate_c | 127           | 14.9         |

### Top 3 players per cohort by GGR (`ROW_NUMBER`)

18 rows (3 per cohort), see `output/player_analytics_report.md`. Ties on GGR are broken by `player_id`.

### GGR deciles (`NTILE`, decile 1 = top 10 % of players)

| decile | players | total_ggr | avg_ggr | share_of_total_ggr_pct |
| ------ | ------- | --------- | ------- | ---------------------- |
| 1      | 84      | 95438.95  | 1136.18 | 85.7                   |
| 2      | 84      | 28381.68  | 337.88  | 25.5                   |
| 3      | 84      | 15661.15  | 186.44  | 14.1                   |
| 4      | 83      | 8772.03   | 105.69  | 7.9                    |
| 5      | 83      | 4484.47   | 54.03   | 4.0                    |
| 6      | 83      | 1926.72   | 23.21   | 1.7                    |
| 7      | 83      | 175.78    | 2.12    | 0.2                    |
| 8      | 83      | -2024.82  | -24.4   | -1.8                   |
| 9      | 83      | -6677.34  | -80.45  | -6.0                   |
| 10     | 83      | -34724.32 | -418.37 | -31.2                  |

The top decile holds 85.7 % of total GGR and the bottom decile is net negative (-31.2 %), because those players won more than they lost. That is a property of the synthetic win distribution, not a benchmark.

### Running deposit total (`SUM() OVER`), one sample player

| player_id | deposit_seq | deposited_at | amount | running_deposit_total |
| --------- | ----------- | ------------ | ------ | --------------------- |
| 4         | 1           | 2024-01-23   | 90.0   | 90.0                  |
| 4         | 2           | 2024-02-16   | 90.0   | 180.0                 |
| 4         | 3           | 2024-03-06   | 90.0   | 270.0                 |
| 4         | 4           | 2024-03-14   | 30.0   | 300.0                 |

### Cohort LTV: cumulative GGR per player by month since registration

Cumulative GGR of the cohort up to that month divided by the cohort size (all registered players, including those who never deposited). M+0 is the registration month. Offsets 0 to 5 are complete for every cohort because the data ends on 2024-12-31.

| Cohort  | Size | M+0   | M+1   | M+2   | M+3   | M+4   | M+5   |
| ------- | ---- | ----- | ----- | ----- | ----- | ----- | ----- |
| 2024-01 | 334  | 30.08 | 66.09 | 79.93 | 81.68 | 83.76 | 83.76 |
| 2024-02 | 333  | 16.21 | 39.44 | 52.82 | 54.27 | 54.19 | 54.33 |
| 2024-03 | 333  | 9.34  | 25.89 | 29.75 | 34.31 | 34.97 | 34.97 |
| 2024-04 | 334  | 8.52  | 49.11 | 68.76 | 72.46 | 72.70 | 72.70 |
| 2024-05 | 333  | 12.32 | 35.64 | 40.91 | 48.03 | 47.90 | 47.89 |
| 2024-06 | 333  | 3.45  | 34.24 | 38.82 | 40.36 | 40.14 | 40.46 |

A cumulative value can dip slightly (see 2024-02, M+4) when a month has net negative GGR.

## Limitations

- All data is synthetic and generated from simple probabilities. Funnel rates, deposit sizes and win distributions are chosen by me, not measured. Differences between cohorts are random noise from a few heavy-tail players, not a trend.
- The revenue figures are GGR (stake - win), not NGR. Bonus cost, taxes and fees are not modelled, so a real NGR would be lower.
- There are no real tracking events: no clicks, sessions, affiliate postbacks, bonus grants, withdrawals or chargebacks. The funnel starts at registration, not at a landing page or click.
- Gaming results are a few session rows per deposit, not individual bets or game rounds.
- KYC is a single date per player, and the generator only lets KYC-passed players deposit, so the funnel is nested by construction.
- SQLite only. The window functions are standard SQL, but date functions (`strftime`, `julianday`) would need changes for another database.

_All data is synthetic. No real player, operator or company data was used._

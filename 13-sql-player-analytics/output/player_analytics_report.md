# Player Analytics Report

Synthetic data. GGR = stake - win (gross: no bonus cost, taxes or fees, so not NGR).

## 1. Funnel by channel

| channel     | registered | kyc_passed | ftd | second_deposit | reg_to_kyc_pct | kyc_to_ftd_pct | ftd_to_second_pct | reg_to_ftd_pct | dropoff_reg_to_kyc | dropoff_kyc_to_ftd | dropoff_ftd_to_second |
| ----------- | ---------- | ---------- | --- | -------------- | -------------- | -------------- | ----------------- | -------------- | ------------------ | ------------------ | --------------------- |
| crm_email   | 307        | 257        | 170 | 102            | 83.7           | 66.1           | 60.0              | 55.4           | 50                 | 87                 | 68                    |
| affiliate_a | 505        | 397        | 225 | 137            | 78.6           | 56.7           | 60.9              | 44.6           | 108                | 172                | 88                    |
| organic     | 508        | 388        | 215 | 106            | 76.4           | 55.4           | 49.3              | 42.3           | 120                | 173                | 109                   |
| affiliate_c | 297        | 201        | 113 | 60             | 67.7           | 56.2           | 53.1              | 38.0           | 96                 | 88                 | 53                    |
| affiliate_b | 383        | 248        | 110 | 47             | 64.8           | 44.4           | 42.7              | 28.7           | 135                | 138                | 63                    |
| ALL         | 2000       | 1491       | 833 | 452            | 74.5           | 55.9           | 54.3              | 41.6           | 509                | 658                | 381                   |

## 1b. KYC passed, never deposited (CRM reactivation list)

| channel     | kyc_passed | reactivation_list_size | pct_of_kyc_passed |
| ----------- | ---------- | ---------------------- | ----------------- |
| organic     | 388        | 173                    | 44.6              |
| affiliate_a | 397        | 172                    | 43.3              |
| affiliate_b | 248        | 138                    | 55.6              |
| affiliate_c | 201        | 88                     | 43.8              |
| crm_email   | 257        | 87                     | 33.9              |

## 2a. Average days between consecutive deposits

| channel     | gaps_measured | avg_gap_days |
| ----------- | ------------- | ------------ |
| affiliate_a | 323           | 13.4         |
| affiliate_b | 111           | 13.9         |
| crm_email   | 261           | 14.0         |
| organic     | 249           | 14.1         |
| affiliate_c | 127           | 14.9         |

## 2b. Top 3 players per cohort by GGR

| cohort_month | rank_in_cohort | player_id | channel     | ggr     |
| ------------ | -------------- | --------- | ----------- | ------- |
| 2024-01      | 1              | 270       | affiliate_a | 5251.15 |
| 2024-01      | 2              | 39        | organic     | 2883.21 |
| 2024-01      | 3              | 210       | crm_email   | 2470.04 |
| 2024-02      | 1              | 459       | affiliate_a | 1973.42 |
| 2024-02      | 2              | 606       | affiliate_b | 1942.01 |
| 2024-02      | 3              | 419       | affiliate_c | 1487.4  |
| 2024-03      | 1              | 810       | crm_email   | 1980.18 |
| 2024-03      | 2              | 704       | affiliate_b | 1641.85 |
| 2024-03      | 3              | 768       | organic     | 1037.91 |
| 2024-04      | 1              | 1330      | organic     | 4365.5  |
| 2024-04      | 2              | 1143      | affiliate_a | 2925.91 |
| 2024-04      | 3              | 1326      | affiliate_a | 1786.2  |
| 2024-05      | 1              | 1637      | crm_email   | 2908.18 |
| 2024-05      | 2              | 1392      | affiliate_b | 2010.47 |
| 2024-05      | 3              | 1464      | organic     | 1216.96 |
| 2024-06      | 1              | 1748      | affiliate_b | 2101.23 |
| 2024-06      | 2              | 1704      | crm_email   | 1075.15 |
| 2024-06      | 3              | 1703      | affiliate_a | 1012.74 |

## 2c. GGR deciles (1 = top 10 percent of players)

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

## 2d. Running deposit total (sample: player 4)

| player_id | deposit_seq | deposited_at | amount | running_deposit_total |
| --------- | ----------- | ------------ | ------ | --------------------- |
| 4         | 1           | 2024-01-23   | 90.0   | 90.0                  |
| 4         | 2           | 2024-02-16   | 90.0   | 180.0                 |
| 4         | 3           | 2024-03-06   | 90.0   | 270.0                 |
| 4         | 4           | 2024-03-14   | 30.0   | 300.0                 |

## 3. Cohort LTV: cumulative GGR per player by month since registration

| Cohort  | Size | M+0   | M+1   | M+2   | M+3   | M+4   | M+5   |
| ------- | ---- | ----- | ----- | ----- | ----- | ----- | ----- |
| 2024-01 | 334  | 30.08 | 66.09 | 79.93 | 81.68 | 83.76 | 83.76 |
| 2024-02 | 333  | 16.21 | 39.44 | 52.82 | 54.27 | 54.19 | 54.33 |
| 2024-03 | 333  | 9.34  | 25.89 | 29.75 | 34.31 | 34.97 | 34.97 |
| 2024-04 | 334  | 8.52  | 49.11 | 68.76 | 72.46 | 72.70 | 72.70 |
| 2024-05 | 333  | 12.32 | 35.64 | 40.91 | 48.03 | 47.90 | 47.89 |
| 2024-06 | 333  | 3.45  | 34.24 | 38.82 | 40.36 | 40.14 | 40.46 |

_Generated from synthetic data. No real player data._

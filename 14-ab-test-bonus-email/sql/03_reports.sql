-- 03_reports.sql
-- Read-only queries behind the report. Each block starts with "-- @query: name" and
-- becomes output/<name>.csv. The statistical tests themselves run in Python
-- (ab_stats.py) on the counts and per-player values these tables provide.

-- @query: eligibility_flow
-- How many players survive each exclusion rule. LAG gives the number removed per step.
WITH steps AS (
    SELECT 1 AS step, 'candidates (KYC passed, 3 days ago)' AS stage, COUNT(*) AS players
    FROM candidates
    UNION ALL
    SELECT 2, 'after: not deposited before', COUNT(*)
    FROM candidates WHERE deposits_before = 0
    UNION ALL
    SELECT 3, 'after: no responsible-gaming flag', COUNT(*)
    FROM candidates WHERE deposits_before = 0 AND rg_flag = 0
    UNION ALL
    SELECT 4, 'after: email consent = ELIGIBLE', COUNT(*)
    FROM candidates WHERE deposits_before = 0 AND rg_flag = 0 AND email_consent = 1
)
SELECT step,
       stage,
       players,
       COALESCE(LAG(players) OVER (ORDER BY step) - players, 0) AS removed
FROM steps
ORDER BY step;

-- @query: enrolment_by_day
-- Players enter on 14 consecutive days (two full weeks, so every weekday appears twice
-- and a weekday effect cannot favour one arm). Conditional aggregation pivots the arms.
SELECT t0 AS email_date,
       SUM(variant = 'A') AS arm_a,
       SUM(variant = 'B') AS arm_b,
       COUNT(*)           AS total
FROM assignments
GROUP BY t0
ORDER BY t0;

-- @query: variant_summary
-- Raw totals per arm; the Python step turns them into tests and intervals.
SELECT variant,
       COUNT(*)                                               AS players,
       SUM(converted_7d)                                      AS converted_7d,
       ROUND(100.0 * SUM(converted_7d) / COUNT(*), 2)         AS conv_pct,
       SUM(unsub_7d)                                          AS unsub_7d,
       ROUND(100.0 * SUM(unsub_7d) / COUNT(*), 2)             AS unsub_pct,
       ROUND(AVG(CASE WHEN converted_7d = 1
                      THEN first_deposit_amount END), 2)      AS avg_first_deposit_of_converters,
       ROUND(SUM(ggr_14d), 2)                                 AS ggr_14d,
       ROUND(SUM(bonus_cost), 2)                              AS bonus_cost,
       ROUND(SUM(ggr_14d) - SUM(bonus_cost), 2)               AS net_value,
       ROUND((SUM(ggr_14d) - SUM(bonus_cost)) / COUNT(*), 3)  AS net_value_per_player
FROM player_metrics
GROUP BY variant
ORDER BY variant;

-- @query: balance_by_channel
-- Covariate balance: randomisation should give both arms the same channel mix.
SELECT channel,
       SUM(variant = 'A') AS a_players,
       SUM(variant = 'B') AS b_players,
       ROUND(100.0 * SUM(variant = 'A') / (SELECT COUNT(*) FROM assignments WHERE variant = 'A'), 2) AS a_share_pct,
       ROUND(100.0 * SUM(variant = 'B') / (SELECT COUNT(*) FROM assignments WHERE variant = 'B'), 2) AS b_share_pct
FROM assignments
GROUP BY channel
ORDER BY channel;

-- @query: balance_by_country
SELECT country,
       SUM(variant = 'A') AS a_players,
       SUM(variant = 'B') AS b_players,
       ROUND(100.0 * SUM(variant = 'A') / (SELECT COUNT(*) FROM assignments WHERE variant = 'A'), 2) AS a_share_pct,
       ROUND(100.0 * SUM(variant = 'B') / (SELECT COUNT(*) FROM assignments WHERE variant = 'B'), 2) AS b_share_pct
FROM assignments
GROUP BY country
ORDER BY country;

-- @query: conversion_by_channel
-- EXPLORATORY ONLY. Subgroups are small and were not part of the plan, so a gap here is
-- a hypothesis for the next test, not a result. Slicing until something is "significant"
-- is the most common way to fool yourself with an A/B test.
SELECT channel,
       SUM(variant = 'A')                                                  AS a_players,
       ROUND(100.0 * SUM(CASE WHEN variant = 'A' THEN converted_7d END)
                   / SUM(variant = 'A'), 2)                                AS a_conv_pct,
       SUM(variant = 'B')                                                  AS b_players,
       ROUND(100.0 * SUM(CASE WHEN variant = 'B' THEN converted_7d END)
                   / SUM(variant = 'B'), 2)                                AS b_conv_pct,
       ROUND(100.0 * SUM(CASE WHEN variant = 'B' THEN converted_7d END) / SUM(variant = 'B')
           - 100.0 * SUM(CASE WHEN variant = 'A' THEN converted_7d END) / SUM(variant = 'A'), 2) AS diff_pp
FROM player_metrics
GROUP BY channel
ORDER BY channel;

-- 03_cohort_ltv.sql
-- Business question: how much cumulative NGR does an average player of each
-- registration-month cohort generate by month since registration (simplified LTV)?
-- Techniques: window SUM over months, CROSS JOIN month grid + LEFT JOIN so months
-- without gaming still appear, division by cohort size (all registered players, not
-- only the active ones).
-- NGR is simplified: stake - win. No bonus cost, no taxes, no fees.
-- Month offset 0 is the registration month. Offsets 0 to 5 are complete for all cohorts.

-- @query: cohort_ltv
WITH cohort_players AS (
    SELECT
        player_id,
        strftime('%Y-%m', registered_at) AS cohort_month,
        CAST(strftime('%Y', registered_at) AS INTEGER) * 12
          + CAST(strftime('%m', registered_at) AS INTEGER) AS reg_month_index
    FROM players
),
cohort_sizes AS (
    SELECT cohort_month, MIN(reg_month_index) AS reg_month_index, COUNT(*) AS cohort_size
    FROM cohort_players
    GROUP BY cohort_month
),
months(month_offset) AS (
    VALUES (0), (1), (2), (3), (4), (5)
),
monthly_ngr AS (
    SELECT
        cp.cohort_month,
        (CAST(strftime('%Y', g.played_at) AS INTEGER) * 12
           + CAST(strftime('%m', g.played_at) AS INTEGER)) - cp.reg_month_index AS month_offset,
        SUM(g.stake - g.win) AS ngr
    FROM gaming_results g
    JOIN cohort_players cp ON cp.player_id = g.player_id
    GROUP BY cp.cohort_month, month_offset
),
grid AS (
    SELECT
        cs.cohort_month,
        cs.cohort_size,
        m.month_offset,
        COALESCE(mn.ngr, 0) AS ngr
    FROM cohort_sizes cs
    CROSS JOIN months m
    LEFT JOIN monthly_ngr mn
           ON mn.cohort_month = cs.cohort_month
          AND mn.month_offset = m.month_offset
)
SELECT
    cohort_month,
    cohort_size,
    month_offset,
    ROUND(ngr, 2) AS month_ngr,
    ROUND(SUM(ngr) OVER (
              PARTITION BY cohort_month
              ORDER BY month_offset
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) / cohort_size, 2)
        AS cumulative_ngr_per_player
FROM grid
ORDER BY cohort_month, month_offset;

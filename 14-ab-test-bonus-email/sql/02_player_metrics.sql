-- 02_player_metrics.sql
-- Step 2: one row per assigned player with every outcome measured in a fixed window
-- that starts on that player's own email day (t0). Windows are relative to t0, not to
-- the calendar, so a player who entered on day 14 gets exactly as long as one who
-- entered on day 1.
--
--   converted_7d         first deposit within 7 days of the email (primary metric)
--   first_deposit_amount amount of that first deposit (0 if none)
--   bonus_cost           bonus credited with that deposit (face value, 0 in arm A)
--   ggr_14d              GGR = stake - win over the 14 days after the email
--   unsub_7d             unsubscribed within 7 days (guardrail)
--
-- Players with no deposit stay in the table with zeros (LEFT JOIN). Dropping them would
-- compare only the converters, which is a different, biased question.

DROP TABLE IF EXISTS player_metrics;

CREATE TABLE player_metrics AS
WITH ranked AS (
    SELECT a.player_id,
           d.amount,
           d.bonus_amount,
           ROW_NUMBER() OVER (PARTITION BY a.player_id
                              ORDER BY d.deposited_at, d.deposit_id) AS rn
    FROM assignments a
    JOIN deposits d
      ON d.player_id = a.player_id
     AND d.deposited_at >= a.t0
     AND d.deposited_at <= date(a.t0, '+7 days')
),
first_dep AS (
    SELECT player_id, amount, bonus_amount FROM ranked WHERE rn = 1
),
ggr AS (
    SELECT a.player_id, SUM(g.stake - g.win) AS ggr_14d
    FROM assignments a
    JOIN gaming_results g
      ON g.player_id = a.player_id
     AND g.played_at >= a.t0
     AND g.played_at <= date(a.t0, '+14 days')
    GROUP BY a.player_id
),
unsub AS (
    SELECT a.player_id, 1 AS unsub_7d
    FROM assignments a
    JOIN email_events e ON e.player_id = a.player_id
    WHERE e.unsubscribed_at IS NOT NULL
      AND e.unsubscribed_at <= date(a.t0, '+7 days')
)
SELECT a.player_id,
       a.variant,
       a.channel,
       a.country,
       a.t0,
       CASE WHEN f.player_id IS NULL THEN 0 ELSE 1 END AS converted_7d,
       COALESCE(f.amount, 0)       AS first_deposit_amount,
       COALESCE(f.bonus_amount, 0) AS bonus_cost,
       COALESCE(g.ggr_14d, 0)      AS ggr_14d,
       COALESCE(u.unsub_7d, 0)     AS unsub_7d
FROM assignments a
LEFT JOIN first_dep f ON f.player_id = a.player_id
LEFT JOIN ggr g       ON g.player_id = a.player_id
LEFT JOIN unsub u     ON u.player_id = a.player_id;

CREATE UNIQUE INDEX idx_player_metrics_player ON player_metrics(player_id);

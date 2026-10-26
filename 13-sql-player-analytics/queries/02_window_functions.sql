-- 02_window_functions.sql
-- Four window-function queries on the same tables. GGR = stake - win. This is gross
-- revenue: no bonus cost, taxes or fees are subtracted, so it is not NGR.
-- The runner splits this file on the "-- @query:" marker lines.

-- @query: deposit_gap_by_channel
-- (a) LAG: days between a player's consecutive deposits, then the average per channel.
-- Business use: how fast do players come back to deposit, per acquisition channel?
WITH deposit_gaps AS (
    SELECT
        p.channel,
        d.player_id,
        julianday(d.deposited_at)
          - julianday(LAG(d.deposited_at) OVER (
                PARTITION BY d.player_id
                ORDER BY d.deposited_at, d.deposit_id)) AS gap_days
    FROM deposits d
    JOIN players p ON p.player_id = d.player_id
)
SELECT
    channel,
    COUNT(gap_days)           AS gaps_measured,   -- first deposits have no previous one
    ROUND(AVG(gap_days), 1)   AS avg_gap_days
FROM deposit_gaps
WHERE gap_days IS NOT NULL
GROUP BY channel
ORDER BY avg_gap_days, channel;

-- @query: top3_players_per_cohort
-- (b) ROW_NUMBER: the three highest-GGR players in each registration-month cohort.
-- Business use: who are the VIP candidates of each cohort, and which channel did they come from?
WITH player_ggr AS (
    SELECT
        p.player_id,
        p.channel,
        strftime('%Y-%m', p.registered_at) AS cohort_month,
        COALESCE(SUM(g.stake - g.win), 0)  AS ggr
    FROM players p
    LEFT JOIN gaming_results g ON g.player_id = p.player_id
    GROUP BY p.player_id, p.channel, cohort_month
),
ranked AS (
    SELECT
        player_ggr.*,
        ROW_NUMBER() OVER (
            PARTITION BY cohort_month
            ORDER BY ggr DESC, player_id) AS rank_in_cohort  -- player_id breaks ties
    FROM player_ggr
)
SELECT cohort_month, rank_in_cohort, player_id, channel, ROUND(ggr, 2) AS ggr
FROM ranked
WHERE rank_in_cohort <= 3
ORDER BY cohort_month, rank_in_cohort;

-- @query: ggr_deciles
-- (c) NTILE(10): player value tiers. Decile 1 = the top 10 percent of players by GGR.
-- Only players with at least one gaming row are ranked.
-- Business use: how concentrated is revenue? A share above 100 percent in the top
-- decile just means the lower deciles are net negative (players who won).
WITH player_ggr AS (
    SELECT g.player_id, SUM(g.stake - g.win) AS ggr
    FROM gaming_results g
    GROUP BY g.player_id
),
tiered AS (
    SELECT
        player_id,
        ggr,
        NTILE(10) OVER (ORDER BY ggr DESC, player_id) AS decile
    FROM player_ggr
)
SELECT
    decile,
    COUNT(*)                                  AS players,
    ROUND(SUM(ggr), 2)                        AS total_ggr,
    ROUND(AVG(ggr), 2)                        AS avg_ggr,
    ROUND(100.0 * SUM(ggr) / SUM(SUM(ggr)) OVER (), 1) AS share_of_total_ggr_pct
FROM tiered
GROUP BY decile
ORDER BY decile;

-- @query: running_deposit_total
-- (d) Running total with SUM() OVER: cumulative deposits per player in time order.
-- Business use: the point at which a player crosses a deposit threshold (VIP, bonus eligibility).
SELECT
    player_id,
    ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY deposited_at, deposit_id) AS deposit_seq,
    deposited_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY player_id
        ORDER BY deposited_at, deposit_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_deposit_total
FROM deposits
ORDER BY player_id, deposited_at, deposit_id;

-- 01_funnel_by_channel.sql
-- Business question: where does each acquisition channel lose players on the way
-- from registration to a repeat depositor, and how big is the CRM reactivation list?
-- Techniques: conditional aggregation (COUNT(DISTINCT CASE WHEN ...)), LEFT JOIN,
-- LEFT JOIN anti-join (WHERE right side IS NULL), UNION ALL for a total row.
--
-- Funnel steps (each step requires the previous one):
--   registered -> kyc_passed -> ftd (first deposit) -> second_deposit
--
-- The runner splits this file on the "-- @query:" marker lines.

-- @query: funnel_by_channel
WITH deposit_stats AS (
    -- one row per depositing player; players without deposits are absent on purpose
    SELECT player_id, COUNT(*) AS deposit_count
    FROM deposits
    GROUP BY player_id
),
step_counts AS (
    SELECT
        p.channel,
        COUNT(DISTINCT p.player_id) AS registered,
        COUNT(DISTINCT CASE WHEN p.kyc_verified_at IS NOT NULL
                            THEN p.player_id END) AS kyc_passed,
        COUNT(DISTINCT CASE WHEN p.kyc_verified_at IS NOT NULL
                             AND ds.player_id IS NOT NULL
                            THEN p.player_id END) AS ftd,
        COUNT(DISTINCT CASE WHEN p.kyc_verified_at IS NOT NULL
                             AND ds.deposit_count >= 2
                            THEN p.player_id END) AS second_deposit
    FROM players p
    LEFT JOIN deposit_stats ds ON ds.player_id = p.player_id   -- keep non-depositors
    GROUP BY p.channel
),
with_total AS (
    SELECT channel, registered, kyc_passed, ftd, second_deposit FROM step_counts
    UNION ALL
    SELECT 'ALL', SUM(registered), SUM(kyc_passed), SUM(ftd), SUM(second_deposit)
    FROM step_counts
)
SELECT
    channel,
    registered,
    kyc_passed,
    ftd,
    second_deposit,
    ROUND(100.0 * kyc_passed     / NULLIF(registered, 0), 1) AS reg_to_kyc_pct,
    ROUND(100.0 * ftd            / NULLIF(kyc_passed, 0), 1) AS kyc_to_ftd_pct,
    ROUND(100.0 * second_deposit / NULLIF(ftd, 0), 1)        AS ftd_to_second_pct,
    ROUND(100.0 * ftd            / NULLIF(registered, 0), 1) AS reg_to_ftd_pct,
    registered - kyc_passed      AS dropoff_reg_to_kyc,
    kyc_passed - ftd             AS dropoff_kyc_to_ftd,
    ftd - second_deposit         AS dropoff_ftd_to_second
FROM with_total
ORDER BY CASE WHEN channel = 'ALL' THEN 1 ELSE 0 END, reg_to_ftd_pct DESC, channel;

-- @query: kyc_no_deposit_by_channel
-- Anti-join: players who passed KYC but never deposited. This is the size of the
-- CRM reactivation list per channel.
WITH kyc_players AS (
    SELECT player_id, channel
    FROM players
    WHERE kyc_verified_at IS NOT NULL
),
never_deposited AS (
    SELECT k.player_id
    FROM kyc_players k
    LEFT JOIN deposits d ON d.player_id = k.player_id
    WHERE d.deposit_id IS NULL                                  -- the anti-join
)
SELECT
    k.channel,
    COUNT(DISTINCT k.player_id) AS kyc_passed,
    COUNT(DISTINCT n.player_id) AS reactivation_list_size,
    ROUND(100.0 * COUNT(DISTINCT n.player_id) / COUNT(DISTINCT k.player_id), 1)
        AS pct_of_kyc_passed
FROM kyc_players k
LEFT JOIN never_deposited n ON n.player_id = k.player_id
GROUP BY k.channel
ORDER BY reactivation_list_size DESC, k.channel;

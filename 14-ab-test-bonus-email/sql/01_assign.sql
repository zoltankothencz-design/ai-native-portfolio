-- 01_assign.sql
-- Step 1 of the experiment: decide WHO is in it and WHICH arm each player gets.
-- Runs once, before any outcome exists. The result is the table `assignments`.
--
-- Audience: players who passed KYC, never deposited and are 3 days past KYC
-- (the same "reactivation list" idea as project 13). Three exclusions, applied
-- BEFORE the split so both arms are filtered the same way:
--   deposits_before > 0   not a first-time-deposit audience any more
--   rg_flag = 1           responsible-gaming flag (self-exclusion or limit set): never
--                         receives a promotion, a compliance rule, not a modelling choice
--   email_consent = 0     cannot be contacted
--
-- Randomisation: hash the player id together with an experiment-specific salt and
-- take the remainder modulo 100. The same player always lands in the same arm
-- (re-running or re-reading the data never reshuffles anyone), and a different
-- salt gives an independent split for the next experiment.
--
-- ab_hash(id, salt) is a Python function registered in SQLite (SHA-256, first 56 bits).
-- In a warehouse the same line is a built-in:
--   Snowflake:  MOD(ABS(HASH(player_id, 'bonus_email_2024_07')), 100) < 50
--   BigQuery:   MOD(ABS(FARM_FINGERPRINT(CONCAT(CAST(player_id AS STRING), 'bonus_email_2024_07'))), 100) < 50

DROP TABLE IF EXISTS assignments;

CREATE TABLE assignments AS
SELECT c.player_id,
       c.channel,
       c.country,
       c.entered_at AS t0,                  -- day the email is sent; all windows start here
       CASE WHEN ab_hash(c.player_id, 'bonus_email_2024_07') % 100 < 50
            THEN 'A'                        -- control: standard reminder, no bonus
            ELSE 'B'                        -- treatment: reminder + 100% deposit match, up to 50
       END AS variant
FROM candidates c
WHERE c.deposits_before = 0
  AND c.rg_flag = 0
  AND c.email_consent = 1;

CREATE UNIQUE INDEX idx_assignments_player ON assignments(player_id);

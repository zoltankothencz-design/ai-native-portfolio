"""
Tests for the A/B test demo. Plain asserts, no pytest needed:  python test_ab.py

Three groups:
  * statistics checked against hand-computed or textbook values
  * the experiment data: assignment rules, windows, bonus rules, re-derived metrics
  * guards: decision rule, SQL techniques present, no em dash in the project
"""

import datetime
import pathlib
import re
import sqlite3

import ab_stats as st
import run_experiment as ex

HERE = pathlib.Path(__file__).resolve().parent


def close(a, b, tol):
    return abs(a - b) <= tol


# ------------------------------------------------------------- statistics
def test_distribution_reference_values():
    assert close(st.chi2_sf(3.841458820694124, 1), 0.05, 1e-6)       # textbook 5% point, df 1
    assert close(st.chi2_sf(9.487729036781154, 4), 0.05, 1e-6)       # textbook 5% point, df 4
    assert close(st.chi2_sf(20.0, 5), 0.00124973, 1e-7)
    assert close(st.normal_sf(1.959963984540054), 0.025, 1e-9)
    assert close(st.normal_ppf(0.975), 1.959964, 1e-6)


def test_sample_size_and_power():
    # 10% -> 12%, alpha 0.05, power 80%: worked by hand = 3 841 per arm
    assert st.sample_size_per_arm(0.10, 0.12) == 3841
    assert close(st.power_two_proportions(0.10, 0.12, 3841), 0.80, 0.005)
    assert st.sample_size_per_arm(0.10, 0.11) > 3 * st.sample_size_per_arm(0.10, 0.12)  # halving the lift needs ~4x


def test_two_proportion_test_hand_example():
    # 100/1000 vs 130/1000: pooled p 0.115, z = 0.03 / 0.014267 = 2.103, two-sided p about 0.0355
    r = st.two_proportion_test(100, 1000, 130, 1000)
    assert close(r["diff"], 0.03, 1e-12)
    assert close(r["z"], 2.1027, 1e-3)
    assert close(r["p_value"], 0.0355, 5e-4)
    assert r["ci_low"] < r["diff"] < r["ci_high"]
    same = st.two_proportion_test(100, 1000, 100, 1000)
    assert same["p_value"] > 0.99 and same["diff"] == 0


def test_srm_detects_a_broken_split():
    assert st.srm_check([4000, 4000], [0.5, 0.5])["ok"]
    assert st.srm_check([4116, 4070], [0.5, 0.5])["ok"]
    broken = st.srm_check([4000, 4400], [0.5, 0.5])
    assert not broken["ok"] and broken["p_value"] < 0.001


def test_chi_square_independence_hand_example():
    r = st.chi_square_independence([[10, 20], [30, 40]])     # expected counts 12/18/28/42
    assert close(r["chi2"], 0.7937, 1e-3) and r["df"] == 1
    assert close(r["p_value"], 0.373, 2e-3)
    assert st.chi_square_independence([[50, 50], [50, 50]])["p_value"] > 0.999


def test_bootstrap_and_winsorize():
    sure = st.bootstrap_mean_diff([0.0] * 100, [1.0] * 100, n_boot=200, ci_level=0.95, seed=1)
    assert sure["diff"] == 1.0 and sure["ci_low"] == 1.0 and sure["ci_high"] == 1.0
    base = [float(i % 10) for i in range(500)]
    null = st.bootstrap_mean_diff(base, list(base), n_boot=300, ci_level=0.95, seed=2)
    assert null["ci_low"] <= 0.0 <= null["ci_high"]
    capped, lo, hi = st.winsorize(list(range(1, 101)) + [10000], 0.01, 0.99)
    assert max(capped) == hi < 101 and min(capped) == lo >= 1


def test_peeking_inflates_false_positives():
    r = st.peeking_simulation(p=0.10, n_per_arm=2000, n_looks=10, n_sims=300, seed=5)
    assert r["fp_single_look"] < 0.10          # one look keeps the 5% promise (within noise)
    assert r["fp_peeking"] > 0.12              # daily looks break it
    assert r["fp_peeking"] > 2 * r["fp_single_look"] - 0.02


# ----------------------------------------------------------- experiment data
_CACHE = {}


def experiment():
    """Build the experiment once in memory and reuse it."""
    if "con" not in _CACHE:
        con = ex.new_connection(":memory:")
        ex.build_experiment(con)
        _CACHE["con"] = con
    return _CACHE["con"]


def test_each_eligible_player_has_exactly_one_arm():
    con = experiment()
    n_rows, n_distinct, arms = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT player_id), COUNT(DISTINCT variant) FROM assignments").fetchone()
    assert n_rows == n_distinct and arms == 2
    assert {r[0] for r in con.execute("SELECT DISTINCT variant FROM assignments")} == {"A", "B"}


def test_excluded_players_are_never_assigned():
    con = experiment()
    leaked = con.execute("""SELECT COUNT(*) FROM assignments a JOIN candidates c USING (player_id)
                            WHERE c.deposits_before > 0 OR c.rg_flag = 1 OR c.email_consent = 0""").fetchone()[0]
    assert leaked == 0
    eligible = con.execute("""SELECT COUNT(*) FROM candidates
                              WHERE deposits_before = 0 AND rg_flag = 0 AND email_consent = 1""").fetchone()[0]
    assert eligible == con.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    # the rule must actually bite: every exclusion removes someone
    assert con.execute("SELECT COUNT(*) FROM candidates WHERE rg_flag = 1").fetchone()[0] > 0
    assert con.execute("SELECT COUNT(*) FROM candidates WHERE email_consent = 0").fetchone()[0] > 0


def test_assignment_is_deterministic_and_salt_dependent():
    con = experiment()
    other = ex.new_connection(":memory:")
    ex.build_experiment(other)
    q = "SELECT player_id, variant FROM assignments ORDER BY player_id"
    assert con.execute(q).fetchall() == other.execute(q).fetchall()
    # a different salt gives an independent split: about half of the players switch arm
    ids = [r[0] for r in con.execute("SELECT player_id FROM assignments")]
    same = sum((ex.ab_hash(i, "bonus_email_2024_07") % 100 < 50) == (ex.ab_hash(i, "another_salt") % 100 < 50)
               for i in ids)
    assert 0.45 < same / float(len(ids)) < 0.55


def test_split_passes_srm_and_is_balanced():
    con = experiment()
    a, b = [con.execute("SELECT COUNT(*) FROM assignments WHERE variant = ?", (v,)).fetchone()[0] for v in "AB"]
    assert st.srm_check([a, b], [0.5, 0.5], 0.001)["ok"]
    for col in ("channel", "country"):
        table = [[x, y] for _, x, y in con.execute(
            "SELECT %s, SUM(variant='A'), SUM(variant='B') FROM assignments GROUP BY %s" % (col, col))]
        assert st.chi_square_independence(table)["p_value"] > 0.001


def test_metrics_match_an_independent_recomputation():
    """Re-derive every player's metrics in Python from the raw tables and compare."""
    con = experiment()
    days = lambda s, n: (datetime.date.fromisoformat(s) + datetime.timedelta(days=n)).isoformat()
    deps, play, mail = {}, {}, {}
    for pid, d, amt, bonus, dep_id in con.execute(
            "SELECT player_id, deposited_at, amount, bonus_amount, deposit_id FROM deposits"):
        deps.setdefault(pid, []).append((d, dep_id, amt, bonus))
    for pid, d, stake, win in con.execute("SELECT player_id, played_at, stake, win FROM gaming_results"):
        play.setdefault(pid, []).append((d, stake - win))
    for pid, un in con.execute("SELECT player_id, unsubscribed_at FROM email_events"):
        mail[pid] = un
    checked = converted = late = 0
    for pid, variant, t0, conv, amt0, bonus0, ggr0, unsub0 in con.execute(
            "SELECT player_id, variant, t0, converted_7d, first_deposit_amount, bonus_cost, ggr_14d, unsub_7d "
            "FROM player_metrics"):
        in_win = sorted(x for x in deps.get(pid, []) if t0 <= x[0] <= days(t0, 7))
        assert conv == (1 if in_win else 0)
        assert amt0 == (in_win[0][2] if in_win else 0)
        assert bonus0 == (in_win[0][3] if in_win else 0)
        ggr = sum(g for d, g in play.get(pid, []) if t0 <= d <= days(t0, 14))
        assert close(ggr0, ggr, 1e-6)
        un = mail[pid]
        assert unsub0 == (1 if (un is not None and un <= days(t0, 7)) else 0)
        if variant == "A":
            assert bonus0 == 0
        checked += 1
        converted += conv
        late += (not conv) and any(x[0] > days(t0, 7) for x in deps.get(pid, []))
    assert checked == con.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    assert converted > 0 and late > 0          # the window rule is really exercised


def test_bonus_rules():
    con = experiment()
    assert con.execute("""SELECT COUNT(*) FROM deposits d JOIN assignments a USING (player_id)
                          WHERE a.variant = 'A' AND d.bonus_amount > 0""").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM deposits WHERE bonus_amount > ? OR bonus_amount > amount",
                       (ex.BONUS_CAP,)).fetchone()[0] == 0
    # offer expires after 7 days: a late deposit in arm B gets no bonus
    assert con.execute("""SELECT COUNT(*) FROM deposits d JOIN assignments a USING (player_id)
                          WHERE d.deposited_at > date(a.t0, '+7 days') AND d.bonus_amount > 0""").fetchone()[0] == 0


def test_all_windows_are_complete_at_the_snapshot():
    con = experiment()
    last = con.execute("SELECT MAX(t0) FROM assignments").fetchone()[0]
    assert datetime.date.fromisoformat(last) + datetime.timedelta(days=14) <= ex.ANALYSIS_DATE
    assert con.execute("SELECT COUNT(*) FROM gaming_results WHERE played_at > ?",
                       (ex.ANALYSIS_DATE.isoformat(),)).fetchone()[0] == 0


def test_full_analysis_runs_and_is_reproducible():
    con = experiment()
    reports = ex.run_reports(con)
    r1 = ex.analyse(con, reports, n_boot=200, n_sims=50)
    r2 = ex.analyse(con, reports, n_boot=200, n_sims=50)
    assert r1["primary"] == r2["primary"] and r1["net"] == r2["net"] and r1["verdict"] == r2["verdict"]
    assert r1["srm"]["ok"] and r1["required_n"] == 3841
    assert r1["verdict"][0] in ("SHIP B", "DO NOT SHIP B", "INCONCLUSIVE")
    flow = [row[2] for row in reports["eligibility_flow"][1]]
    assert flow == sorted(flow, reverse=True) and reports["eligibility_flow"][1][0][3] == 0


# -------------------------------------------------------------------- guards
def fake(srm_ok=True, p=0.01, diff=0.02, net_lo=-1.0, net_hi=1.0, u_p=0.5, u_diff=0.0):
    return {"srm": {"ok": srm_ok}, "primary": {"p_value": p, "diff": diff},
            "net": {"ci_low": net_lo, "ci_high": net_hi}, "unsub_test": {"p_value": u_p, "diff": u_diff}}


def test_decision_rule():
    assert ex.decide(fake(srm_ok=False))[0] == "INVALID"
    assert ex.decide(fake(p=0.2))[0] == "DO NOT SHIP B"                       # primary not significant
    assert ex.decide(fake(p=0.001, diff=-0.02))[0] == "DO NOT SHIP B"         # significant but worse
    assert ex.decide(fake(net_lo=-3, net_hi=-1))[0] == "DO NOT SHIP B"        # value destroyed
    assert ex.decide(fake(u_p=0.001, u_diff=0.01))[0] == "DO NOT SHIP B"      # guardrail breached
    assert ex.decide(fake(net_lo=1, net_hi=3))[0] == "SHIP B"
    assert ex.decide(fake(net_lo=-1, net_hi=3))[0] == "INCONCLUSIVE"


def strip_comments(sql):
    return re.sub(r"--[^\n]*", "", sql)


def test_sql_files_use_the_intended_techniques():
    assign = strip_comments((ex.SQL_DIR / "01_assign.sql").read_text(encoding="utf-8"))
    metrics = strip_comments((ex.SQL_DIR / "02_player_metrics.sql").read_text(encoding="utf-8"))
    reports = strip_comments((ex.SQL_DIR / "03_reports.sql").read_text(encoding="utf-8"))
    assert "ab_hash(" in assign and ex.PLAN["name"] in assign        # salt in SQL equals the plan name
    assert "ROW_NUMBER()" in metrics and "LEFT JOIN" in metrics and "date(a.t0" in metrics
    assert "LAG(" in reports and "UNION ALL" in reports and "CASE WHEN" in reports


def test_no_em_dash_anywhere_in_the_project():
    dash = chr(0x2014)
    for path in HERE.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".sql", ".md", ".csv", ".svg", ".txt"):
            assert dash not in path.read_text(encoding="utf-8"), "em dash in %s" % path


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("ok   %s" % name)
    print("\n%d tests passed (SQLite %s)" % (len(tests), sqlite3.sqlite_version))


if __name__ == "__main__":
    main()

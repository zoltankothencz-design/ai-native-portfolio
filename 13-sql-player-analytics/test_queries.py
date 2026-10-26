"""
Tests for the SQL queries. Plain asserts, run with:  python test_queries.py
Each test re-computes results in pure Python from the same table rows and compares.
"""

import datetime
import pathlib
import re
import sqlite3
import sys

if sqlite3.sqlite_version_info < (3, 25, 0):
    sys.exit("FAIL: SQLite %s is too old, window functions need 3.25 or newer."
             % sqlite3.sqlite_version)

import run_analytics as ra

HERE = pathlib.Path(__file__).resolve().parent
TOLERANCE = 0.0051   # SQL output is rounded to 2 decimals


def make_db():
    con = sqlite3.connect(":memory:")
    ra.build_database(con)
    return con


def test_funnel_shape(con, results):
    headers, rows = results["funnel_by_channel"]
    ix = {h: i for i, h in enumerate(headers)}
    n_players = con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    channels = 0
    for r in rows:
        steps = [r[ix[c]] for c in ("registered", "kyc_passed", "ftd", "second_deposit")]
        assert steps == sorted(steps, reverse=True), "funnel not non-increasing: %r" % (r,)
        if r[ix["channel"]] != "ALL":
            channels += 1
    total = [r for r in rows if r[ix["channel"]] == "ALL"][0]
    assert total[ix["registered"]] == n_players, "ALL row != number of players"
    assert sum(r[ix["registered"]] for r in rows if r[ix["channel"]] != "ALL") == n_players
    assert channels == len(ra.CHANNELS)


def test_funnel_matches_python(con, results):
    players = con.execute("SELECT player_id, channel, kyc_verified_at FROM players").fetchall()
    dep_count = {}
    for (pid,) in con.execute("SELECT player_id FROM deposits"):
        dep_count[pid] = dep_count.get(pid, 0) + 1
    expected = {}
    reactivation = {}
    for pid, channel, kyc in players:
        e = expected.setdefault(channel, [0, 0, 0, 0])
        e[0] += 1
        if kyc is not None:
            e[1] += 1
            if dep_count.get(pid, 0) >= 1:
                e[2] += 1
            else:
                reactivation[channel] = reactivation.get(channel, 0) + 1
            if dep_count.get(pid, 0) >= 2:
                e[3] += 1
    headers, rows = results["funnel_by_channel"]
    got = {r[0]: list(r[1:5]) for r in rows if r[0] != "ALL"}
    assert got == expected, "funnel mismatch:\nSQL    %r\nPython %r" % (got, expected)
    # percentages for one channel, recomputed
    for r in rows:
        if r[0] == "ALL":
            continue
        reg, kyc, ftd, sec = expected[r[0]]
        assert abs(r[headers.index("reg_to_ftd_pct")] - 100.0 * ftd / reg) <= 0.051
        assert abs(r[headers.index("kyc_to_ftd_pct")] - 100.0 * ftd / kyc) <= 0.051
    # anti-join result
    h2, rows2 = results["kyc_no_deposit_by_channel"]
    got2 = {r[0]: r[2] for r in rows2}
    assert got2 == reactivation, "reactivation mismatch: %r vs %r" % (got2, reactivation)


def month_index(iso):
    return int(iso[:4]) * 12 + int(iso[5:7])


def test_cohort_ltv_matches_python(con, results):
    reg = {pid: m for pid, m in con.execute("SELECT player_id, registered_at FROM players")}
    size, ggr = {}, {}
    for d in reg.values():
        size[d[:7]] = size.get(d[:7], 0) + 1
    for pid, played, stake, win in con.execute(
            "SELECT player_id, played_at, stake, win FROM gaming_results"):
        cohort = reg[pid][:7]
        offset = month_index(played) - month_index(reg[pid])
        ggr[(cohort, offset)] = ggr.get((cohort, offset), 0.0) + (stake - win)
    headers, rows = results["cohort_ltv"]
    ix = {h: i for i, h in enumerate(headers)}
    assert len(rows) == len(size) * 6
    for cohort in size:
        cumulative = 0.0
        for offset in range(6):
            cumulative += ggr.get((cohort, offset), 0.0)
            expected = cumulative / size[cohort]
            row = [r for r in rows if r[ix["cohort_month"]] == cohort
                   and r[ix["month_offset"]] == offset][0]
            assert row[ix["cohort_size"]] == size[cohort]
            assert abs(row[ix["cumulative_ggr_per_player"]] - expected) <= TOLERANCE, \
                "LTV mismatch %s M+%d: %r vs %r" % (
                    cohort, offset, row[ix["cumulative_ggr_per_player"]], expected)


def test_running_total_last_value(con, results):
    headers, rows = results["running_deposit_total"]
    last = {}
    for pid, seq, _date, _amount, running in rows:
        assert seq == last.get(pid, (0, 0.0))[0] + 1, "deposit_seq not consecutive"
        last[pid] = (seq, running)
    totals = {pid: total for pid, total in con.execute(
        "SELECT player_id, SUM(amount) FROM deposits GROUP BY player_id")}
    assert set(last) == set(totals)
    for pid, total in totals.items():
        assert abs(last[pid][1] - total) < 1e-6, "running total != total for player %d" % pid


def test_other_window_queries(con, results):
    # deciles: all ranked players are covered, sizes differ by at most one, shares sum to 100
    _, rows = results["ggr_deciles"]
    n = con.execute("SELECT COUNT(DISTINCT player_id) FROM gaming_results").fetchone()[0]
    assert sum(r[1] for r in rows) == n and len(rows) == 10
    assert max(r[1] for r in rows) - min(r[1] for r in rows) <= 1
    assert abs(sum(r[4] for r in rows) - 100.0) <= 0.2
    # top 3: exactly three per cohort, GGR non-increasing
    _, rows = results["top3_players_per_cohort"]
    by_cohort = {}
    for cohort, rank, _pid, _ch, value in rows:
        by_cohort.setdefault(cohort, []).append((rank, value))
    for cohort, items in by_cohort.items():
        assert [r for r, _ in items] == [1, 2, 3], cohort
        vals = [v for _, v in items]
        assert vals == sorted(vals, reverse=True), cohort
    # LAG gaps: python recompute of the average gap per channel
    ch = {pid: c for pid, c in con.execute("SELECT player_id, channel FROM players")}
    per_player = {}
    for did, pid, d in con.execute("SELECT deposit_id, player_id, deposited_at FROM deposits"):
        per_player.setdefault(pid, []).append((d, did))
    gaps = {}
    for pid, items in per_player.items():
        items.sort()
        dates = [datetime.date.fromisoformat(d) for d, _ in items]
        for a, b in zip(dates, dates[1:]):
            gaps.setdefault(ch[pid], []).append((b - a).days)
    _, rows = results["deposit_gap_by_channel"]
    for channel, n_gaps, avg in rows:
        vals = gaps[channel]
        assert n_gaps == len(vals)
        assert abs(avg - sum(vals) / len(vals)) <= 0.051


def strip_sql_comments(sql):
    return "\n".join(line.split("--")[0] for line in sql.splitlines())


def test_readme_claims_match_sql():
    techniques = ["LEFT JOIN", "CASE WHEN", "LAG", "ROW_NUMBER", "NTILE", "OVER", "PARTITION BY"]
    sql = " ".join(strip_sql_comments(p.read_text(encoding="utf-8")).upper()
                   for p in sorted((HERE / "queries").glob("*.sql")))
    sql = re.sub(r"\s+", " ", sql)
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    for t in techniques:
        assert re.search(r"\b" + t.replace(" ", r"\s+") + r"\b", sql), \
            "technique %r is claimed but not used in the .sql files" % t
        assert "`%s" % t in readme, "technique %r missing from README key techniques" % t


def test_no_em_dash():
    dash = chr(0x2014)
    for p in HERE.rglob("*"):
        if p.is_file() and p.suffix in {".py", ".sql", ".md", ".csv", ".txt"}:
            assert dash not in p.read_text(encoding="utf-8"), "em dash in %s" % p


def main():
    con = make_db()
    results = ra.run_all(con)
    tests = [
        (test_funnel_shape, True), (test_funnel_matches_python, True),
        (test_cohort_ltv_matches_python, True), (test_running_total_last_value, True),
        (test_other_window_queries, True), (test_readme_claims_match_sql, False),
        (test_no_em_dash, False),
    ]
    for fn, needs_db in tests:
        fn(con, results) if needs_db else fn()
        print("PASS", fn.__name__)
    print("All %d tests passed (SQLite %s, Python %s)."
          % (len(tests), sqlite3.sqlite_version, sys.version.split()[0]))


if __name__ == "__main__":
    main()

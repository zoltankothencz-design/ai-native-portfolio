"""
Player Analytics (CRM + affiliate reporting) on SQLite
------------------------------------------------------
Seeds a deterministic synthetic database (players, deposits, gaming_results),
runs the three query files in queries/ and writes CSV + Markdown outputs to output/.
Stdlib only, Python 3.9+, SQLite 3.25+ (window functions).
"""

import csv
import datetime
import pathlib
import random
import re
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
DB_PATH = HERE / "player_analytics.db"
QUERY_DIR = HERE / "queries"
OUT_DIR = HERE / "output"

SEED = 42
N_PLAYERS = 2000
COHORT_MONTHS = 6                     # Jan-Jun 2024
DATA_CUTOFF = datetime.date(2024, 12, 31)
COUNTRIES = ["DE", "SE", "FI", "NO", "CA", "BR"]

# Fictional channels. kyc / ftd / second are the step conversion probabilities.
CHANNELS = {
    "affiliate_a": {"weight": 0.25, "kyc": 0.78, "ftd": 0.58, "second": 0.56},
    "affiliate_b": {"weight": 0.20, "kyc": 0.62, "ftd": 0.41, "second": 0.41},
    "affiliate_c": {"weight": 0.15, "kyc": 0.70, "ftd": 0.50, "second": 0.48},
    "organic":     {"weight": 0.25, "kyc": 0.72, "ftd": 0.54, "second": 0.50},
    "crm_email":   {"weight": 0.15, "kyc": 0.80, "ftd": 0.60, "second": 0.58},
}

SCHEMA = """
DROP TABLE IF EXISTS gaming_results;
DROP TABLE IF EXISTS deposits;
DROP TABLE IF EXISTS players;

CREATE TABLE players (
    player_id       INTEGER PRIMARY KEY,
    registered_at   TEXT NOT NULL,      -- ISO date YYYY-MM-DD
    channel         TEXT NOT NULL,
    country         TEXT NOT NULL,
    kyc_verified_at TEXT                -- NULL = never passed KYC
);

CREATE TABLE deposits (
    deposit_id   INTEGER PRIMARY KEY,
    player_id    INTEGER NOT NULL REFERENCES players(player_id),
    deposited_at TEXT NOT NULL,
    amount       REAL NOT NULL
);

CREATE TABLE gaming_results (
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    played_at TEXT NOT NULL,
    stake     REAL NOT NULL,
    win       REAL NOT NULL
);

CREATE INDEX idx_deposits_player ON deposits(player_id);
CREATE INDEX idx_gaming_player ON gaming_results(player_id);
"""


def check_sqlite():
    if sqlite3.sqlite_version_info < (3, 25, 0):
        raise SystemExit(
            "SQLite %s is too old: window functions need 3.25 or newer."
            % sqlite3.sqlite_version
        )


def generate_data(seed=SEED):
    """Return (players, deposits, gaming_results) as lists of tuples."""
    rnd = random.Random(seed)
    names = list(CHANNELS)
    weights = [CHANNELS[n]["weight"] for n in names]
    day = datetime.timedelta
    players, deposits, gaming = [], [], []
    deposit_id = 1
    for pid in range(1, N_PLAYERS + 1):
        month = (pid - 1) * COHORT_MONTHS // N_PLAYERS + 1
        registered = datetime.date(2024, month, rnd.randint(1, 28))
        channel = rnd.choices(names, weights)[0]
        cfg = CHANNELS[channel]
        country = rnd.choice(COUNTRIES)
        kyc = None
        if rnd.random() < cfg["kyc"]:
            kyc = registered + day(days=rnd.randint(0, 3))
        players.append((pid, registered.isoformat(), channel, country,
                        kyc.isoformat() if kyc else None))
        if kyc is None or rnd.random() >= cfg["ftd"]:
            continue
        dates = [kyc + day(days=rnd.randint(0, 10))]
        if rnd.random() < cfg["second"]:
            dates.append(dates[-1] + day(days=rnd.randint(1, 30)))
            while len(dates) < 8 and rnd.random() < 0.6:
                dates.append(dates[-1] + day(days=rnd.randint(1, 25)))
        scale = rnd.choice([20, 30, 50, 100, 200])
        for d in dates:
            if d > DATA_CUTOFF:
                break
            amount = scale * rnd.choice([1, 1, 1, 2, 3])
            deposits.append((deposit_id, pid, d.isoformat(), float(amount)))
            deposit_id += 1
            # a few gaming sessions after each deposit
            for _ in range(rnd.randint(1, 5)):
                played = d + day(days=rnd.randint(0, 20))
                if played > DATA_CUTOFF:
                    continue
                stake = round(amount * rnd.uniform(0.3, 2.5), 2)
                win = round(stake * max(0.0, rnd.gauss(0.90, 0.5)), 2)
                gaming.append((pid, played.isoformat(), stake, win))
    return players, deposits, gaming


def build_database(con, seed=SEED):
    con.executescript(SCHEMA)
    players, deposits, gaming = generate_data(seed)
    con.executemany("INSERT INTO players VALUES (?,?,?,?,?)", players)
    con.executemany("INSERT INTO deposits VALUES (?,?,?,?)", deposits)
    con.executemany("INSERT INTO gaming_results VALUES (?,?,?,?)", gaming)
    con.commit()
    return len(players), len(deposits), len(gaming)


def load_queries(path):
    """Split a .sql file on '-- @query: name' lines. Returns [(name, sql), ...]."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^-- @query: (\w+)[ \t]*$", text, flags=re.MULTILINE)
    return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def run_query(con, sql):
    cur = con.execute(sql)
    headers = [c[0] for c in cur.description]
    return headers, cur.fetchall()


def run_all(con):
    """Run every query file. Returns {query_name: (headers, rows)}."""
    results = {}
    for path in sorted(QUERY_DIR.glob("*.sql")):
        for name, sql in load_queries(path):
            results[name] = run_query(con, sql)
    return results


def md_table(headers, rows):
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = lambda cells: "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    return "\n".join([line(headers), sep] + [line(r) for r in rows])


def write_csv(name, headers, rows):
    with open(OUT_DIR / (name + ".csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def ltv_pivot(headers, rows):
    ix = {h: i for i, h in enumerate(headers)}
    sizes, cells = {}, {}
    for r in rows:
        sizes[r[ix["cohort_month"]]] = r[ix["cohort_size"]]
        cells[(r[ix["cohort_month"]], r[ix["month_offset"]])] = r[ix["cumulative_ggr_per_player"]]
    offsets = sorted({k[1] for k in cells})
    head = ["Cohort", "Size"] + ["M+%d" % o for o in offsets]
    body = [[c, sizes[c]] + ["%.2f" % cells[(c, o)] for o in offsets] for c in sorted(sizes)]
    return head, body


def write_reports(results):
    OUT_DIR.mkdir(exist_ok=True)
    for name, (headers, rows) in results.items():
        write_csv(name, headers, rows)

    # the per-deposit running total is long: keep one sample player in the Markdown
    h, rows = results["running_deposit_total"]
    by_player = {}
    for r in rows:
        by_player.setdefault(r[0], []).append(r)
    sample_pid = next(p for p in sorted(by_player) if len(by_player[p]) >= 4)

    md = ["# Player Analytics Report", "",
          "Synthetic data. GGR = stake - win (gross: no bonus cost, taxes or fees, so not NGR).", ""]
    md += ["## 1. Funnel by channel", "", md_table(*results["funnel_by_channel"]), ""]
    md += ["## 1b. KYC passed, never deposited (CRM reactivation list)", "",
           md_table(*results["kyc_no_deposit_by_channel"]), ""]
    md += ["## 2a. Average days between consecutive deposits", "",
           md_table(*results["deposit_gap_by_channel"]), ""]
    md += ["## 2b. Top 3 players per cohort by GGR", "",
           md_table(*results["top3_players_per_cohort"]), ""]
    md += ["## 2c. GGR deciles (1 = top 10 percent of players)", "",
           md_table(*results["ggr_deciles"]), ""]
    md += ["## 2d. Running deposit total (sample: player %d)" % sample_pid, "",
           md_table(h, by_player[sample_pid]), ""]
    lh, lrows = results["cohort_ltv"]
    md += ["## 3. Cohort LTV: cumulative GGR per player by month since registration", "",
           md_table(*ltv_pivot(lh, lrows)), ""]
    md += ["_Generated from synthetic data. No real player data._", ""]
    (OUT_DIR / "player_analytics_report.md").write_text("\n".join(md), encoding="utf-8")


def main():
    check_sqlite()
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    n_p, n_d, n_g = build_database(con)
    print("Seeded %d players, %d deposits, %d gaming rows (SQLite %s, Python %s)."
          % (n_p, n_d, n_g, sqlite3.sqlite_version, sys.version.split()[0]))
    results = run_all(con)
    write_reports(results)
    con.close()
    print("Wrote %d CSV files and player_analytics_report.md to %s" % (len(results), OUT_DIR))
    print()
    print(md_table(*results["funnel_by_channel"]))


if __name__ == "__main__":
    main()

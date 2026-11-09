"""
A/B test demo: reactivation bonus email (iGaming CRM)
-----------------------------------------------------
Runs a complete experiment on synthetic data, in the order a real one runs:

  1. PLAN      hypothesis, metrics, sample size and decision rule fixed BEFORE any outcome
  2. ASSIGN    eligibility filter + hash-based 50/50 split, in SQL (sql/01_assign.sql)
  3. CHECK     sample ratio mismatch (SRM) and covariate balance
  4. OBSERVE   simulated player behaviour after the email (stands in for the real world)
  5. MEASURE   per-player metrics in fixed windows, in SQL (sql/02, sql/03)
  6. ANALYSE   z-test, bootstrap intervals, guardrail, robustness check, verdict
  7. REPORT    output/experiment_report.md, CSV files and an SVG summary

Stdlib only, Python 3.9+, SQLite 3.25+. Deterministic (fixed seed).
"""

import csv
import datetime
import hashlib
import pathlib
import random
import re
import sqlite3
import sys

import ab_stats as st

HERE = pathlib.Path(__file__).resolve().parent
DB_PATH = HERE / "ab_test.db"
SQL_DIR = HERE / "sql"
OUT_DIR = HERE / "output"

SEED = 42

# ------------------------------------------------------------------ 1. THE PLAN
# Written down before the data exists. The verdict at the end applies exactly these rules.
PLAN = {
    "name": "bonus_email_2024_07",
    "hypothesis": ("Adding a 100% deposit match (up to 50) to the first-deposit reminder email "
                   "raises the share of players who make a first deposit within 7 days."),
    "primary_metric": "first deposit within 7 days of the email (conversion, per eligible player)",
    "secondary_metrics": ["first-deposit amount per eligible player",
                          "net value per eligible player = GGR (14 days) - bonus cost"],
    "guardrail_metric": "unsubscribe within 7 days (must not rise significantly)",
    "unit": "player (one email per player, assigned once)",
    "baseline_rate": 0.10,      # from earlier campaigns (planning assumption)
    "mde_abs": 0.02,            # smallest lift worth acting on: +2.0 percentage points
    "alpha": 0.05,
    "power": 0.80,
    "split": [0.5, 0.5],
    "srm_threshold": 0.001,
    "n_secondary_tests": 3,     # 2 secondary metrics + 1 guardrail -> Bonferroni
    "n_boot": 2000,
}
PLAN["alpha_secondary"] = PLAN["alpha"] / PLAN["n_secondary_tests"]

# ------------------------------------------------- synthetic world (the "truth")
N_CANDIDATES = 11000
ENROL_START = datetime.date(2024, 7, 1)
ENROL_DAYS = 14
ANALYSIS_DATE = datetime.date(2024, 8, 4)     # last enrolment (Jul 14) + 14 days + slack
COUNTRIES = ["DE", "SE", "FI", "NO", "CA", "BR"]
# base_rate = probability of a first deposit within 7 days WITHOUT the bonus
CHANNELS = {
    "affiliate_a": {"weight": 0.25, "base_rate": 0.09},
    "affiliate_b": {"weight": 0.20, "base_rate": 0.07},
    "affiliate_c": {"weight": 0.15, "base_rate": 0.08},
    "organic":     {"weight": 0.25, "base_rate": 0.10},
    "crm_email":   {"weight": 0.15, "base_rate": 0.15},
}
P_ALREADY_DEPOSITED = 0.10
P_RG_FLAG = 0.03
P_EMAIL_CONSENT = 0.85
TRUE_LIFT_MULT = 1.25          # the bonus multiplies every player's conversion chance by this
LATE_RATE = 0.03               # non-converters who deposit on day 8-20 (outside the window)
BONUS_CAP = 50.0
UNSUB_RATE = {"A": 0.009, "B": 0.011}
LATE_UNSUB_RATE = 0.004

SCHEMA = """
DROP TABLE IF EXISTS gaming_results;
DROP TABLE IF EXISTS deposits;
DROP TABLE IF EXISTS email_events;
DROP TABLE IF EXISTS candidates;

CREATE TABLE candidates (
    player_id        INTEGER PRIMARY KEY,
    channel          TEXT NOT NULL,
    country          TEXT NOT NULL,
    registered_at    TEXT NOT NULL,
    kyc_verified_at  TEXT NOT NULL,
    entered_at       TEXT NOT NULL,     -- KYC date + 3 days: the day the player joins the audience
    deposits_before  INTEGER NOT NULL,
    rg_flag          INTEGER NOT NULL,  -- 1 = responsible-gaming flag
    email_consent    INTEGER NOT NULL
);

CREATE TABLE email_events (
    player_id       INTEGER NOT NULL,
    sent_at         TEXT NOT NULL,
    unsubscribed_at TEXT
);

CREATE TABLE deposits (
    deposit_id   INTEGER PRIMARY KEY,
    player_id    INTEGER NOT NULL,
    deposited_at TEXT NOT NULL,
    amount       REAL NOT NULL,
    bonus_amount REAL NOT NULL
);

CREATE TABLE gaming_results (
    player_id INTEGER NOT NULL,
    played_at TEXT NOT NULL,
    stake     REAL NOT NULL,
    win       REAL NOT NULL
);
CREATE INDEX idx_deposits_player ON deposits(player_id);
CREATE INDEX idx_gaming_player ON gaming_results(player_id);
CREATE INDEX idx_email_player ON email_events(player_id);
"""


def check_sqlite():
    if sqlite3.sqlite_version_info < (3, 25, 0):
        raise SystemExit("SQLite %s is too old: window functions need 3.25 or newer."
                         % sqlite3.sqlite_version)


def ab_hash(player_id, salt):
    """Deterministic 56-bit hash of player id + experiment salt (fits SQLite INTEGER)."""
    digest = hashlib.sha256(("%s:%s" % (salt, player_id)).encode("utf-8")).digest()
    return int.from_bytes(digest[:7], "big")


# --------------------------------------------------------- data generation
def generate_candidates(seed=SEED):
    rnd = random.Random(seed)
    names = list(CHANNELS)
    weights = [CHANNELS[n]["weight"] for n in names]
    day = datetime.timedelta
    rows = []
    for pid in range(1, N_CANDIDATES + 1):
        channel = rnd.choices(names, weights)[0]
        country = rnd.choice(COUNTRIES)
        entered = ENROL_START + day(days=rnd.randint(0, ENROL_DAYS - 1))
        kyc = entered - day(days=3)
        registered = kyc - day(days=rnd.randint(0, 3))
        rows.append((pid, channel, country, registered.isoformat(), kyc.isoformat(),
                     entered.isoformat(),
                     0 if rnd.random() >= P_ALREADY_DEPOSITED else 1,
                     1 if rnd.random() < P_RG_FLAG else 0,
                     1 if rnd.random() < P_EMAIL_CONSENT else 0))
    return rows


def simulate_outcomes(con, seed=SEED):
    """What the players do after the email. This stands in for the real world: it reads
    the assignments the SQL step made and writes events. Each player has an own random
    stream (seeded by id), so the result does not depend on iteration order."""
    day = datetime.timedelta
    people = con.execute("SELECT player_id, channel, variant, t0 FROM assignments "
                         "ORDER BY player_id").fetchall()
    deposits, gaming, emails = [], [], []
    dep_id = 1
    for pid, channel, variant, t0_iso in people:
        rnd = random.Random(seed * 1000003 + pid)
        t0 = datetime.date.fromisoformat(t0_iso)
        p_base = CHANNELS[channel]["base_rate"]
        p_arm = p_base * (TRUE_LIFT_MULT if variant == "B" else 1.0)
        u = rnd.random()
        converted = u < p_arm
        induced = converted and u >= p_base      # only converts BECAUSE of the bonus
        dep_date = None
        in_window = False
        if converted:
            dep_date = t0 + day(days=min(7, int(rnd.expovariate(0.6))))
            in_window = True
        elif rnd.random() < LATE_RATE:
            dep_date = t0 + day(days=rnd.randint(8, 20))
        if dep_date is not None and dep_date <= ANALYSIS_DATE:
            if induced:      # marginal players deposit less
                amount = rnd.choice([20, 30, 50]) * rnd.choice([1, 1, 2])
            else:
                amount = rnd.choice([20, 30, 50, 100, 200]) * rnd.choice([1, 1, 1, 2, 3])
            amount = float(amount)
            bonus = min(amount, BONUS_CAP) if (variant == "B" and in_window) else 0.0
            deposits.append((dep_id, pid, dep_date.isoformat(), amount, bonus))
            dep_id += 1
            for _ in range(rnd.randint(1, 5)):
                played = dep_date + day(days=rnd.randint(0, 13))
                if played > ANALYSIS_DATE:
                    continue
                stake = round((amount + bonus) * rnd.uniform(0.3, 2.5), 2)
                win = round(stake * max(0.0, rnd.gauss(0.90, 0.5)), 2)
                gaming.append((pid, played.isoformat(), stake, win))
        unsub = None
        if rnd.random() < UNSUB_RATE[variant]:
            unsub = t0 + day(days=rnd.randint(0, 6))
        elif rnd.random() < LATE_UNSUB_RATE:
            unsub = t0 + day(days=rnd.randint(8, 20))
        emails.append((pid, t0_iso, unsub.isoformat() if unsub else None))
    con.executemany("INSERT INTO deposits VALUES (?,?,?,?,?)", deposits)
    con.executemany("INSERT INTO gaming_results VALUES (?,?,?,?)", gaming)
    con.executemany("INSERT INTO email_events VALUES (?,?,?)", emails)
    con.commit()
    return len(deposits), len(gaming), len(emails)


# ------------------------------------------------------------- SQL plumbing
def load_queries(path):
    """Split a .sql file on '-- @query: name' lines. Returns [(name, sql), ...]."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^-- @query: (\w+)[ \t]*$", text, flags=re.MULTILINE)
    return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def run_script(con, name):
    con.executescript((SQL_DIR / name).read_text(encoding="utf-8"))
    con.commit()


def run_reports(con):
    results = {}
    for name, sql in load_queries(SQL_DIR / "03_reports.sql"):
        cur = con.execute(sql)
        results[name] = ([c[0] for c in cur.description], cur.fetchall())
    return results


def new_connection(path):
    con = sqlite3.connect(str(path))
    con.create_function("ab_hash", 2, ab_hash, deterministic=True)
    return con


def build_experiment(con, seed=SEED):
    """Steps 2 to 5: seed candidates, assign in SQL, simulate outcomes, measure in SQL."""
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?)", generate_candidates(seed))
    con.commit()
    run_script(con, "01_assign.sql")
    counts = simulate_outcomes(con, seed)
    run_script(con, "02_player_metrics.sql")
    return counts


# ------------------------------------------------------------------ analysis
def per_arm_values(con):
    by = {"A": [], "B": []}
    for row in con.execute("SELECT variant, converted_7d, first_deposit_amount, bonus_cost, "
                           "ggr_14d, unsub_7d FROM player_metrics ORDER BY player_id"):
        by[row[0]].append(row[1:])
    return by


def analyse(con, reports, n_boot=None, n_sims=1000):
    n_boot = n_boot or PLAN["n_boot"]
    by = per_arm_values(con)
    n = {v: len(by[v]) for v in by}
    conv = {v: sum(r[0] for r in by[v]) for v in by}
    unsub = {v: sum(r[4] for r in by[v]) for v in by}
    deposit = {v: [r[1] for r in by[v]] for v in by}
    net = {v: [r[3] - r[2] for r in by[v]] for v in by}
    ci_sec = 1.0 - PLAN["alpha_secondary"]

    out = {"n": n, "conv": conv, "unsub": unsub}
    base, mde = PLAN["baseline_rate"], PLAN["mde_abs"]
    out["required_n"] = st.sample_size_per_arm(base, base + mde, PLAN["alpha"], PLAN["power"])
    out["power_at_n"] = st.power_two_proportions(base, base + mde, min(n.values()), PLAN["alpha"])
    out["sample_size_table"] = [
        (d, st.sample_size_per_arm(base, base + d, PLAN["alpha"], PLAN["power"]))
        for d in (0.010, 0.015, 0.020, 0.025, 0.030)]

    out["srm"] = st.srm_check([n["A"], n["B"]], PLAN["split"], PLAN["srm_threshold"])
    bal = {}
    for key in ("balance_by_channel", "balance_by_country"):
        table = [[r[1], r[2]] for r in reports[key][1]]
        bal[key] = st.chi_square_independence(table)
    out["balance"] = bal

    out["primary"] = st.two_proportion_test(conv["A"], n["A"], conv["B"], n["B"], PLAN["alpha"])
    out["deposit"] = st.bootstrap_mean_diff(deposit["A"], deposit["B"], n_boot, ci_sec, seed=11)
    out["net"] = st.bootstrap_mean_diff(net["A"], net["B"], n_boot, ci_sec, seed=12)
    out["unsub_test"] = st.two_proportion_test(unsub["A"], n["A"], unsub["B"], n["B"],
                                               PLAN["alpha_secondary"])
    # robustness: cap the top and bottom 1% of net value (pooled), rerun
    pooled, lo, hi = st.winsorize(net["A"] + net["B"], 0.01, 0.99)
    wa, wb = pooled[:n["A"]], pooled[n["A"]:]
    out["net_wins"] = st.bootstrap_mean_diff(wa, wb, n_boot, ci_sec, seed=13)
    out["net_wins_caps"] = (lo, hi)
    out["bonus_pp"] = {v: sum(r[2] for r in by[v]) / float(n[v]) for v in by}
    out["ggr_pp"] = {v: sum(r[3] for r in by[v]) / float(n[v]) for v in by}
    out["peeking"] = st.peeking_simulation(p=base, n_per_arm=out["required_n"],
                                           n_looks=14, n_sims=n_sims)
    out["verdict"] = decide(out)
    return out


def decide(res):
    """The pre-registered decision rule, applied mechanically."""
    prim, net, ung = res["primary"], res["net"], res["unsub_test"]
    if not res["srm"]["ok"]:
        return ("INVALID", "Sample ratio mismatch: the assignment is broken, so no result can be trusted.")
    if ung["p_value"] < PLAN["alpha_secondary"] and ung["diff"] > 0:
        return ("DO NOT SHIP B", "The unsubscribe guardrail was breached.")
    if not (prim["p_value"] < PLAN["alpha"] and prim["diff"] > 0):
        return ("DO NOT SHIP B", "The primary metric did not show a significant lift.")
    if net["ci_high"] < 0:
        return ("DO NOT SHIP B", "Conversion rose, but net value per player (14-day GGR minus the bonus at "
                                 "face value) is significantly lower in B than in A.")
    if net["ci_low"] > 0:
        return ("SHIP B", "Conversion rose significantly and net value per player is significantly positive.")
    return ("INCONCLUSIVE", "Conversion rose significantly, but the 14-day net value difference is not "
                            "distinguishable from zero. Extend the value window or test a smaller bonus.")


# -------------------------------------------------------------------- output
def md_table(headers, rows):
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = lambda cells: "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    return "\n".join([line(headers), sep] + [line(r) for r in rows])


def write_csv(name, headers, rows):
    with open(str(OUT_DIR / (name + ".csv")), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def pct(x, digits=2):
    return "%.*f%%" % (digits, 100.0 * x)


def pp(x, digits=2):
    return "%+.*f pp" % (digits, 100.0 * x)


def fmt_p(p):
    return "<0.0001" if p < 0.0001 else "%.4f" % p


def write_svg(res):
    """Two small panels: conversion per arm with 95% CI, and the net-value difference."""
    prim, net = res["primary"], res["net"]
    w, h = 720, 250
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
             'font-family="Arial, sans-serif" font-size="13">' % (w, h, w, h),
             '<rect width="100%" height="100%" fill="#ffffff"/>']

    def scale(v, lo, hi, x0, x1):
        return x0 + (v - lo) / (hi - lo) * (x1 - x0)

    # panel 1: conversion by arm
    parts.append('<text x="20" y="28" font-weight="bold">Conversion within 7 days (95% CI)</text>')
    zc = st.normal_ppf(1 - PLAN["alpha"] / 2)
    arms = []
    for label, p, n_arm, color in (("A control", prim["p_a"], res["n"]["A"], "#6b7280"),
                                   ("B bonus", prim["p_b"], res["n"]["B"], "#2563eb")):
        se = (p * (1 - p) / n_arm) ** 0.5
        arms.append((label, p, p - zc * se, p + zc * se, color))
    lo = min(a[2] for a in arms) - 0.01
    hi = max(a[3] for a in arms) + 0.01
    for i, (label, p, a, b, color) in enumerate(arms):
        y = 80 + i * 60
        parts.append('<text x="20" y="%d">%s</text>' % (y + 4, label))
        parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="3"/>'
                     % (scale(a, lo, hi, 110, 330), y, scale(b, lo, hi, 110, 330), y, color))
        parts.append('<circle cx="%.1f" cy="%d" r="6" fill="%s"/>' % (scale(p, lo, hi, 110, 330), y, color))
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>'
                     % (scale(p, lo, hi, 110, 330), y - 12, pct(p)))
    parts.append('<text x="20" y="%d" fill="#444">Lift %s (95%% CI %s to %s), p = %s</text>'
                 % (h - 18, pp(prim["diff"]), pp(prim["ci_low"]), pp(prim["ci_high"]), fmt_p(prim["p_value"])))

    # panel 2: net value difference
    parts.append('<text x="400" y="28" font-weight="bold">Net value per player, B minus A (%.1f%% CI)</text>'
                 % (100 * net["ci_level"]))
    lo2 = min(net["ci_low"], 0.0) - 0.5
    hi2 = max(net["ci_high"], 0.0) + 0.5
    zero = scale(0.0, lo2, hi2, 420, 700)
    parts.append('<line x1="%.1f" y1="55" x2="%.1f" y2="170" stroke="#999" stroke-dasharray="4 3"/>' % (zero, zero))
    parts.append('<text x="%.1f" y="186" text-anchor="middle" fill="#666">0</text>' % zero)
    color = "#dc2626" if net["ci_high"] < 0 else ("#16a34a" if net["ci_low"] > 0 else "#d97706")
    parts.append('<line x1="%.1f" y1="110" x2="%.1f" y2="110" stroke="%s" stroke-width="3"/>'
                 % (scale(net["ci_low"], lo2, hi2, 420, 700), scale(net["ci_high"], lo2, hi2, 420, 700), color))
    parts.append('<circle cx="%.1f" cy="110" r="6" fill="%s"/>' % (scale(net["diff"], lo2, hi2, 420, 700), color))
    parts.append('<text x="%.1f" y="94" text-anchor="middle">%+.2f</text>'
                 % (scale(net["diff"], lo2, hi2, 420, 700), net["diff"]))
    parts.append('<text x="400" y="%d" fill="#444">CI %+.2f to %+.2f (synthetic EUR per eligible player)</text>'
                 % (h - 18, net["ci_low"], net["ci_high"]))
    parts.append("</svg>")
    (OUT_DIR / "ab_summary.svg").write_text("\n".join(parts), encoding="utf-8")


def write_report(reports, res):
    OUT_DIR.mkdir(exist_ok=True)
    for name, (headers, rows) in reports.items():
        write_csv(name, headers, rows)
    write_csv("sample_size_table", ["mde_abs_pp", "players_per_arm"],
              [(round(100 * d, 1), n) for d, n in res["sample_size_table"]])
    pk = res["peeking"]
    write_csv("peeking_simulation", ["looks", "simulated_AA_tests", "false_positive_single_look",
                                     "false_positive_peeking_every_day"],
              [(pk["n_looks"], pk["n_sims"], pk["fp_single_look"], pk["fp_peeking"])])

    prim, dep, net, ung, wins = (res["primary"], res["deposit"], res["net"],
                                 res["unsub_test"], res["net_wins"])
    ci_s = "%.1f%%" % (100 * net["ci_level"])
    result_rows = [
        ("conversion within 7 days", "primary", pct(prim["p_a"]), pct(prim["p_b"]), pp(prim["diff"]),
         "%s to %s (95%%)" % (pp(prim["ci_low"]), pp(prim["ci_high"])), fmt_p(prim["p_value"])),
        ("first-deposit amount per player", "secondary", "%.2f" % dep["mean_a"], "%.2f" % dep["mean_b"],
         "%+.2f" % dep["diff"], "%+.2f to %+.2f (%s)" % (dep["ci_low"], dep["ci_high"], ci_s), "bootstrap"),
        ("net value per player (GGR 14d - bonus)", "secondary", "%.2f" % net["mean_a"], "%.2f" % net["mean_b"],
         "%+.2f" % net["diff"], "%+.2f to %+.2f (%s)" % (net["ci_low"], net["ci_high"], ci_s), "bootstrap"),
        ("unsubscribe within 7 days", "guardrail", pct(ung["p_a"]), pct(ung["p_b"]), pp(ung["diff"]),
         "%s to %s (%s)" % (pp(ung["ci_low"]), pp(ung["ci_high"]), ci_s), fmt_p(ung["p_value"])),
    ]
    write_csv("experiment_results", ["metric", "role", "a_control", "b_bonus", "diff_b_minus_a",
                                     "confidence_interval", "p_value"], result_rows)

    flow = reports["eligibility_flow"]
    verdict, reason = res["verdict"]
    srm, balc, balk = res["srm"], res["balance"]["balance_by_channel"], res["balance"]["balance_by_country"]
    md = ["# A/B Test Report: reactivation bonus email", "",
          "Synthetic data. GGR = stake - win; net value = GGR - bonus face value (not NGR: no taxes or fees).", "",
          "## 0. Plan (fixed before any outcome)", "",
          md_table(["item", "value"], [
              ("hypothesis", PLAN["hypothesis"]),
              ("arms", "A = standard reminder, B = reminder + 100%% deposit match up to %d" % BONUS_CAP),
              ("unit", PLAN["unit"]),
              ("primary metric", PLAN["primary_metric"]),
              ("secondary metrics", "; ".join(PLAN["secondary_metrics"])),
              ("guardrail", PLAN["guardrail_metric"]),
              ("baseline / MDE", "%s baseline, +%.1f pp smallest lift worth acting on" % (pct(PLAN["baseline_rate"], 0), 100 * PLAN["mde_abs"])),
              ("alpha / power", "%.2f two-sided / %.0f%%" % (PLAN["alpha"], 100 * PLAN["power"])),
              ("secondary alpha", "%.4f (Bonferroni, %d tests)" % (PLAN["alpha_secondary"], PLAN["n_secondary_tests"])),
              ("required sample", "%d players per arm" % res["required_n"]),
              ("decision rule", "SHIP B only if primary p < alpha with a positive lift AND the net-value CI "
                                "lies fully above 0 AND the guardrail holds. DO NOT SHIP if the primary fails, "
                                "the net-value CI lies fully below 0, or the guardrail breaks. Otherwise INCONCLUSIVE."),
          ]), "",
          "## 1. Who is in the test (eligibility flow)", "", md_table(*reports["eligibility_flow"]), "",
          "Required %d per arm, available %d (A) and %d (B). Power to detect the planned +%.1f pp with the "
          "available sample: %.0f%%." % (res["required_n"], res["n"]["A"], res["n"]["B"],
                                         100 * PLAN["mde_abs"], 100 * res["power_at_n"]), "",
          "## 2. Did the randomisation work?", "",
          "- Sample ratio check (planned 50/50): A = %d, B = %d, chi-square = %.3f, p = %s -> **%s** "
          "(fails only below %.3f)." % (res["n"]["A"], res["n"]["B"], srm["chi2"], fmt_p(srm["p_value"]),
                                         "OK" if srm["ok"] else "BROKEN", PLAN["srm_threshold"]),
          "- Channel mix equal across arms: chi-square = %.2f, df = %d, p = %s." % (balc["chi2"], balc["df"], fmt_p(balc["p_value"])),
          "- Country mix equal across arms: chi-square = %.2f, df = %d, p = %s." % (balk["chi2"], balk["df"], fmt_p(balk["p_value"])), "",
          md_table(*reports["balance_by_channel"]), "",
          "Enrolment ran for %d consecutive days (two full weeks), see `output/enrolment_by_day.csv`." % ENROL_DAYS, "",
          "## 3. Results", "", md_table(["metric", "role", "A control", "B bonus", "B minus A",
                                          "confidence interval", "p-value"], result_rows), "",
          "Raw totals per arm:", "", md_table(*reports["variant_summary"]), "",
          "Relative lift of the primary metric: %+.1f%%. The average first deposit of converters in the table "
          "above is descriptive only: it compares players who converted, and the bonus changes who converts." % (100 * prim["rel_lift"]), "",
          "Where the net-value difference of %+.2f per eligible player comes from: GGR difference %+.2f "
          "(not tested on its own, GGR is very noisy) and bonus cost %+.2f (B only)." % (
              net["diff"], res["ggr_pp"]["B"] - res["ggr_pp"]["A"], -res["bonus_pp"]["B"]), "",
          "## 4. Robustness: outliers", "",
          "Net value is heavy-tailed (a few large depositors). Capping the top and bottom 1%% of net value "
          "(at %.2f and %.2f) gives B minus A = %+.2f, %s CI %+.2f to %+.2f. %s" % (
              res["net_wins_caps"][0], res["net_wins_caps"][1], wins["diff"], ci_s, wins["ci_low"], wins["ci_high"],
              "The conclusion about net value is the same as without capping." if (
                  (wins["ci_high"] < 0) == (net["ci_high"] < 0) and (wins["ci_low"] > 0) == (net["ci_low"] > 0))
              else "The conclusion about net value CHANGES when outliers are capped, so treat it as weak."), "",
          "## 5. Verdict (rule from section 0, applied mechanically)", "",
          "**%s.** %s" % (verdict, reason), "",
          "What this verdict does not say: the bonus is costed at its face value (a real cost depends on "
          "wagering requirements and forfeits, so it is usually lower); only the first 14 days of value are "
          "counted (a longer window could pay a bonus back); it is one audience and one bonus size. "
          "The money figures follow from the generator settings, not from a real operator.", "",
          "![summary](ab_summary.svg)", "",
          "## 6. Why the plan forbids peeking", "",
          "%d simulated A/A tests (both arms identical, so every 'win' is a false positive), %d players per arm, "
          "%d daily looks, alpha %.2f:" % (pk["n_sims"], pk["n_per_arm"], pk["n_looks"], pk["alpha"]), "",
          md_table(["how the data is read", "false-positive rate"], [
              ("one look at the planned end", pct(pk["fp_single_look"], 1)),
              ("check every day, stop at the first p < 0.05 (%d looks)" % pk["n_looks"], pct(pk["fp_peeking"], 1))]), "",
          "## 7. Sample size by smallest detectable lift (baseline %s, alpha %.2f, power %.0f%%)" % (
              pct(PLAN["baseline_rate"], 0), PLAN["alpha"], 100 * PLAN["power"]), "",
          md_table(["lift to detect", "players per arm"], [("+%.1f pp" % (100 * d), n) for d, n in res["sample_size_table"]]), "",
          "_Generated from synthetic data. No real player data._", ""]
    (OUT_DIR / "experiment_report.md").write_text("\n".join(md), encoding="utf-8")
    write_svg(res)


def main():
    check_sqlite()
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = new_connection(DB_PATH)
    n_dep, n_gam, n_mail = build_experiment(con)
    print("Candidates: %d | emails sent: %d, deposits: %d, gaming rows: %d (SQLite %s, Python %s)"
          % (N_CANDIDATES, n_mail, n_dep, n_gam, sqlite3.sqlite_version, sys.version.split()[0]))
    reports = run_reports(con)
    res = analyse(con, reports)
    OUT_DIR.mkdir(exist_ok=True)
    write_report(reports, res)
    con.close()
    p = res["primary"]
    print("SRM p = %s | conversion A %s vs B %s (%s, p = %s) | net value diff %+.2f (CI %+.2f to %+.2f)"
          % (fmt_p(res["srm"]["p_value"]), pct(p["p_a"]), pct(p["p_b"]), pp(p["diff"]), fmt_p(p["p_value"]),
             res["net"]["diff"], res["net"]["ci_low"], res["net"]["ci_high"]))
    print("VERDICT: %s - %s" % res["verdict"])
    print("Wrote report and CSV files to %s" % OUT_DIR)


if __name__ == "__main__":
    main()

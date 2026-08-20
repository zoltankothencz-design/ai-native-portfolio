"""
Cohort Retention Report
-----------------------
Creates a SQLite DB with fake users + events, then runs a CTE/window-function
query that calculates monthly cohort retention %.
Outputs: retention_report.csv and retention_report.md
"""

import sqlite3, csv, random, datetime, pathlib

DB = pathlib.Path("cohort.db")
OUT_CSV = pathlib.Path("retention_report.csv")
OUT_MD  = pathlib.Path("retention_report.md")

# ── 1. Seed ───────────────────────────────────────────────────────────────────

random.seed(42)

def random_date(start: datetime.date, days: int) -> datetime.date:
    return start + datetime.timedelta(days=random.randint(0, days))

con = sqlite3.connect(DB)
cur = con.cursor()
cur.executescript("""
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS events;

CREATE TABLE users (
    user_id   INTEGER PRIMARY KEY,
    signup_at TEXT NOT NULL          -- ISO date YYYY-MM-DD
);

CREATE TABLE events (
    event_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    event_at  TEXT NOT NULL,         -- ISO date YYYY-MM-DD
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
""")

START = datetime.date(2024, 1, 1)
COHORT_MONTHS = 6   # cohorts Jan–Jun 2024
USERS_PER_MONTH = 200
RETENTION_CURVE = [1.0, 0.65, 0.48, 0.38, 0.30, 0.24]  # M0-M5 baseline

users = []
events_batch = []
uid = 1
for cohort_month in range(COHORT_MONTHS):
    cohort_start = datetime.date(2024, 1 + cohort_month, 1)
    # Users sign up within this calendar month
    days_in_month = 28
    for _ in range(USERS_PER_MONTH):
        signup = cohort_start + datetime.timedelta(days=random.randint(0, days_in_month - 1))
        users.append((uid, signup.isoformat()))
        # Generate activity events across subsequent months
        for m_offset, base_ret in enumerate(RETENTION_CURVE):
            # Add some noise ±10%
            ret = min(1.0, max(0, base_ret + random.uniform(-0.10, 0.10)))
            if random.random() < ret:
                activity_date = signup + datetime.timedelta(days=m_offset * 30 + random.randint(0, 25))
                events_batch.append((uid, activity_date.isoformat()))
        uid += 1

cur.executemany("INSERT INTO users VALUES (?,?)", users)
cur.executemany("INSERT INTO events (user_id, event_at) VALUES (?,?)", events_batch)
con.commit()

print(f"Seeded {len(users)} users, {len(events_batch)} events.")

# ── 2. Cohort Retention Query ─────────────────────────────────────────────────

SQL = """
WITH cohorts AS (
    SELECT
        user_id,
        strftime('%Y-%m', signup_at) AS cohort_month
    FROM users
),
activity AS (
    SELECT
        e.user_id,
        c.cohort_month,
        CAST(
            (julianday(strftime('%Y-%m-01', e.event_at))
             - julianday(cohort_month || '-01'))
            / 30.44 AS INTEGER
        ) AS months_since_signup
    FROM events e
    JOIN cohorts c USING (user_id)
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM cohorts
    GROUP BY cohort_month
),
retained AS (
    SELECT cohort_month, months_since_signup, COUNT(DISTINCT user_id) AS active_users
    FROM activity
    WHERE months_since_signup BETWEEN 0 AND 5
    GROUP BY cohort_month, months_since_signup
)
SELECT
    r.cohort_month,
    cs.cohort_size,
    r.months_since_signup AS month_offset,
    r.active_users,
    ROUND(100.0 * r.active_users / cs.cohort_size, 1) AS retention_pct
FROM retained r
JOIN cohort_sizes cs USING (cohort_month)
ORDER BY r.cohort_month, r.months_since_signup;
"""

rows = cur.execute(SQL).fetchall()
headers = ["cohort_month", "cohort_size", "month_offset", "active_users", "retention_pct"]

# CSV
with open(OUT_CSV, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(headers)
    w.writerows(rows)

# Pivot for markdown
from collections import defaultdict
pivot: dict[str, dict[int, str]] = defaultdict(dict)
sizes: dict[str, int] = {}
for cohort, size, offset, active, pct in rows:
    pivot[cohort][offset] = f"{pct}%"
    sizes[cohort] = size

max_offset = max(o for row in pivot.values() for o in row)
col_headers = ["Cohort", "Size"] + [f"M+{i}" for i in range(max_offset + 1)]
md_rows = []
for cohort in sorted(pivot):
    row = [cohort, str(sizes[cohort])]
    for i in range(max_offset + 1):
        row.append(pivot[cohort].get(i, "-"))
    md_rows.append(row)

def md_table(headers, rows):
    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    header_line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    body = "\n".join(
        "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(row)) + " |"
        for row in rows
    )
    return f"{header_line}\n{sep}\n{body}"

with open(OUT_MD, "w") as f:
    f.write("# Monthly Cohort Retention Report\n\n")
    f.write("Retention % = active users in month N / cohort size at M+0\n\n")
    f.write(md_table(col_headers, md_rows))
    f.write("\n\n_Generated from synthetic data. No real user PII._\n")

con.close()
print(f"Reports written: {OUT_CSV}, {OUT_MD}")

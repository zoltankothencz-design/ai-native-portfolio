"""
Revenue Forecast Model
-----------------------
Fake monthly ARR/MRR data for a B2B SaaS product.
Computes LTV:CAC per cohort, then extrapolates the next quarter
with a simple linear trend + 80% confidence interval.
Outputs: forecast_chart.png
"""

import random, datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

random.seed(7)
np.random.seed(7)

# ── 1. Generate fake monthly cohort data (Jan 2023 – Jun 2024) ────────────────

months = pd.date_range("2023-01-01", "2024-06-01", freq="MS")
n = len(months)

cohorts = []
for i, m in enumerate(months):
    new_customers     = int(random.gauss(80 + i * 3, 10))
    acv               = random.uniform(1_800, 3_200)         # annual contract value
    cac               = random.uniform(800, 1_400)           # cost to acquire
    avg_lifetime_mo   = random.gauss(24, 4)                  # average lifetime in months
    mrr_new           = new_customers * (acv / 12)
    ltv               = (acv / 12) * avg_lifetime_mo         # simple LTV
    cohorts.append({
        "month":          m,
        "new_customers":  new_customers,
        "acv":            acv,
        "cac":            cac,
        "mrr_new":        mrr_new,
        "ltv":            ltv,
        "ltv_cac":        ltv / cac,
    })

df = pd.DataFrame(cohorts)

# ── 2. Rolling MRR (cumulative with 2% monthly churn) ────────────────────────

churn_rate = 0.02
mrr_series = []
current_mrr = 0.0
for _, row in df.iterrows():
    current_mrr = current_mrr * (1 - churn_rate) + row["mrr_new"]
    mrr_series.append(current_mrr)

df["mrr_total"] = mrr_series
df["arr_total"]  = df["mrr_total"] * 12

# ── 3. Trend extrapolation for next quarter ───────────────────────────────────

x = np.arange(n)
y = df["arr_total"].values
coeffs = np.polyfit(x, y, deg=1)          # linear fit
slope, intercept = coeffs

# Residuals → confidence interval
y_fit     = np.polyval(coeffs, x)
residuals = y - y_fit
sigma     = residuals.std()
z_80      = 1.282                          # 80% CI z-score

future_x = np.arange(n, n + 3)            # next 3 months (Q3 2024)
future_dates = pd.date_range(months[-1] + pd.offsets.MonthBegin(1), periods=3, freq="MS")
future_y     = np.polyval(coeffs, future_x)
ci_lower     = future_y - z_80 * sigma
ci_upper     = future_y + z_80 * sigma

# ── 4. Print summary table ────────────────────────────────────────────────────

print("\n=== Cohort LTV:CAC Summary ===")
print(df[["month", "new_customers", "ltv_cac", "arr_total"]]
      .rename(columns={"month": "Month", "new_customers": "New Cust.",
                       "ltv_cac": "LTV:CAC", "arr_total": "ARR ($)"})
      .to_string(index=False,
                 formatters={"Month": lambda d: d.strftime("%Y-%m"),
                              "LTV:CAC": "{:.2f}".format,
                              "ARR ($)": "${:,.0f}".format}))

print(f"\n=== Q3 2024 Forecast (80% CI) ===")
for d, y_hat, lo, hi in zip(future_dates, future_y, ci_lower, ci_upper):
    print(f"  {d.strftime('%Y-%m')}: ${y_hat:,.0f}  [{lo:,.0f} – {hi:,.0f}]")

# ── 5. Chart ─────────────────────────────────────────────────────────────────

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("Revenue Forecast — Synthetic B2B SaaS Data", fontsize=13, fontweight="bold")

# Left: ARR trend + forecast
ax = axes[0]
ax.plot(df["month"], df["arr_total"] / 1e6, color="#2563EB", lw=2, label="Historical ARR")
ax.plot(future_dates, future_y / 1e6, color="#10B981", lw=2, linestyle="--", label="Forecast")
ax.fill_between(future_dates, ci_lower / 1e6, ci_upper / 1e6,
                color="#10B981", alpha=0.18, label="80% CI")
ax.set_title("ARR Trajectory + Q3 2024 Forecast")
ax.set_ylabel("ARR (US$M)")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.1f}M"))
ax.legend(fontsize=9)
ax.grid(axis="y", alpha=0.3)

# Right: LTV:CAC per cohort
ax2 = axes[1]
colors = ["#2563EB" if v >= 3 else "#F59E0B" if v >= 2 else "#EF4444"
          for v in df["ltv_cac"]]
bars = ax2.bar(df["month"], df["ltv_cac"], width=20, color=colors)
ax2.axhline(3, color="#10B981", lw=1.5, linestyle="--", label="Healthy (3:1)")
ax2.axhline(2, color="#F59E0B", lw=1.2, linestyle=":", label="Caution (2:1)")
ax2.set_title("LTV:CAC Ratio per Cohort")
ax2.set_ylabel("LTV:CAC")
ax2.legend(fontsize=9)
ax2.grid(axis="y", alpha=0.3)

fig.tight_layout()
out = "forecast_chart.png"
fig.savefig(out, dpi=150)
print(f"\nChart saved: {out}")

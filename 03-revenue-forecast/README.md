# 03 — Revenue Forecast Model

**What it does:** Generates 18 months of synthetic B2B SaaS ARR/MRR data across monthly acquisition cohorts, computes LTV:CAC ratios per cohort, then extrapolates the next quarter's ARR using a linear trend with an 80% confidence interval. Outputs a two-panel matplotlib chart.

## Key techniques

- **Cohort-level LTV:CAC** — each cohort gets its own ACV, CAC, and estimated lifetime, not a blanket company average.
- **Rolling MRR with churn** — `MRR_t = MRR_{t-1} × (1 − churn) + new_MRR_t` gives a realistic compounding curve.
- **Linear extrapolation + confidence interval** — `np.polyfit(deg=1)` on historical ARR, residual σ → z₀.₈₀ = 1.282 for 80% CI bands. Intentionally simple — easy to explain, easy to upgrade to a more sophisticated model.
- **Color-coded LTV:CAC bars** — green ≥ 3:1 (healthy), amber 2–3:1, red < 2:1.

## How to run

```bash
cd 03-revenue-forecast
pip install -r requirements.txt
python forecast.py
# → forecast_chart.png + printed summary table + Q3 forecast
```

## Output

- Console: cohort table + Q3 2024 forecast with CI
- `forecast_chart.png`: ARR trajectory + LTV:CAC bar chart

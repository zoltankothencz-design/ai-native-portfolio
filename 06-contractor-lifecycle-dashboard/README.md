# 06 — Contractor Lifecycle & SLA Tracker (Web)

**Live demo:** https://vendor-ops-dashboard-two.vercel.app

**What it does:** A single-page HTML/JS dashboard tracking contractor onboarding, SLA/KPI compliance, turnover, and contract expiration across a vendor portfolio. Every chart is cross-filtering — clicking a bar, state, or funnel stage filters every other visual on the page. Data is synced to Supabase, with a demo dataset seeded by default and an "Import Data" option to load your own CSV.

## Key techniques

- Client-side cross-filtering across 10 dimensions (state, vendor, pay band, age, tenure, gender, expiration window, …) with no backend query round-trip per click.
- "Bottleneck Insights" panel: a rules-based layer that surfaces the single slowest onboarding stage, the vendor with the most near-term expirations, and flagged data discrepancies (duplicate/missing records) — computed client-side from the same dataset the charts use, not hardcoded.
- Supabase as a lightweight sync layer so the demo dataset persists between visits without a custom backend.

## How to run locally

```bash
# just open the file — no build step
open 06-contractor-lifecycle-dashboard/vendor_ops_dashboard.html
```

For the live Supabase-synced version, use the deployed link above.

**Stack:** HTML, CSS, vanilla JavaScript, Supabase (data sync), deployed on Vercel.

---

_All data is synthetic — a fictional contractor/vendor portfolio for illustration only._

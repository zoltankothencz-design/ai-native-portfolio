# AI-native Portfolio Demo Projects

Twelve self-contained demo projects built with Claude Code and other AI tools, on synthetic or mock data (one exception noted below). They cover the work I do around reporting, retention analytics and automation, with a focus on iGaming.
Each project lives in its own subdirectory with a README and, where applicable, runnable code.

## Start here for iGaming CRM, retention and reporting

- [01 SQL Cohort Retention Report](01-cohort-retention/): month-over-month player retention per signup cohort, in SQL (CTEs, joins, distinct counts).
- [10 iGaming Operations Report](10-powerbi-igaming-report/): GGR/NGR, RTP, bonus cost and player geography in Power BI.
- [04 Ticket Triage Agent](04-ticket-triage/): a classify, decide, act pipeline built on the Claude API, the pattern behind support and CRM automation.
- [02 API Webhook Integration](02-webhook-integration/): event intake with authentication and retry logic.
- [08 Casino Player Tracking Master Report](08-casino-master-report/): description only, real production reporting patterns, not published.

## All projects

| # | Project | Stack | What it shows |
|---|---|---|---|
| 01 | [SQL Cohort Retention Report](01-cohort-retention/) | Python, SQLite | Multi-step CTE cohort retention |
| 02 | [API Webhook Integration](02-webhook-integration/) | FastAPI, httpx | Auth, retry logic, event routing |
| 03 | [Revenue Forecast Model](03-revenue-forecast/) | pandas, matplotlib | LTV:CAC, trend extrapolation, CI bands |
| 04 | [Ticket Triage Agent](04-ticket-triage/) | Python, Claude API | Multi-step agent: classify → decide → act |
| 05 | [Few-Shot Prompt Examples](05-few-shot-prompts/) | Markdown | Prompt engineering reference |
| 06 | [Contractor Lifecycle Dashboard (Web)](06-contractor-lifecycle-dashboard/) | HTML/JS, Supabase, Vercel | Live cross-filtering ops dashboard: [demo](https://vendor-ops-dashboard-two.vercel.app) |
| 07 | [Contractor Lifecycle Dashboard (Excel)](07-ceo-excel-dashboard/) | Excel, VBA, PivotTables | Click-to-filter charts, auto-computed bottleneck findings |
| 08 | [Casino Player Tracking Master Report](08-casino-master-report/) | Excel, Power Query, Power Pivot | Description only: real production data, not published |
| 09 | [EV Sales & Charging Infrastructure](09-powerbi-ev-sales/) | Power BI, DAX | Global EV market trends, 2010 to 2024 |
| 10 | [iGaming Operations Report](10-powerbi-igaming-report/) | Power BI, DAX | GGR/NGR, RTP, player geography |
| 11 | [Zara Sales & Merchandising Analysis](11-powerbi-zara-sales/) | Power BI, DAX | Retail pricing, promotion, and placement analysis |
| 12 | [HR Analytics Dashboard](12-powerbi-hr-analytics/) | Power BI, DAX | Workforce, salary, and fluctuation-risk analytics |

## Quick start

Each project has its own `requirements.txt`. General pattern:

```bash
cd 0N-project-name
pip install -r requirements.txt   # if applicable
python main_script.py
```

Project 04 requires `ANTHROPIC_API_KEY` set in the environment.
All other projects run on stdlib or open-source libraries only.

---

_All data is synthetic. No real user, payment, or company data was used, except project 08, which is described only (no files published) because it runs on real production data._

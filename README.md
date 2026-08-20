# AI-native Portfolio Demo Projects

Five self-contained demo projects built with synthetic/mock data.
Each project lives in its own subdirectory with a README and runnable code.

| # | Project | Stack | What it shows |
|---|---|---|---|
| 01 | [SQL Cohort Retention Report](01-cohort-retention/) | Python, SQLite | CTE + window-function analytics |
| 02 | [API Webhook Integration](02-webhook-integration/) | FastAPI, httpx | Auth, retry logic, event routing |
| 03 | [Revenue Forecast Model](03-revenue-forecast/) | pandas, matplotlib | LTV:CAC, trend extrapolation, CI bands |
| 04 | [Ticket Triage Agent](04-ticket-triage/) | Python, Claude API | Multi-step agent: classify → decide → act |
| 05 | [Few-Shot Prompt Examples](05-few-shot-prompts/) | Markdown | Prompt engineering reference |

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

_All data is synthetic. No real user, payment, or company data was used._

# 06 — Contractor Lifecycle & SLA Tracker (Web)

**Live demo:** https://vendor-ops-dashboard-two.vercel.app

**What it does:** A single-page HTML/JS dashboard tracking contractor onboarding, SLA/KPI compliance, turnover, and contract expiration across a vendor portfolio. Every chart is cross-filtering — clicking a bar, state, or funnel stage filters every other visual on the page. Data is synced to Supabase, with a demo dataset seeded by default and an "Import Data" option to load your own CSV.

## Key techniques

- Client-side cross-filtering across 10 dimensions (state, vendor, pay band, age, tenure, gender, expiration window, …) with no backend query round-trip per click.
- "Bottleneck Insights" panel: a rules-based layer that surfaces the single slowest onboarding stage, the vendor with the most near-term expirations, and flagged data discrepancies (duplicate/missing records) — computed client-side from the same dataset the charts use, not hardcoded.
- Supabase as a lightweight sync layer so the demo dataset persists between visits without a custom backend.

## How I would run an experiment here

The Bottleneck Insights panel names the slowest onboarding stage. I would turn that into a test instead of a guess.

- **Hypothesis:** simplifying the slowest stage (for example a shorter document checklist) cuts its median time without more rejected or incomplete contractors later.
- **Metric:** primary is median days in that stage. Guardrails are SLA compliance after onboarding, early turnover, and the share of records flagged as discrepancies.
- **Sample size:** the unit is the contractor, assigned at random as they enter the stage (not by vendor, so vendor mix does not skew it). I would calculate the number needed in advance from the current spread of stage times and the smallest saving worth having. The demo dataset is synthetic, so it shows the method, not a result.
- **Decision rule:** fixed before the start. Roll out only if the time saving reaches the set threshold with a confidence interval away from zero and no guardrail gets worse. Otherwise keep the current process.

### Hogyan mérnék itt egy kísérletet

A Bottleneck Insights panel megnevezi a leglassabb onboarding-lépést. Ebből tesztet csinálnék találgatás helyett.

- **Feltevés:** ha a leglassabb lépést egyszerűsítem (például rövidebb dokumentum-ellenőrzőlista), a lépés mediánideje csökken, a későbbi elutasítások és hiányos rekordok növekedése nélkül.
- **Mérőszám:** fő mérőszám a lépésben töltött napok mediánja. Védőmérőszám az onboarding utáni SLA-teljesítés, a korai kilépés és az eltérésként jelölt rekordok aránya.
- **Mintaméret:** az egység a vállalkozó, véletlenszerűen osztom be, amikor belép a lépésbe (nem vendor szerint, hogy a vendor-összetétel ne torzítson). A szükséges számot előre számolom a lépésidők szórásából és a még érdemi megtakarításból. A demo adat szintetikus, ezért a módszert mutatja, nem eredményt.
- **Döntési szabály:** a kezdés előtt rögzítem. Csak akkor vezetem be, ha az időmegtakarítás eléri a küszöböt, a konfidenciaintervallum nulla fölött van, és egy védőmérőszám sem romlik. Különben marad a jelenlegi folyamat.

## How to run locally

```bash
# just open the file — no build step
open 06-contractor-lifecycle-dashboard/vendor_ops_dashboard.html
```

For the live Supabase-synced version, use the deployed link above.

**Stack:** HTML, CSS, vanilla JavaScript, Supabase (data sync), deployed on Vercel.

---

_All data is synthetic — a fictional contractor/vendor portfolio for illustration only._

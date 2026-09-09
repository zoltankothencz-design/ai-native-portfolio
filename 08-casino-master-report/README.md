# 08 — Casino Player Tracking Master Report (Excel + Power Pivot)

**No files or screenshots in this folder — by design.** This is a real production reporting workbook built for an active Las Vegas casino property, and it runs on real player data (names, birthdates, financial results). It isn't published here; this README is a description of the build, available to walk through live in an interview.

## What it does

A single Excel workbook (18MB+, live external data connections) consolidating live-table and slot-tracking data for the property:

- **Player Profile lookup:** search any tracked player by name and see their full history — drop, result, and visit count, broken out by Live and Slot sections, aggregated across every tracked visit day.
- **VIP / Top 100 leaderboards** for both Live and Slot play.
- **Time-series reporting** (daily/monthly rollups) feeding YoY comparisons.
- **Data discrepancy handling:** the underlying player list is sourced from two live external tracking files (Live pit + Slot systems) via Power Query, so the same real person can legitimately appear multiple times — once per tracked visit, across both sections. The report reconciles this into one player identity per search result rather than showing raw duplicate rows.

## Key techniques

- Power Pivot data model (8 model tables) fed by ~20 Power Query connections against two external live-tracking source files.
- Dynamic array `FILTER()` formulas for the player search box, spilling a variable number of matching visit rows per query.
- `SUMIFS`-based rollups across the full transaction history (tens of thousands of rows) so a player-level summary reflects every visit, not just the most recent one.

**Stack:** Excel, Power Query, Power Pivot (Power BI-style data model inside Excel), DAX-free `SUMIFS`/`FILTER` formula layer.

---

_Not published: contains real player PII and real financial data for an operating casino property. Described here for context only._

# 08 - Casino Player Tracking Master Report (Excel + Power Pivot)

No files or screenshots in this folder, by design. This is a demo workbook built around the reporting patterns used in live casino floor operations. It is not published here, because the original build requires proprietary operator data sources. This README describes the build and its techniques, available to walk through live in an interview.

## What it does

A single Excel workbook (18MB+, live external data connections) consolidating live-table and slot-tracking data for a casino floor. Player Profile lookup lets you search any tracked player by name and see their full history, drop, result, and visit count, broken out by Live and Slot sections, aggregated across every tracked visit day. VIP and Top 100 leaderboards cover both Live and Slot play. Time-series reporting gives daily and monthly rollups feeding YoY comparisons. Data discrepancy handling reconciles the underlying player list, which is sourced from two live external tracking files, Live pit plus Slot systems, via Power Query, so the same person can legitimately appear multiple times, once per tracked visit, across both sections. The report reconciles this into one player identity per search result rather than showing raw duplicate rows.

## Key techniques

Power Pivot data model with 8 model tables, fed by around 20 Power Query connections against two external live-tracking source files. Dynamic array FILTER formulas power the player search box, spilling a variable number of matching visit rows per query. SUMIFS-based rollups run across the full transaction history, tens of thousands of rows, so a player-level summary reflects every visit, not just the most recent one.

Stack: Excel, Power Query, Power Pivot, DAX-free SUMIFS and FILTER formula layer.

Not published: built on an operating casino property's internal reporting structure and requires the original data source files. Available to walk through live in an interview.

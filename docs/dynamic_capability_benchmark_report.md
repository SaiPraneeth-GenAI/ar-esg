# Dynamism Benchmark Report: Inputs & Dashboards
**Scope:** Not new features — the same categories and fields Amara Raja already tracks. This report evaluates *how the same inputs are collected* and *how the same numbers are visualized*, benchmarked against market-leading ESG platforms (Workiva, Watershed, Persefoni, Novisto, IBM Envizi, Sphera, Diligent ESG).

---

## Part 1 — Dynamic Data Input

| Capability | Market leaders (2026) | Amara Raja's current tool | What "dynamic" looks like for us |
|---|---|---|---|
| Conditional/branching fields | Questions appear only when relevant, based on prior answers (KeyESG's conditional custom metrics) | None observed — every field shows regardless of relevance (e.g. Stack Air Emissions shows all 6 pollutant fields even when marked "Not Applicable") | Same fields, shown conditionally — an "Applicable / Not Applicable" toggle at the top of a form hides/shows the fields beneath it live |
| Repeatable/multi-instance entry | Repeatable question blocks for multi-site or multi-meter data | The Trend/Task table already has a **Meter ID** column — meaning the schema anticipates multiple meters per data point, but the entry screen only exposes one field at a time | Let a user add N meter readings under the same data point in one session; the system sums/aggregates them automatically into the monthly total |
| Smart defaults & pre-fill | Prior-period value suggested, anomaly flagged at entry time | Prior month/year values are shown as read-only reference text, not used to pre-fill or validate | Pre-fill with last month's value as a placeholder; flag in real time if the new entry deviates sharply from trailing average, before it's even saved |
| Multi-source ingestion into the same field | Manual, bulk CSV, and (increasingly) automated meter/API feeds all write to the same underlying field | Every entry in every screenshot is logged as "Manual" — no bulk or automated path observed | Same input slot, three ways to fill it: type it, upload a CSV against a template, or (later) pull from a connected meter — the approval and audit-trail step stays identical regardless of source |
| Dynamic validation | Field-level min/max bounds derived from a facility's own historical range, catching typos before they reach an approver | No validation observed beyond "required" — a typo (10x factor error) would sail straight into the approval queue | Auto-computed bounds per field per location, flagged inline rather than caught later by a human eyeballing a report |
| Multi-framework mapping | A single entered value can satisfy multiple disclosure frameworks (CSRD, GRI, SASB, BRSR) at once without re-entry (Novisto's model) | Every field appears purpose-built for one report path | Tag each existing field with which frameworks it satisfies, so BRSR/GRI/EPR reports auto-populate from the same entry instead of separate data pulls |

**Bottom line on inputs:** the actual list of fields doesn't need to grow. What needs to change is that entering data becomes adaptive to context (location, history, applicability) instead of a flat, always-fully-visible form — that's the exact gap between what Amara Raja has today and what the 2026 leaders ship.

---

## Part 2 — Dynamic Dashboards

| Capability | Market leaders (2026) | Amara Raja's current tool | What "dynamic" looks like for us |
|---|---|---|---|
| Layout | Drag-and-drop, user-arranged widgets (Workiva) | Fixed spreadsheet-style report with sheet-tab navigation (Index, Target Dashboard I/II/III, Energy-Targets...) — literally an embedded Excel layout | Same metrics (Environmental Performance, Safety, Absolute/Intensity), rendered as movable cards each user can arrange for their own role |
| Drill-down | Click a KPI → decomposes into location → month → raw entry | None — numbers are static table cells with no click behavior | Every dashboard number is clickable straight down to the approved entry that produced it |
| Query interface | Natural-language / AI copilot: "show me water withdrawal trend for Plant X, last 6 months" (now shipping in Microsoft Sustainability Manager Copilot and equivalents at Workiva/Watershed) | None — navigation is entirely manual, tab by tab | Same underlying data, queryable in plain language instead of only through fixed tabs |
| Scenario / what-if | Forecast the impact of changing a variable (e.g. recycling rate) before it happens | None — dashboard only shows what already occurred | Same metrics, but with a slider/toggle to model "what if" against the same historical data (e.g. impact of +10% battery-waste recycling on EPR recovery %) |
| Benchmarking | Industry benchmark shown inline, next to your own number | Isolated in a separate "Peer Analysis" report, not shown alongside the live dashboard numbers | Same peer data, layered directly onto the same chart as a toggleable overlay instead of a separate destination |
| Refresh behavior | Recalculates live as new approved entries land | Static export-oriented view (PDF/PPT buttons are the primary actions) | Same numbers, but the dashboard updates the moment an entry is approved — no manual refresh/export cycle required to see current state |
| Role-awareness | Executives get a condensed live summary; analysts get full drill-down, automatically | One fixed view for every user regardless of role | Same data, shaped differently by who's looking at it — Preparer sees entry status, Approver sees the queue, Executive sees the KPI summary |

**Bottom line on dashboards:** the metrics Amara Raja already tracks (energy/GHG/water/waste intensity, safety rates) are the right metrics — nothing needs to be added. What's missing is that the dashboard is currently a *report you export*, not a *system you interact with*. Every leading 2026 platform has moved past static tables toward click-through, queryable, role-aware views of the same underlying numbers.

---

## Part 3 — Why This Framing Matters for the Pitch

Every gap identified above is a **delivery** gap, not a **coverage** gap — which is actually the stronger pitch to make to Amara Raja: "we're not asking you to track anything new, we're making the exact data you already collect dramatically easier to act on." That's a faster, lower-risk sell than proposing new metrics, and it's precisely where the current Updapt-style tool is weakest relative to Workiva/Watershed/Persefoni/Novisto/IBM Envizi in 2026.

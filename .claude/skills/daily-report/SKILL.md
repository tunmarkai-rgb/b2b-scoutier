---
name: daily-report
description: Regenerate the local HTML pipeline dashboard (reports/daily-report.html) and write the run summary with KPIs, hot leads, and warnings. Use at the end of every outreach run or when asked for a pipeline report.
---

# Daily Report

1. `python scripts/report.py` rebuilds `reports/daily-report.html`, a self-contained kanban with KPIs, inbox usage and
   hot leads. It opens with a double-click and needs no server.
2. `python scripts/crm.py stats` for the numbers.
3. End the run with a summary in this order:
   1. **Replies needing you**: each interested/question reply, with the suggested response.
   2. **Drafts awaiting approval** (manual mode): count, and the path `outreach/queue/outreach-queue.md`.
   3. **Today**: sourced / enriched / qualified / drafted / sent, and per-inbox sent vs cap.
   4. **Health**: reply rate (target 20% or more) and bounce rate (alarm above 3%), with a list of `pattern` emails to spot-check.
   5. **Recommendations**: at most 3, e.g. a copy angle that's working, a city switch, or an inbox ready to enable.

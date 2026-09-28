---
description: Show today's follow-ups, hot leads, drafts awaiting approval and inbox capacity (read-only)
---

Give a quick pipeline status. Don't send, draft, or change anything except the regenerated report file.

1. `python scripts/crm.py stats`
2. `python scripts/crm.py due-followups`
3. `python scripts/crm.py list --stage Interested` and `python scripts/crm.py list --stage "Call Booked"`
4. `python scripts/queue_md.py list --status pending` and `python scripts/queue_md.py list --status approved`
5. `python scripts/inbox_router.py status`
6. `python scripts/report.py`

Summarise in this order: hot leads needing action, follow-ups due today, drafts waiting for approval, inbox capacity
left today (sent/cap per inbox), and reply and bounce rates against targets (20% reply, under 3% bounce). End with the path
to `reports/daily-report.html`.

---
name: inbox-router
description: Assign queued drafts to sending inboxes by remaining daily capacity and warm-up stage, and report per-inbox capacity. Use after drafts are queued and before sending, or when asked how much sending capacity is left.
---

# Inbox Router

```
python scripts/inbox_router.py status     # capacity table
python scripts/inbox_router.py assign     # fill the `inbox:` field on unassigned active drafts
```

How capacity works (the script enforces this, so just read and report it):
- The cap per inbox comes from `config/warmup-schedule.json` based on `warmup_start` in `inboxes.json` (5, 10, 15, 20, 25),
  unless the inbox has `daily_cap_override` set.
- Sent today = the **higher** of the Gmail Sent folder count (ground truth, includes manual sends) and `contacted.csv`.
- Remaining = cap - sent today - drafts already assigned but unsent.
- First touches go to the inbox with the most room. Follow-ups keep the inbox that sent touch 1.
- Drafts that don't fit stay in the queue for tomorrow. That's expected, not an error.

If `imap_error` appears for an inbox, the Sent folder couldn't be checked. `send.py --live` will refuse to send from
that inbox until it's fixed (app password in `.env`, IMAP enabled in Gmail settings).

Never edit caps to squeeze in more volume. To grow volume, the human adds or enables more inboxes.

---
name: crm-writer
description: Record lead status changes in the flat-file CRM (contacts/*.csv) via scripts/crm.py, covering stage moves, notes, call booked, proposal sent, won/lost, suppression and do-not-contact. Use whenever any lead's status, contact details or notes change.
---

# CRM Writer

The CSVs in `contacts/` are the single source of truth. **Only change them through `scripts/crm.py`**, never by
editing the files. The script validates stages, dedupes, keeps suppression permanent, and writes atomically.

| Event | Command |
|---|---|
| New leads | `python scripts/crm.py add outreach/work/<batch>.json` |
| Any field change | `python scripts/crm.py update L-00012 --set stage="Call Booked" --note "Call Thu 2pm ET"` |
| Proposal sent | `python scripts/crm.py update L-00012 --set stage="Proposal Sent" --note "Sent $X/mo proposal"` |
| Won / Lost | `python scripts/crm.py update L-00012 --set stage=Won --note "Signed 3-month pilot"` |
| Hot reply | `python scripts/crm.py hot L-00012 --classification interested --summary "..." --next-action "..."` |
| Opt-out | `python scripts/crm.py suppress jane@acme.ca --reason unsubscribe` (or a domain) |
| Existing client | `python scripts/crm.py dnc --company "Acme" --domain acme.ca --reason "existing client"` |
| Lookups | `python scripts/crm.py get L-00012`, `list --stage Interested`, `stats` |

Valid stages: Sourced, Enriched, Qualified, Contacted, Follow-up, Replied, Interested, Call Booked,
Proposal Sent, Won, Lost, Disqualified. Moving a lead to Replied or later clears its `next_follow_up` automatically.

`send.py` and `fetch_replies.py` already record sends, bounces and replies. Don't duplicate those updates.

If a CSV is open in Excel, writes fail with a "locked" error. Ask the human to close it, then retry.

---
name: outreach-writer
description: Draft personalised cold emails and follow-ups offering TUNMARK's customer-acquisition system to qualified B2B leads, and add them to the outreach queue for review. Use after compliance-guard passes leads, or for due follow-ups.
---

# Outreach Writer

Write the drafts. Never send them. Every draft lands in `outreach/queue/outreach-queue.md` as `pending`.

## Inputs

- First touches: lead IDs that **passed** `python scripts/compliance.py leads --stage Qualified`.
- Follow-ups: `python scripts/crm.py due-followups` (touch 2 or 3). Check each with `compliance.py lead <id> --touch N`.
- For each lead: `python scripts/crm.py get <id>` gives `company`, `decision_maker`, `role`, `sells_what`,
  `category`, `signals`, `signal_notes`, `city`.
- Voice, structure and proof points: the "The offer and the voice" section of `CLAUDE.md`. Follow it exactly.

## Writing rules

- Open with **one specific, true observation** taken from `signal_notes` / `sells_what`, for example "Saw you're hiring a
  BD manager", "Noticed your trade-account page for retailers", or "Your Clutch reviews all mention fast turnaround".
  If there's nothing specific, open with a category-level observation ("Most staffing firms in Toronto
  we talk to..."). Never fabricate.
- Tie that observation to the problem: keeping a steady flow of new B2B customers without adding a sales hire or more ad spend.
- One sentence on TUNMARK: we build and run the whole customer-acquisition system (right-fit prospect lists,
  personalised outbound, reply handling) and hand them booked calls.
- Proof point: optional, one line, only when the industry matches (for example, The Realty Network for real estate).
- CTA: a soft question. No calendar links in touch 1.
- Address them by first name. Sign off with just your first name from `config/settings.json` -> `sender.name`.
  `send.py` appends the full signature, address and opt-out.
- No `[placeholders]`, no TODO, no links, no emojis, no ALL CAPS.
- Follow-ups: leave `subject` empty so it threads as "Re: <original>", and add a new angle, not "just bumping this".
- Canada: keep the pitch clearly about their business (CASL relevance).

## Output

Write `outreach/work/drafts-<YYYY-MM-DD>-<n>.json`:
```json
[{"lead_id": "L-00012", "subject": "trade accounts at acme",
  "body": "Hi Jane,\n\nNoticed Acme's trade-account page...\n\nWorth a quick chat?\n\nAlex"},
 {"lead_id": "L-00003", "touch": 2, "subject": "", "body": "Hi Omar,\n\n..."}]
```
Then run `python scripts/queue_md.py add outreach/work/drafts-<...>.json` followed by `python scripts/compliance.py queue`.

## Self-check before adding (for every draft)

Is it 60 to 110 words for touch 1? Is the first line specific and true? Is there exactly one CTA? Would an owner read it as
one person writing to another, not a template? If not, rewrite it.

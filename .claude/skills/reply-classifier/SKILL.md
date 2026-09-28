---
name: reply-classifier
description: Fetch inbound replies and bounces from all inboxes, classify each (interested, question, not now, not interested, unsubscribe, referral, wrong person, out of office, bounce) and update the CRM accordingly. Use at the start of every outreach run or when asked to check replies.
---

# Reply Classifier

## Steps

1. `python scripts/fetch_replies.py`. This pulls new mail read-only and matches it to leads. It also applies the
   automatic rules: a human reply stops the sequence (stage `Replied`), a bounce marks the email `bounced`, and an
   auto-reply is only flagged. It prints the new items (also saved in `outreach/replies/replies-<date>.json`).
   If `errors` lists an inbox, report it (usually a missing app password in `.env`).
2. Classify every item where `type` is `reply` (and sanity-check `auto_reply` items):

| Class | Meaning | Action |
|---|---|---|
| `interested` | wants to talk / asks for times / "tell me more" | `crm.py hot <id> --classification interested --summary "<1 line>" --next-action "Reply with 2 time slots"` |
| `question` | asks price/how it works, not yet a yes | `crm.py hot <id> --classification question --summary ... --next-action "Answer: ..."` |
| `not_now` | "maybe next quarter", "busy now" | `crm.py update <id> --set stage=Lost --note "not now: revisit <month>"` |
| `not_interested` | polite no | `crm.py update <id> --set stage=Lost --note "not interested"` |
| `unsubscribe` | stop / remove / angry / "how did you get my email" | `crm.py suppress <email> --reason unsubscribe` |
| `referral` | "talk to X instead" | add X as a new lead via `crm.py add` (same company, same email_source rules), and update the original with `--note "referred to X"` |
| `wrong_person` | not the right contact, no referral | `crm.py update <id> --set stage=Lost --note "wrong person"` |
| `ooo` | out of office | nothing (sequence continues). If they're back after the next follow-up date, push it: `crm.py update <id> --set next_follow_up=YYYY-MM-DD` and `stage=Follow-up` |
| `bounce` | handled by the script | list them in the summary. If there are several from one domain, suspect the pattern guess |

When in doubt between `not_interested` and `unsubscribe`, choose `unsubscribe`.

3. **Do not reply to prospects.** List every `interested` / `question` reply at the top of the run summary with a
   suggested response draft (2 to 4 sentences, offer two call times). The human sends replies personally from the
   inbox the reply came in on.

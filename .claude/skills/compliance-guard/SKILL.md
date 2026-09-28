---
name: compliance-guard
description: Pre-send compliance gate (CASL for Canada, PECR/UK GDPR for the UK, suppression, do-not-contact, reply-stops-sequence). Run before drafting any outreach and before any send. Use whenever deciding whether a lead may be contacted.
---

# Compliance Guard

This is a gate, not advice. If the script says a lead is blocked, it does not get a draft.

## Before drafting

```
python scripts/compliance.py leads --stage Qualified
```
Only lead IDs in `passed` may go to the outreach-writer. For each `blocked` lead:
- `CASL: ... must be conspicuously published`: go back to enrichment and find a published address, or leave it.
- `email not verified`: run `python scripts/verify_email.py --leads`, or fix the address.
- `sender.* not filled in`: **stop the whole run** and tell the human to complete `config/settings.json` -> `sender`
  (legal name, company, website, physical mailing address). Nothing can be sent without these.
- `on suppression / do-not-contact list`: never override.

For follow-ups, check each due lead: `python scripts/compliance.py lead L-00012 --touch 2`.

## After drafting, before approval

```
python scripts/compliance.py queue
```
Drafts that fail are marked `blocked` in the queue with the reason. `send.py` re-runs the same checks per message,
so a lead who replies or unsubscribes between drafting and sending is never emailed.

## Judgment checks the script can't do (you must)

- The message relates to the recipient's business role (a CASL implied-consent condition). No personal-life angles.
- The prospect's site/listing has no "no unsolicited commercial email" notice next to the address. If it does, suppress the lead:
  `python scripts/crm.py suppress <email> --reason "site says no solicitation"`.
- Existing TUNMARK clients or partners: `python scripts/crm.py dnc --company "<name>" --domain <domain> --reason "existing client"`.
- No deceptive subject lines (no fake "Re:" on a first touch, no fake urgency).

# B2B Scoutier: TUNMARK Lead Generation Engine (Rulebook)

This project is a local, subscription-free outbound engine. Claude Code is the engine: it finds
**business owners who sell products or services to other businesses**, qualifies them against
the ICP, writes personalised outreach offering **TUNMARK's customer-acquisition system**, sends
through a pool of Gmail inboxes under warm-up caps, reads replies, and keeps a flat-file CRM.

Read this file before any pipeline work. The machine-readable versions of these rules are in
`config/*.json` and are enforced by `scripts/*.py`.

## Hard rules (never break these)

1. **Never edit `contacts/*.csv`, `outreach/queue/outreach-queue.md` status fields, or `outreach/sent-log.md` by hand.**
   Every state change goes through the scripts (`crm.py`, `queue_md.py`, `verify_email.py`, `send.py`, `fetch_replies.py`).
   The scripts handle dedupe, suppression, stage rules and atomic writes.
2. **Never send email any way other than `python scripts/send.py --live`.** It holds the inbox lock, re-checks the
   Gmail Sent folder against the cap, and re-runs compliance for every message.
3. **Review gate.** When `config/settings.json` has `"review_mode": "manual"` (Phase 1 default), never approve drafts
   yourself and never run `send.py --live` on drafts you created in the same run. Only the human approves drafts, by
   changing `status: pending` to `status: approved`. In `"auto"` mode, drafts that pass `compliance.py queue` may be
   approved with `queue_md.py approve --all`.
4. **Any human reply stops the sequence.** `fetch_replies.py` does this automatically. Never queue a follow-up for a
   lead whose stage is Replied or later.
5. **Unsubscribe = permanent.** "Stop", "unsubscribe", "remove me", "not interested, don't email again" means
   `crm.py suppress <email> --reason unsubscribe`. Never re-contact. Existing TUNMARK clients go on `do-not-contact.csv` (`crm.py dnc`).
6. **Canada (CASL):** only email addresses the business itself **publishes** (website, directory listing, signature
   on a public page) with no "no unsolicited email" notice. Record `email_source=published`. Pattern-guessed
   addresses (`email_source=pattern`) may be used **only for UK leads**. The message must relate to the
   recipient's role in their business.
7. **UK (PECR / UK GDPR):** corporate addresses of named individuals are fine under legitimate interest, with honest
   identification and a one-line opt-out (added automatically by `send.py`).
8. Never invent facts about a prospect. Every personalisation line must come from something you actually saw on
   their site, listing, or public profile. If you found nothing specific, use the category-level opener.

## Who we target (ICP)

- **Core:** owner-led businesses with 5 to 50 employees that sell to other businesses, either products (wholesale,
  manufacturing, distribution, e-commerce brands with a B2B/wholesale arm) or services.
- **Priority categories** (keys in `config/icp.json`): `marketing_agency`, `real_estate` (teams/brokerages),
  `clinic_medspa`, `b2b_saas`, `staffing_recruiting`, `home_services`, `ecommerce_wholesale`, plus
  `b2b_services_other` / `b2b_products_other`.
- **Readiness signals** (`signals` keys): `hiring_growth_role`, `paid_ads_no_outbound`, `founder_posts_about_pipeline`,
  `stale_website_or_crm`, `recent_funding_or_expansion`, `sells_to_businesses_confirmed`, `owner_reachable_directly`.
- **Disqualifiers:** `sells_only_to_consumers`, `enterprise_500_plus`, `franchise_corporate_controlled`,
  `existing_client`, `direct_competitor` (other lead-gen / outbound agencies).
- Decision-maker: owner, founder, CEO, managing partner, broker of record, clinic owner, or head of sales/growth.

## Geography

One city at a time, from `config/cities.json` (the entry with `"status": "active"`). The order is Toronto, Vancouver,
and Calgary, then London, Manchester, and Birmingham. Move to the next city only when the human says so, or when the active
city yields fewer than 10 new qualified leads across two consecutive runs. In that case, recommend the switch in the
run summary rather than doing it yourself.

## The offer and the voice

- **What we offer:** TUNMARK builds and runs a done-for-you customer-acquisition system (targeted prospect lists,
  personalised multi-inbox outbound, reply handling, booked calls) so owners get new B2B customers without hiring
  a sales team or buying more ads.
- **Proof points** (use at most one per email, only if relevant): The Realty Network (Canadian real estate) and
  BLEAK Group. Keep claims qualitative unless the human adds verified numbers here:
  - The Realty Network: _TODO add a verified result_
  - BLEAK Group: _TODO add a verified result_
- **Voice:** plain, peer-to-peer, one owner to another. No hype, no "I hope this finds you well", no fake
  familiarity, no emojis, no links in touch 1, no attachments.
- **Shape of touch 1:** 60 to 110 words. Line 1 is a specific observation about them. Then one sentence on the problem
  it implies, one sentence on what TUNMARK does, and a soft question CTA ("Worth a quick chat?" / "Open to seeing how
  it would work for {company}?"). Subject: 2 to 5 words, lowercase, no clickbait.
- **Touch 2 (day 3):** 30 to 60 words, same thread, a new angle or micro-case, and the same soft CTA.
- **Touch 3 (day 7):** 20 to 40 words, a polite close-the-loop message.
- `send.py` appends the signature, physical address and opt-out line. **Do not** write your own sign-off block.

## Sending rules

- Per-inbox caps come from `config/warmup-schedule.json` (5, 10, 15, 20, 25 per day as the inbox ages).
  `inbox_router.py` spreads first touches across inboxes. Follow-ups stay on the original inbox.
- The Gmail Sent folder is the ground truth for today's count, because it includes manual sends.
- One send batch per inbox at a time (`.locks/`). If a lock is stale and no run is active, it can be deleted.
- Target is 100 per day aggregate, reached by adding warmed inboxes, never by raising caps early.
- Watch the bounce rate: if it goes above 3% on a run, stop sending, report it, and tighten enrichment.

## Pipeline stages

Sourced, Enriched, Qualified, Contacted, Follow-up, Replied, Interested, Call Booked, Proposal Sent, and then
Won or Lost. There is also Disqualified (failed the ICP score or hit a disqualifier).

## Commands

- `/run-outreach` runs the full daily pipeline end to end (see `.claude/commands/run-outreach.md`).
- `/check-pipeline` shows today's follow-ups, hot leads, and inbox capacity.

## Script cheat-sheet (run from repo root)

```
python scripts/init_data.py
python scripts/crm.py add <file.json> | update <id> --set k=v | list --stage X | score | due-followups | stats
python scripts/crm.py suppress <email|domain> --reason ... | dnc --domain x.com --reason ... | hot <id> --classification ... --summary ...
python scripts/verify_email.py --leads
python scripts/compliance.py leads | queue
python scripts/queue_md.py add <drafts.json> | list | approve <ids>|--all | reject <ids> | archive
python scripts/inbox_router.py status | assign
python scripts/send.py [--live]
python scripts/fetch_replies.py
python scripts/report.py
```

Scratch JSON files (prospect batches, draft batches) go in `outreach/work/`, which is git-ignored.

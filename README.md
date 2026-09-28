# B2B Scoutier

A local, subscription-free lead-generation engine for **TUNMARK**. It runs entirely inside Claude Code: Claude
finds owner-led businesses that sell products or services to other businesses, qualifies them, writes personalised
outreach offering TUNMARK's customer-acquisition system, sends it through your own Gmail inboxes under warm-up caps,
reads the replies, and keeps a flat-file CRM plus a local HTML dashboard.

No n8n, no Airtable, no Apollo or Hunter, no ESP. The only costs are your Claude subscription and the inboxes you own.

```
Replies ─► Follow-ups ─► Prospect (web search) ─► Enrich + MX check ─► ICP score
   ─► Compliance gate ─► Draft ─► Route to inbox ─► [you approve] ─► Send ─► CRM ─► Dashboard
```

## How it's split

| Part | Where | Role |
|---|---|---|
| Rulebook | `CLAUDE.md` | ICP, voice, offer, compliance and sending rules Claude must follow |
| Config | `config/` | `settings.json` (review mode, sender identity, thresholds), `icp.json` (scoring), `cities.json` (rotation), `warmup-schedule.json` |
| Judgment | `.claude/skills/`, `.claude/agents/` | Sourcing, enrichment, copywriting, reply classification: the work that needs an LLM |
| State + sending | `scripts/` | Deterministic Python (standard library only). All CSV writes, compliance checks, caps, locks, SMTP/IMAP |
| One-button run | `.claude/commands/run-outreach.md` | `/run-outreach` runs the whole day. `/check-pipeline` gives a read-only status |
| CRM | `contacts/*.csv` (git-ignored) | prospects, contacted (append-only), hot-leads, suppression-list, do-not-contact |
| Dashboard | `reports/daily-report.html` (git-ignored) | Kanban + KPIs, rebuilt each run. Double-click to open |

## Setup (Windows)

1. **Prerequisites:** Python 3.10+ and Claude Code. Optional: `pip install -r requirements.txt` (dnspython, for faster MX checks).
2. **Create the local files:** `python scripts/init_data.py`
3. **Sender identity:** fill in every `TODO` under `sender` in `config/settings.json`: your name, website and a **real
   physical mailing address** (CASL requires it). Nothing sends until this is done.
4. **Inboxes:** edit `inboxes.json`, one entry per Gmail/Workspace inbox, with `warmup_start` set to the day it began cold sending.
   - For each inbox, turn on 2-Step Verification, create an app password at <https://myaccount.google.com/apppasswords>,
     and put it in `.env` as `INBOX_<ID>_APP_PASSWORD` (e.g. `INBOX_TM1_APP_PASSWORD`).
   - Make sure IMAP is enabled (Gmail settings, then Forwarding and POP/IMAP).
   - Sending domains should have SPF, DKIM and DMARC set up. Use secondary domains for cold email, not your main domain.
5. **Proof points:** replace the `TODO` results for The Realty Network and BLEAK Group in `CLAUDE.md` with verified outcomes.
6. **Existing clients:** add each one with `python scripts/crm.py dnc --company "Name" --domain their.com --reason "existing client"`.
7. **Check it:** `python scripts/inbox_router.py status` should show each inbox with a cap and no `imap_error`.

## Daily use

- Run `/run-outreach` in Claude Code (from this folder). In Phase 1 (`review_mode: manual`) it stops after drafting.
- Open `outreach/queue/outreach-queue.md`, edit any draft you like, and change `status: pending` to `status: approved`
  (or `rejected`).
- Send the approved ones: `python scripts/send.py --live` (or they go out at the start of the next `/run-outreach`).
  Run `python scripts/send.py` without `--live` first to preview them in `outreach/dry-run-preview.md`.
- Reply to interested leads yourself, from the inbox they replied to. The run summary includes suggested responses.
- `/check-pipeline` gives a quick status. Open `reports/daily-report.html` for the board.

### Schedule it

```powershell
.\scheduler\register-task.ps1 -Time "08:30"
```
This creates a daily Windows scheduled task that runs `claude -p "/run-outreach"` in this folder, with logs in `logs/`. The
PC must be on and logged in. Tools the run needs are pre-allowed in `.claude/settings.json`.

## Guardrails built in

- **Compliance gate** (`scripts/compliance.py`) runs before drafting and again per message inside `send.py`. It checks
  suppression/DNC, reply-stops-sequence, max 3 touches, verified email, allowed countries, CASL (Canadian addresses must be
  published by the business, never guessed), and a complete sender identity.
- Every message automatically gets your signature, physical address, a one-line opt-out and a `List-Unsubscribe` header.
- **Caps:** the warm-up schedule goes 5, 10, 15, 20, 25 per inbox per day. Today's count is taken from the Gmail **Sent folder**
  (which includes manual sends) and `contacted.csv`, whichever is higher. There's also one send-lock per inbox.
- Safe defaults: `send.py` is a dry run unless you pass `--live`, and `review_mode` starts at `manual`.

## Phases

| Phase | Scope | Target |
|---|---|---|
| 1. MVP | Toronto, 2-3 inboxes warming, every draft reviewed | Prove ICP + copy |
| 2. Scale inboxes | Full inbox pool, `review_mode: auto` | 40-60/day |
| 3. Multi-city | UK cities added to `cities.json` rotation | 100/day |
| 4. Optimize | A/B copy on reply data | Reply and call-booking rate |

## Privacy

This repository is public. Prospect data, inbox addresses, app passwords, queues, logs and reports are all git-ignored.
Keep it that way: run `git status` before committing.

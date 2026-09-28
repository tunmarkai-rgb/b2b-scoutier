---
description: Run the full daily outreach pipeline end to end (replies, follow-ups, prospecting, enrichment, compliance, drafting, routing, sending, report)
argument-hint: "[optional: number of new prospects to source, e.g. 30]"
---

Run today's B2B Scoutier pipeline. Read `CLAUDE.md` first and obey its hard rules. Run all scripts from the repo root
with the Bash tool (`python scripts/...`). Keep going through every step unless a step says STOP.

0. **Setup check.** `python scripts/init_data.py`. Read `config/settings.json` and note `review_mode`.
   If `sender` still contains TODO, you may source, enrich and draft, but note in the summary that nothing
   can send until it's filled in.
1. **Send what the human already approved.** If any drafts are `approved`, run
   `python scripts/inbox_router.py assign` and then `python scripts/send.py --live`. (In manual mode, these are drafts the human
   approved since the last run, so sending them is correct.) If inboxes aren't configured yet, skip this step.
2. **Replies.** Delegate to the `reply-reader` agent (or follow the reply-classifier skill directly).
   STOP sending for the day if the bounce rate from `crm.py stats` is above 3%. Still finish the drafting and report steps.
3. **Follow-ups.** `python scripts/crm.py due-followups`. Keep the lead IDs for step 6.
4. **Prospecting.** If there are fewer than 60 `Qualified` leads not yet contacted (`crm.py list --stage Qualified`),
   delegate to the `prospector` agent with a target of $ARGUMENTS (default: `daily_new_prospects_target`).
5. **Compliance.** `python scripts/compliance.py leads --stage Qualified`. Only `passed` IDs continue.
   Draft no more first touches than today's total remaining capacity (`inbox_router.py status`, summing
   `remaining`) plus 20% slack. If no inboxes are configured yet, draft at most 10 for review.
6. **Drafting.** Delegate to the `message-writer` agent with the passed IDs and the due follow-ups.
7. **Routing.** `python scripts/inbox_router.py assign`.
8. **Review gate.**
   - `review_mode = manual`: do **not** approve or send. Report the pending drafts in the summary.
   - `review_mode = auto`: `python scripts/compliance.py queue`, then `python scripts/queue_md.py approve --all`,
     then `python scripts/send.py --live`.
9. **Report.** Follow the daily-report skill: `python scripts/report.py`, then print the run summary.

If any script errors, show the error and continue with the steps that don't depend on it. Never work around a
script by editing CSVs directly.

---
name: enrichment
description: Find the decision-maker and a deliverable email for Sourced leads from their own website or public profiles, verify the domain accepts mail, record readiness signals, then ICP-score them. Use after city-prospector, or when leads are stuck in Sourced.
---

# Enrichment

Turn `Sourced` leads into `Enriched` leads with a named decision-maker and a verified email. Then score them into
`Qualified` or `Disqualified`.

## Steps

1. `python scripts/crm.py list --stage Sourced --json`, and work through the leads (cap at ~40 per run).
2. For each lead, WebFetch in this order: the `/about`, `/team`, `/our-team`, `/contact`, and `/leadership` pages, then the homepage footer.
   If needed, use WebSearch for `"<company>" <City> founder OR owner OR CEO` and `site:linkedin.com/in "<company>"`.
3. Decide on **one** decision-maker: owner / founder / CEO / managing partner / broker of record / clinic owner /
   head of sales or growth. Record `decision_maker` (full name) and `role`.
4. Email, in order of preference:
   - **Published** personal address on their site or listing, which gives `email_source=published`.
   - **Published** generic address (info@, hello@), which also gives `email_source=published`. Acceptable, but lower reply odds.
   - **Pattern** (UK leads only; CASL forbids this for Canada). Infer the company format from any published
     address (`first@`, `first.last@`, `flast@`), apply it to the decision-maker, and set `email_source=pattern`.
     If there's no evidence of the pattern, use `first@domain` and add the note "pattern guessed, no evidence".
   - Found nothing usable: set stage `Disqualified` with a note "no reachable email".
5. While on the site, add readiness `signals` (keys from `config/icp.json`), each with a short evidence note in
   `signal_notes`:
   - careers page lists a sales/BD/growth role gives `hiring_growth_role`
   - Meta/Google ad pixels or "as seen on" ads but no sign of outbound gives `paid_ads_no_outbound` (only if observed)
   - copyright year 2+ years old, broken forms, or a dated design gives `stale_website_or_crm`
   - founder posts about leads, pipeline, or growth on LinkedIn gives `founder_posts_about_pipeline`
   - an owner's direct email or phone is listed gives `owner_reachable_directly`
6. Save each lead:
   ```
   python scripts/crm.py update L-00012 --set decision_maker="Jane Doe" role=Founder email=jane@acme.ca email_source=published "signals=sells_to_businesses_confirmed; hiring_growth_role" "signal_notes=Careers page: BD Manager (Sep 2026)" stage=Enriched
   ```
   Keep existing signals and append new ones (`crm.py get` first).
7. Verify every new email: `python scripts/verify_email.py --leads`. Emails with `no-mx` / `invalid-syntax` will be
   blocked by compliance, so try to find a better address, or move those leads to `Disqualified`.
8. Score: `python scripts/crm.py score`. Enriched leads move to `Qualified` (score >= `min_icp_score`) or `Disqualified`.

## Accuracy notes

Sourcing has no paid safety net, so in Phase 1, list every `pattern` email in the run summary for spot-checking. Also
flag any lead where the name/role came from a source older than about 12 months.

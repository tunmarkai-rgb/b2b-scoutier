---
name: city-prospector
description: Source new B2B businesses (owner-led companies selling products or services to other businesses) in the active city using web search, and add them to the CRM as Sourced leads. Use when topping up the prospect pool or when asked to find businesses in a city or category.
---

# City Prospector

Goal: add up to `daily_new_prospects_target` (see `config/settings.json`) **new, non-duplicate** businesses
from the active city in `config/cities.json` that fit the ICP in `CLAUDE.md`.

## Steps

1. Read `config/cities.json` and take the entry with `"status": "active"`. Read the ICP section of `CLAUDE.md`.
2. Check what's already in the CRM so you don't waste searches:
   `python scripts/crm.py list --city "<City>"`. Note which categories are thin.
3. Rotate categories. Pick 2 or 3 priority categories per run, favouring the ones with the fewest leads.
   For each one, run several WebSearch queries, for example:
   - `"<category>" "<City>" B2B` / `"<category> agency" <City>`
   - `site:linkedin.com/company "<City>" <category> 11-50 employees`
   - `<City> <industry> association members directory`
   - `wholesale supplier <City> <product type>` / `<City> manufacturer "trade accounts"`
   - Readiness hunting: `"<City>" hiring "business development" OR "sales manager" <category>`
   - Google Business / Yelp / Clutch / chamber-of-commerce listings for the city
4. For each candidate, WebFetch the homepage (and the About page if needed) just long enough to confirm:
   - it **sells to businesses** (look for trade/wholesale accounts, "for businesses", B2B clients, case studies).
     Tag `sells_to_businesses_confirmed` only if you saw evidence. Tag `sells_only_to_consumers` if it clearly doesn't.
   - it's plausibly 5 to 50 people (team page, LinkedIn size band). Record `employees` as a number or range like `11-50`.
   - it's independent/owner-led, not a franchise location or an enterprise.
5. Write the batch to `outreach/work/prospects-<YYYY-MM-DD>-<n>.json` as a JSON list:
   ```json
   [{"company": "Acme Displays", "website": "https://acmedisplays.ca", "city": "Toronto", "country": "CA",
     "category": "b2b_products_other", "sells_what": "custom retail display fixtures for stores",
     "employees": "11-50", "source": "clutch.co listing", "signals": ["sells_to_businesses_confirmed"],
     "signal_notes": "Case studies with 3 retail chains; 'Trade accounts' page"}]
   ```
   Use `country` codes `CA` or `UK`. `category` and `signals` must use the keys from `config/icp.json`.
6. Import it: `python scripts/crm.py add outreach/work/prospects-<...>.json`. The script dedupes against
   existing leads and the suppression/DNC lists. Report how many were added and skipped.

## Quality bar

- 20 real, verifiable businesses beat 60 scraped names. Skip anything you couldn't open or confirm.
- Never add a company without a working website/domain, since the domain is the dedupe key.
- Exclude other lead-gen/outbound/appointment-setting agencies (`direct_competitor`).

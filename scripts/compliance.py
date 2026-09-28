#!/usr/bin/env python3
"""Pre-send compliance gate. It runs before drafting (per lead) and again inside
send.py right before every single message goes out.

Rules enforced:
  - never contact anyone on suppression-list.csv or do-not-contact.csv (email, domain or company)
  - never contact a lead who has replied, is closed, or has been disqualified
  - one sequence per lead: first touch only if never contacted, at most `max_touches`
  - the email must be verified (valid MX) and must not have bounced
  - country must be in settings.allowed_countries
  - Canada (CASL): no express consent, so we rely on implied consent by
    conspicuous publication. The address must be published by the business
    (email_source=published), and the message must relate to the recipient's business role.
  - UK (PECR / UK GDPR): corporate addresses are allowed under legitimate interest,
    with honest identification and an easy opt-out
  - sender identity, physical address and opt-out line must be filled in (no TODO)

Usage:
    python scripts/compliance.py lead L-00001 [--touch 1]
    python scripts/compliance.py leads [--stage Qualified]
    python scripts/compliance.py queue          # check active drafts, mark failures `blocked`
"""
import argparse
import sys

import queue_md
from common import CLOSED_STAGES, blocklists, has_placeholder, load_settings, print_json, read_csv


def sender_problems(settings):
    s = settings["sender"]
    return [f"sender.{k} not filled in (config/settings.json)"
            for k in ("name", "company", "physical_address", "opt_out_line", "website")
            if not s.get(k) or has_placeholder(s.get(k))]


def check_lead(row, settings, lists, touch=None):
    emails, domains, companies = lists
    reasons = []
    touch = touch or int(row["touch_count"] or 0) + 1
    if not row["email"]:
        reasons.append("no email address")
    if row["email"] in emails or row["domain"] in domains or row["company"].strip().lower() in companies:
        reasons.append("on suppression / do-not-contact list")
    if row["email_status"] == "bounced":
        reasons.append("email previously bounced")
    elif row["email_status"] != "valid-mx":
        reasons.append(f"email not verified (status: {row['email_status'] or 'unverified'})")
    if row["stage"] in CLOSED_STAGES:
        reasons.append(f"stage is {row['stage']} (sequence stopped)")
    if touch == 1 and int(row["touch_count"] or 0) > 0:
        reasons.append("already contacted; only follow-ups allowed")
    if touch > settings["max_touches"]:
        reasons.append(f"touch {touch} exceeds max_touches {settings['max_touches']}")
    if touch > 1 and row["stage"] not in ("Contacted", "Follow-up"):
        reasons.append(f"follow-up requires stage Contacted/Follow-up, is {row['stage']}")
    country = row["country"].strip().upper()
    if country == "GB":
        country = "UK"
    if country not in settings["allowed_countries"]:
        reasons.append(f"country '{row['country']}' not in allowed_countries")
    if country == "CA" and row["email_source"] != "published":
        reasons.append("CASL: Canadian address must be conspicuously published by the business "
                       "(email_source=published); guessed addresses are not allowed")
    if touch == 1 and row["stage"] != "Qualified":
        reasons.append(f"first touch requires stage Qualified, is {row['stage'] or 'blank'}")
    reasons += sender_problems(settings)
    return reasons


def check_draft(draft, lead, settings, lists):
    reasons = []
    if not lead:
        return ["lead not found in prospects.csv"]
    if draft["to"].strip().lower() != lead["email"]:
        reasons.append("draft recipient does not match lead email")
    if not draft["subject"].strip() and int(draft["touch"] or 1) == 1:
        reasons.append("empty subject")
    if len(draft["body"].strip()) < 40:
        reasons.append("body too short")
    if has_placeholder(draft["body"]) or has_placeholder(draft["subject"]):
        reasons.append("unfilled placeholder in draft ([...] or TODO)")
    reasons += check_lead(lead, settings, lists, touch=int(draft["touch"] or 1))
    return reasons


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("lead"); one.add_argument("lead_id"); one.add_argument("--touch", type=int)
    many = sub.add_parser("leads"); many.add_argument("--stage", default="Qualified")
    sub.add_parser("queue")
    args = p.parse_args()

    settings = load_settings()
    lists = blocklists()
    leads = {r["lead_id"]: r for r in read_csv("prospects")}

    if args.cmd == "lead":
        lead = leads.get(args.lead_id)
        if not lead:
            print_json({"lead_id": args.lead_id, "pass": False, "reasons": ["not found"]})
            sys.exit(1)
        reasons = check_lead(lead, settings, lists, args.touch)
        print_json({"lead_id": args.lead_id, "pass": not reasons, "reasons": reasons})
        sys.exit(0 if not reasons else 1)

    if args.cmd == "leads":
        out = []
        for lead in leads.values():
            if lead["stage"] == args.stage:
                reasons = check_lead(lead, settings, lists)
                out.append({"lead_id": lead["lead_id"], "company": lead["company"],
                            "pass": not reasons, "reasons": reasons})
        print_json({"passed": [o["lead_id"] for o in out if o["pass"]],
                    "blocked": [o for o in out if not o["pass"]]})
        return

    drafts = queue_md.load()
    result = {"passed": [], "blocked": []}
    for d in drafts:
        if d["status"] not in queue_md.ACTIVE:
            continue
        reasons = check_draft(d, leads.get(d["lead_id"]), settings, lists)
        if reasons:
            d["status"] = "blocked"
            d["note"] = "; ".join(reasons)
            result["blocked"].append({"id": d["id"], "reasons": reasons})
        else:
            result["passed"].append(d["id"])
    queue_md.save(drafts)
    print_json(result)


if __name__ == "__main__":
    main()

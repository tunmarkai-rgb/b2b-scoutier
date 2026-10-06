#!/usr/bin/env python3
"""Flat-file CRM. This is the only code path skills use to change contacts/*.csv.

Usage:
    python scripts/crm.py add prospects.json          # list of prospect dicts (or "-" for stdin)
    python scripts/crm.py update L-00001 --set stage=Enriched email=a@b.com [--note "text"]
    python scripts/crm.py get L-00001
    python scripts/crm.py list [--stage Qualified] [--city Toronto] [--json]
    python scripts/crm.py score [--all]              # ICP-score Enriched leads -> Qualified/Disqualified
    python scripts/crm.py due-followups               # writes outreach/queue/follow-up-queue.md
    python scripts/crm.py suppress EMAIL_OR_DOMAIN --reason "unsubscribe"
    python scripts/crm.py dnc --company X --domain x.com [--email] --reason "existing client"
    python scripts/crm.py hot L-00001 --classification interested --summary "..." [--next-action "..."] [--stage "Call Booked"]
    python scripts/crm.py stats
"""
import argparse
import json
import sys
from datetime import date, timedelta

import queue_md
from common import (CLOSED_STAGES, CONFIG, FOLLOWUP_FILE, HEADERS, STAGES, append_csv,
                    blocklists, die, domain_of, load_json, load_settings, norm_email,
                    now_iso, print_json, read_csv, today_str, write_csv)

PROTECTED = {"lead_id", "created_at"}


def _load_items(path):
    if path == "-":
        data = json.load(sys.stdin)
    else:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    return [data] if isinstance(data, dict) else data


def _clean(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def _find(rows, lead_id):
    for row in rows:
        if row["lead_id"] == lead_id:
            return row
    die(f"lead {lead_id} not found")


def _apply(row, updates):
    for key, val in updates.items():
        if key in PROTECTED or key not in row:
            die(f"field '{key}' is not editable")
        if key == "stage" and val not in STAGES:
            die(f"invalid stage '{val}'. Valid: {', '.join(STAGES)}")
        if key == "email":
            val = norm_email(val)
        if key == "domain":
            val = domain_of(val)
        row[key] = val
    row["updated_at"] = now_iso()


def cmd_add(args):
    items = _load_items(args.json)
    rows = read_csv("prospects")
    bl_emails, bl_domains, bl_companies = blocklists()
    seen_domains = {r["domain"] for r in rows if r["domain"]}
    seen_emails = {r["email"] for r in rows if r["email"]}
    seen_companies = {(r["company"].lower(), r["city"].lower()) for r in rows}
    n = max([int(r["lead_id"][2:]) for r in rows if r["lead_id"].startswith("L-")] or [0])
    added, skipped = [], []
    for item in items:
        company = _clean(item.get("company"))
        domain = domain_of(item.get("domain") or item.get("website") or item.get("email"))
        email = norm_email(item.get("email"))
        city = _clean(item.get("city"))
        why = None
        if not company:
            why = "missing company"
        elif domain in bl_domains or email in bl_emails or company.lower() in bl_companies:
            why = "on suppression/do-not-contact list"
        elif (domain and domain in seen_domains) or (email and email in seen_emails) \
                or (company.lower(), city.lower()) in seen_companies:
            why = "duplicate"
        if why:
            skipped.append({"company": company, "reason": why})
            continue
        n += 1
        row = {h: "" for h in HEADERS["prospects"]}
        for key, val in item.items():
            if key in row and key not in PROTECTED:
                row[key] = _clean(val)
        stage = row["stage"] or "Sourced"
        if stage not in STAGES:
            stage = "Sourced"
        row.update(lead_id=f"L-{n:05d}", company=company, domain=domain, email=email,
                   stage=stage, touch_count="0", created_at=now_iso(), updated_at=now_iso())
        rows.append(row)
        seen_domains.add(domain)
        seen_emails.add(email)
        seen_companies.add((company.lower(), city.lower()))
        added.append(row["lead_id"])
    write_csv("prospects", rows)
    print_json({"added": added, "skipped": skipped})


def cmd_update(args):
    rows = read_csv("prospects")
    row = _find(rows, args.lead_id)
    updates = {}
    for pair in args.set or []:
        key, sep, val = pair.partition("=")
        if not sep:
            die(f"expected key=value, got '{pair}'")
        updates[key.strip()] = val.strip()
    _apply(row, updates)
    if args.note:
        stamp = today_str()
        row["notes"] = (row["notes"] + " | " if row["notes"] else "") + f"{stamp}: {args.note}"
    if row["stage"] in CLOSED_STAGES:
        row["next_follow_up"] = ""
    write_csv("prospects", rows)
    print_json(row)


def cmd_get(args):
    print_json(_find(read_csv("prospects"), args.lead_id))


def cmd_list(args):
    rows = read_csv("prospects")
    if args.stage:
        rows = [r for r in rows if r["stage"] == args.stage]
    if args.city:
        rows = [r for r in rows if r["city"].lower() == args.city.lower()]
    if args.json:
        print_json(rows)
        return
    for r in rows:
        print(f"{r['lead_id']}  {r['stage']:<13} {r['icp_score'] or '-':>3}  {r['company']} "
              f"({r['city']})  {r['decision_maker']} <{r['email']}> [{r['email_status'] or 'unverified'}]")
    print(f"{len(rows)} lead(s)")


def score_row(row, icp):
    """Deterministic ICP score from icp.json. Returns (score, disqualified_reason)."""
    signals = {s.strip() for s in row["signals"].split(";") if s.strip()}
    for dq in icp["disqualifiers"]:
        if dq in signals:
            return 0, dq
    score = icp["categories"].get(row["category"], icp["categories"].get("other", 0))
    lo, hi = icp["employee_range"]
    try:
        emp = int(str(row["employees"]).split("-")[0].replace("+", "").strip())
        if lo <= emp <= hi:
            score += icp["size_points"]["in_range"]
        elif lo * 0.5 <= emp <= hi * 2:
            score += icp["size_points"]["near_range"]
    except ValueError:
        score += icp["size_points"]["unknown"]
    score += sum(icp["signals"].get(s, 0) for s in signals)
    return min(score, 100), None


def cmd_score(args):
    icp = load_json(CONFIG / "icp.json")
    settings = load_settings()
    threshold = settings["min_icp_score"]
    rows = read_csv("prospects")
    results = []
    for row in rows:
        if not args.all and row["stage"] != "Enriched":
            continue
        if row["stage"] in CLOSED_STAGES | {"Contacted", "Follow-up"}:
            continue
        score, dq = score_row(row, icp)
        row["icp_score"] = str(score)
        if row["stage"] == "Enriched":
            row["stage"] = "Qualified" if (score >= threshold and not dq) else "Disqualified"
            if dq:
                row["notes"] = (row["notes"] + " | " if row["notes"] else "") + f"disqualified: {dq}"
        row["updated_at"] = now_iso()
        results.append({"lead_id": row["lead_id"], "company": row["company"],
                        "score": score, "stage": row["stage"], "disqualifier": dq})
    write_csv("prospects", rows)
    print_json({"threshold": threshold, "scored": results})


def cmd_due_followups(_args):
    settings = load_settings()
    max_touches = settings["max_touches"]
    today = today_str()
    due = [r for r in read_csv("prospects")
           if r["stage"] in ("Contacted", "Follow-up") and r["next_follow_up"]
           and r["next_follow_up"] <= today and int(r["touch_count"] or 0) < max_touches]
    lines = ["# Follow-up Queue", "", f"Generated {now_iso()}. Leads due for touch 2/3 today.", "",
             "| lead_id | company | contact | email | touch due | last touch | inbox |",
             "|---|---|---|---|---|---|---|"]
    for r in due:
        lines.append(f"| {r['lead_id']} | {r['company']} | {r['decision_maker']} | {r['email']} | "
                     f"{int(r['touch_count'] or 0) + 1} | {r['last_touch']} | {r['assigned_inbox']} |")
    FOLLOWUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    FOLLOWUP_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print_json([{"lead_id": r["lead_id"], "company": r["company"], "email": r["email"],
                 "touch": int(r["touch_count"] or 0) + 1, "inbox": r["assigned_inbox"]} for r in due])


def cmd_suppress(args):
    target = args.target.strip().lower()
    is_email = "@" in target
    append_csv("suppression", {"email": target if is_email else "",
                               "domain": "" if is_email else domain_of(target),
                               "reason": args.reason, "added_at": now_iso()})
    rows = read_csv("prospects")
    touched = []
    for row in rows:
        if (is_email and row["email"] == target) or (not is_email and row["domain"] == domain_of(target)):
            row["stage"] = "Lost"
            row["next_follow_up"] = ""
            row["notes"] = (row["notes"] + " | " if row["notes"] else "") + f"{today_str()}: suppressed ({args.reason})"
            row["updated_at"] = now_iso()
            queue_md.cancel_for_lead(row["lead_id"], f"suppressed: {args.reason}")
            touched.append(row["lead_id"])
    write_csv("prospects", rows)
    print_json({"suppressed": target, "leads_closed": touched})


def cmd_dnc(args):
    if not (args.company or args.domain or args.email):
        die("give at least one of --company/--domain/--email")
    append_csv("dnc", {"company": args.company or "", "domain": domain_of(args.domain or ""),
                       "email": norm_email(args.email or ""), "reason": args.reason, "added_at": now_iso()})
    print_json({"dnc_added": [args.company, args.domain, args.email]})


def cmd_hot(args):
    rows = read_csv("prospects")
    row = _find(rows, args.lead_id)
    append_csv("hot_leads", {
        "lead_id": row["lead_id"], "company": row["company"], "decision_maker": row["decision_maker"],
        "email": row["email"], "reply_date": args.reply_date or today_str(),
        "classification": args.classification, "summary": args.summary,
        "next_action": args.next_action or "", "added_at": now_iso()})
    _apply(row, {"stage": args.stage})
    row["next_follow_up"] = ""
    queue_md.cancel_for_lead(row["lead_id"], "lead replied")
    write_csv("prospects", rows)
    print_json(row)


def cmd_stats(_args):
    print_json(compute_stats())


def compute_stats():
    rows = read_csv("prospects")
    sends = [c for c in read_csv("contacted") if c["status"] == "sent"]
    today = today_str()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    contacted_leads = {c["lead_id"] for c in sends}
    replied = [r for r in rows if r["lead_id"] in contacted_leads and
               (r["stage"] in {"Replied", "Interested", "Call Booked", "Proposal Sent", "Won"}
                or "replied" in r["notes"].lower())]
    bounced = [r for r in rows if r["email_status"] == "bounced"]
    by_stage = {s: sum(1 for r in rows if r["stage"] == s) for s in STAGES}
    return {
        "leads_total": len(rows), "by_stage": by_stage,
        "sent_today": sum(1 for c in sends if c["timestamp"].startswith(today)),
        "sent_7d": sum(1 for c in sends if c["timestamp"][:10] >= week_ago),
        "sent_total": len(sends), "leads_contacted": len(contacted_leads),
        "leads_replied": len(replied),
        "reply_rate": round(len(replied) / len(contacted_leads), 3) if contacted_leads else 0,
        "bounced": len(bounced),
        "bounce_rate": round(len(bounced) / len(contacted_leads), 3) if contacted_leads else 0,
        "hot_leads": len(read_csv("hot_leads")),
        "due_follow_ups": sum(1 for r in rows if r["stage"] in ("Contacted", "Follow-up")
                              and r["next_follow_up"] and r["next_follow_up"] <= today),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("json")
    u = sub.add_parser("update"); u.add_argument("lead_id"); u.add_argument("--set", nargs="*"); u.add_argument("--note")
    g = sub.add_parser("get"); g.add_argument("lead_id")
    l = sub.add_parser("list"); l.add_argument("--stage"); l.add_argument("--city"); l.add_argument("--json", action="store_true")
    s = sub.add_parser("score"); s.add_argument("--all", action="store_true", help="re-score every open lead")
    sub.add_parser("due-followups")
    sp = sub.add_parser("suppress"); sp.add_argument("target"); sp.add_argument("--reason", default="unsubscribe")
    d = sub.add_parser("dnc"); d.add_argument("--company"); d.add_argument("--domain"); d.add_argument("--email"); d.add_argument("--reason", default="existing client")
    h = sub.add_parser("hot"); h.add_argument("lead_id"); h.add_argument("--classification", required=True)
    h.add_argument("--summary", required=True); h.add_argument("--next-action"); h.add_argument("--reply-date")
    h.add_argument("--stage", default="Interested")
    sub.add_parser("stats")
    args = p.parse_args()
    {"add": cmd_add, "update": cmd_update, "get": cmd_get, "list": cmd_list, "score": cmd_score,
     "due-followups": cmd_due_followups, "suppress": cmd_suppress, "dnc": cmd_dnc,
     "hot": cmd_hot, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    main()

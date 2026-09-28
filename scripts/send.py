#!/usr/bin/env python3
"""Send approved drafts from outreach/queue/outreach-queue.md through Gmail SMTP.

Safe by default: without --live nothing is sent; rendered messages are written
to outreach/dry-run-preview.md instead.

For every message it (1) holds the inbox's send-lock, (2) re-counts today's sends
from the Gmail Sent folder (ground truth) and stops at the cap, (3) re-runs the
compliance gate, (4) appends the sender identity + opt-out footer, and (5) logs to
contacted.csv, sent-log.md and prospects.csv straight after each send.

Usage:
    python scripts/send.py                 # dry run
    python scripts/send.py --live          # really send
    python scripts/send.py --live --inbox tm1 --limit 5
"""
import argparse
import random
import smtplib
import time
from datetime import date, timedelta
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import queue_md
from common import (OUTREACH, SENT_LOG, append_csv, blocklists, load_settings, now_iso,
                    print_json, read_csv, today_str, write_csv)
from compliance import check_draft
from mail_utils import SendLock, count_sent_today, daily_cap, load_inboxes, password_for


def footer(settings):
    s = settings["sender"]
    title = f", {s['title']}" if s.get("title") else ""
    return (f"--\n{s['name']}{title} | {s['company']}\n{s['website']}\n"
            f"{s['physical_address']}\n\n{s['opt_out_line']}")


def last_thread(contacted, lead_id):
    sent = [c for c in contacted if c["lead_id"] == lead_id and c["status"] == "sent" and c["message_id"]]
    if not sent:
        return None
    return {"first_subject": sent[0]["subject"], "ids": [c["message_id"] for c in sent]}


def build_message(draft, inbox, settings, thread):
    msg = EmailMessage()
    msg["From"] = formataddr((inbox.get("display_name") or settings["sender"]["name"], inbox["address"]))
    msg["To"] = formataddr((draft["name"], draft["to"])) if draft["name"] else draft["to"]
    subject = draft["subject"]
    if thread:
        subject = subject or thread["first_subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        msg["In-Reply-To"] = thread["ids"][-1]
        msg["References"] = " ".join(thread["ids"])
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=inbox["address"].split("@", 1)[1])
    msg["List-Unsubscribe"] = f"<mailto:{inbox['address']}?subject=unsubscribe>"
    msg.set_content(f"{draft['body'].strip()}\n\n{footer(settings)}\n")
    return msg


def log_sent(draft, msg, inbox_id):
    SENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    if not SENT_LOG.exists():
        SENT_LOG.write_text("# Sent Log\n\nAppend-only record of every message sent.\n\n", encoding="utf-8")
    with open(SENT_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"## {now_iso()} | {inbox_id} -> {draft['to']}\n"
                 f"- lead: {draft['lead_id']} ({draft['company']})\n- draft: {draft['id']}\n"
                 f"- touch: {draft['touch']}\n- subject: {msg['Subject']}\n"
                 f"- message_id: {msg['Message-ID']}\n\n```\n{msg.get_content().strip()}\n```\n\n")


def update_lead(lead, draft, settings):
    touch = int(draft["touch"] or 1)
    lead["touch_count"] = str(touch)
    lead["last_touch"] = today_str()
    lead["assigned_inbox"] = draft["inbox"]
    lead["stage"] = "Contacted" if touch == 1 else "Follow-up"
    gaps = settings["follow_up_days"]
    if touch < settings["max_touches"] and touch - 1 < len(gaps):
        lead["next_follow_up"] = (date.today() + timedelta(days=gaps[touch - 1])).isoformat()
    else:
        lead["next_follow_up"] = ""
    lead["updated_at"] = now_iso()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", help="actually send (default is a dry run)")
    p.add_argument("--inbox", help="only send from this inbox id")
    p.add_argument("--limit", type=int, help="max messages this run")
    p.add_argument("--no-delay", action="store_true", help="skip the randomized gap between sends")
    args = p.parse_args()

    settings = load_settings()
    inboxes = {i["id"]: i for i in load_inboxes()}
    drafts = queue_md.load()
    todo = [d for d in drafts if d["status"] == "approved" and d["inbox"]
            and (not args.inbox or d["inbox"] == args.inbox)]
    if not todo:
        print_json({"sent": [], "note": "no approved drafts with an assigned inbox"})
        return

    rows = read_csv("prospects")
    leads = {r["lead_id"]: r for r in rows}
    contacted = read_csv("contacted")
    lists = blocklists()
    today = today_str()
    budget = args.limit if args.limit is not None else 10 ** 9
    report = {"mode": "live" if args.live else "dry-run", "sent": [], "blocked": [],
              "failed": [], "held_for_cap": [], "inbox_errors": {}}
    preview = []

    for inbox_id in sorted({d["inbox"] for d in todo}):
        inbox = inboxes.get(inbox_id)
        group = [d for d in todo if d["inbox"] == inbox_id]
        if not inbox:
            report["inbox_errors"][inbox_id] = "inbox missing or disabled in inboxes.json"
            continue
        with SendLock(inbox_id):
            logged = sum(1 for c in contacted if c["inbox"] == inbox_id and c["status"] == "sent"
                         and c["timestamp"].startswith(today))
            smtp = None
            if args.live:
                try:
                    sent_today = max(logged, count_sent_today(inbox))
                    smtp = smtplib.SMTP(inbox.get("smtp_host", "smtp.gmail.com"), int(inbox.get("smtp_port", 587)), timeout=60)
                    smtp.starttls()
                    smtp.login(inbox["address"], password_for(inbox))
                except Exception as exc:
                    report["inbox_errors"][inbox_id] = f"cannot verify Sent folder / log in: {exc}"
                    continue
            else:
                sent_today = logged
            remaining = daily_cap(inbox) - sent_today
            try:
                for i, d in enumerate(group):
                    if budget <= 0:
                        break
                    if remaining <= 0:
                        report["held_for_cap"].append(d["id"])
                        continue
                    lead = leads.get(d["lead_id"])
                    reasons = check_draft(d, lead, settings, lists)
                    if reasons:
                        d["status"], d["note"] = "blocked", "; ".join(reasons)
                        report["blocked"].append({"id": d["id"], "reasons": reasons})
                        queue_md.save(drafts)
                        continue
                    msg = build_message(d, inbox, settings, last_thread(contacted, d["lead_id"]) if int(d["touch"] or 1) > 1 else None)
                    if not args.live:
                        preview.append(f"## {d['id']} (inbox {inbox_id})\n\n```\n{msg.as_string()}\n```\n")
                        report["sent"].append({"id": d["id"], "to": d["to"], "inbox": inbox_id})
                        remaining -= 1
                        budget -= 1
                        continue
                    try:
                        smtp.send_message(msg)
                    except smtplib.SMTPRecipientsRefused as exc:
                        d["status"], d["note"] = "failed", f"recipient refused: {exc}"
                        lead["email_status"], lead["stage"], lead["next_follow_up"] = "bounced", "Lost", ""
                        report["failed"].append({"id": d["id"], "error": "recipient refused"})
                        queue_md.save(drafts)
                        write_csv("prospects", rows)
                        continue
                    except smtplib.SMTPException as exc:
                        d["status"], d["note"] = "failed", f"smtp error: {exc}"
                        report["failed"].append({"id": d["id"], "error": str(exc)})
                        queue_md.save(drafts)
                        break
                    row = {"timestamp": now_iso(), "lead_id": d["lead_id"], "email": d["to"],
                           "company": d["company"], "inbox": inbox_id, "touch": d["touch"],
                           "subject": msg["Subject"], "message_id": msg["Message-ID"],
                           "status": "sent", "draft_id": d["id"]}
                    append_csv("contacted", row)
                    contacted.append(row)
                    log_sent(d, msg, inbox_id)
                    d["status"], d["sent_at"], d["message_id"] = "sent", row["timestamp"], msg["Message-ID"]
                    update_lead(lead, d, settings)
                    queue_md.save(drafts)
                    write_csv("prospects", rows)
                    report["sent"].append({"id": d["id"], "to": d["to"], "inbox": inbox_id})
                    remaining -= 1
                    budget -= 1
                    if not args.no_delay and i < len(group) - 1 and remaining > 0 and budget > 0:
                        time.sleep(random.uniform(*settings["send_delay_seconds"]))
            finally:
                if smtp:
                    try:
                        smtp.quit()
                    except Exception:
                        pass

    if args.live:
        queue_md.cmd_archive()
    elif preview:
        path = OUTREACH / "dry-run-preview.md"
        path.write_text(f"# Dry-run preview {now_iso()}\n\nNothing was sent.\n\n" + "\n".join(preview), encoding="utf-8")
        report["preview_file"] = str(path)
    print_json(report)


if __name__ == "__main__":
    main()

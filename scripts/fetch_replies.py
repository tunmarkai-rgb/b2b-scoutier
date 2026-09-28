#!/usr/bin/env python3
"""Pull new replies and bounces from every inbox over IMAP (read-only, nothing is
marked as read). Matches each one to a lead and applies the deterministic rules:

  - a human reply stops that lead's sequence immediately (stage -> Replied)
  - a bounce marks the email `bounced` and closes the lead
  - auto-replies (out-of-office) are flagged but do not stop the sequence

Classification (interested / not now / unsubscribe / referral ...) is left to the
reply-classifier skill, which reads outreach/replies/replies-YYYY-MM-DD.json.

Usage:
    python scripts/fetch_replies.py [--days 14] [--dry-run]
"""
import argparse
import email
import json
import re
from datetime import date, timedelta
from email import policy
from email.utils import parseaddr

import queue_md
from common import REPLIES_DIR, domain_of, load_settings, now_iso, print_json, read_csv, today_str, write_csv
from mail_utils import imap_connect, load_inboxes

BOUNCE_FROM = re.compile(r"mailer-daemon|postmaster|mail-delivery", re.I)
BOUNCE_SUBJ = re.compile(r"delivery status notification|undeliver|mail delivery failed|returned mail|failure notice", re.I)
AUTO_SUBJ = re.compile(r"out of (the )?office|automatic reply|auto[- ]?reply|autoreply|away from", re.I)
EMAIL_IN_TEXT = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
QUOTE_START = re.compile(r"^(On .+wrote:|-{2,} ?Original Message|From: .+|Sent from my )", re.I)


def body_text(msg):
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        text = re.sub(r"<(br|/p|/div)[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
    lines = []
    for line in text.splitlines():
        if QUOTE_START.match(line.strip()):
            break
        if not line.startswith(">"):
            lines.append(line)
    return "\n".join(lines).strip()[:3000]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", type=int)
    p.add_argument("--dry-run", action="store_true", help="report only; do not update the CRM")
    args = p.parse_args()
    days = args.days or load_settings()["reply_lookback_days"]

    inboxes = load_inboxes()
    if not inboxes:
        print_json({"replies": [], "note": "no inboxes configured in inboxes.json"})
        return

    sent = [c for c in read_csv("contacted") if c["status"] == "sent"]
    by_email = {c["email"].lower(): c["lead_id"] for c in sent}
    domain_leads = {}
    for c in sent:
        domain_leads.setdefault(domain_of(c["email"]), set()).add(c["lead_id"])
    by_domain = {d: next(iter(ids)) for d, ids in domain_leads.items() if len(ids) == 1}
    ours = {i["address"].lower() for i in load_inboxes(enabled_only=False)}

    REPLIES_DIR.mkdir(parents=True, exist_ok=True)
    processed_file = REPLIES_DIR / "processed-ids.txt"
    processed = set(processed_file.read_text(encoding="utf-8").split()) if processed_file.exists() else set()
    since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
    found, errors, newly_processed = [], {}, []

    for inbox in inboxes:
        try:
            conn = imap_connect(inbox)
        except Exception as exc:
            errors[inbox["id"]] = str(exc)
            continue
        try:
            conn.select("INBOX", readonly=True)
            status, data = conn.search(None, "SINCE", since)
            for num in (data[0].split() if status == "OK" and data[0] else []):
                status, parts = conn.fetch(num, "(BODY.PEEK[])")
                if status != "OK" or not parts or not isinstance(parts[0], tuple):
                    continue
                msg = email.message_from_bytes(parts[0][1], policy=policy.default)
                mid = (msg["Message-ID"] or f"{inbox['id']}:{num.decode()}").strip()
                if mid in processed:
                    continue
                processed.add(mid)
                newly_processed.append(mid)
                sender = parseaddr(str(msg["From"] or ""))[1].lower()
                if sender in ours:
                    continue
                subject = str(msg["Subject"] or "")
                text = body_text(msg)
                kind, lead_id = "reply", None
                if BOUNCE_FROM.search(sender) or BOUNCE_SUBJ.search(subject):
                    kind = "bounce"
                    candidates = [str(msg["X-Failed-Recipients"] or "")] + EMAIL_IN_TEXT.findall(str(msg))
                    for cand in candidates:
                        lead_id = by_email.get(cand.strip().lower())
                        if lead_id:
                            break
                else:
                    lead_id = by_email.get(sender) or by_domain.get(domain_of(sender))
                    auto = str(msg["Auto-Submitted"] or "no").lower() != "no" or msg["X-Autoreply"] \
                        or msg["X-Autorespond"] or AUTO_SUBJ.search(subject)
                    if auto:
                        kind = "auto_reply"
                if not lead_id:
                    continue
                found.append({"inbox": inbox["id"], "message_id": mid, "from": sender,
                              "lead_id": lead_id, "type": kind, "subject": subject,
                              "date": str(msg["Date"] or ""), "text": text,
                              "matched_by": "email" if sender in by_email else ("bounce" if kind == "bounce" else "domain")})
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    if not args.dry_run and found:
        rows = read_csv("prospects")
        leads = {r["lead_id"]: r for r in rows}
        for item in found:
            lead = leads.get(item["lead_id"])
            if not lead:
                continue
            item["company"] = lead["company"]
            note = ""
            if item["type"] == "reply":
                if lead["stage"] in ("Contacted", "Follow-up"):
                    lead["stage"] = "Replied"
                lead["next_follow_up"] = ""
                note = f"replied from {item['from']}"
                queue_md.cancel_for_lead(lead["lead_id"], "lead replied")
            elif item["type"] == "bounce":
                lead["email_status"] = "bounced"
                lead["next_follow_up"] = ""
                if lead["stage"] in ("Contacted", "Follow-up"):
                    lead["stage"] = "Lost"
                note = "bounced; re-enrich if still worth pursuing"
                queue_md.cancel_for_lead(lead["lead_id"], "bounced")
            else:
                note = "auto-reply received (sequence continues)"
            lead["notes"] = (lead["notes"] + " | " if lead["notes"] else "") + f"{today_str()}: {note}"
            lead["updated_at"] = now_iso()
        write_csv("prospects", rows)

    if not args.dry_run:
        out = REPLIES_DIR / f"replies-{today_str()}.json"
        existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
        out.write_text(json.dumps(existing + found, indent=2, ensure_ascii=False), encoding="utf-8")
        with open(processed_file, "a", encoding="utf-8") as fh:
            fh.writelines(f"{m}\n" for m in newly_processed)

    print_json({"replies": found, "errors": errors,
                "counts": {k: sum(1 for f in found if f["type"] == k) for k in ("reply", "bounce", "auto_reply")}})


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read/write outreach/queue/outreach-queue.md.

The queue is a Markdown file so a human can review drafts in any editor, but it
has a strict shape so scripts can parse it:

    ## D-20260928-001
    - status: pending
    - lead_id: L-00001
    ...meta lines...

    Body text...
    <!-- end D-20260928-001 -->

To approve a draft, change `status: pending` to `status: approved`.

Usage:
    python scripts/queue_md.py add drafts.json      # list of {lead_id, subject, body[, touch]}
    python scripts/queue_md.py list [--status pending]
    python scripts/queue_md.py approve D-... D-...  |  --all
    python scripts/queue_md.py reject D-... [--reason text]
    python scripts/queue_md.py set D-... key=value
    python scripts/queue_md.py archive
"""
import argparse
import json
import re
import sys
from datetime import date

from common import (QUEUE_DIR, QUEUE_FILE, die, now_iso, print_json, read_csv,
                    today_str)

META_KEYS = ["status", "lead_id", "to", "name", "company", "inbox", "touch",
             "subject", "created", "sent_at", "message_id", "note"]
STATUSES = {"pending", "approved", "rejected", "blocked", "sent", "failed", "cancelled"}
ACTIVE = {"pending", "approved"}
DONE = {"sent", "rejected", "cancelled"}

HEADER = """# Outreach Queue

<!-- Review each draft. Change `- status: pending` to `- status: approved` to send it,
     or `rejected` to drop it. You may edit the subject and body. Keep the
     `## D-...` heading and the `<!-- end D-... -->` marker intact. -->
"""

BLOCK_RE = re.compile(r"^## (D-[\w-]+)\n(.*?)\n<!-- end \1 -->", re.S | re.M)


def load():
    if not QUEUE_FILE.exists():
        return []
    text = QUEUE_FILE.read_text(encoding="utf-8")
    drafts = []
    for match in BLOCK_RE.finditer(text):
        draft = {k: "" for k in META_KEYS}
        draft["id"] = match.group(1)
        lines = match.group(2).split("\n")
        i = 0
        while i < len(lines) and lines[i].startswith("- "):
            key, _, val = lines[i][2:].partition(":")
            draft[key.strip()] = val.strip()
            i += 1
        draft["body"] = "\n".join(lines[i:]).strip("\n")
        drafts.append(draft)
    return drafts


def render(draft):
    meta = "\n".join(f"- {k}: {draft.get(k, '')}" for k in META_KEYS)
    return f"## {draft['id']}\n{meta}\n\n{draft['body'].strip()}\n<!-- end {draft['id']} -->\n"


def save(drafts, path=QUEUE_FILE, header=HEADER):
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    body = "\n".join(render(d) for d in drafts)
    path.write_text(header + "\n" + body, encoding="utf-8")


def next_id(drafts):
    stamp = date.today().strftime("%Y%m%d")
    prefix = f"D-{stamp}-"
    used = [int(d["id"][len(prefix):]) for d in drafts if d["id"].startswith(prefix)]
    # Archived drafts keep their IDs too, so scan the archives as well.
    for arch in QUEUE_DIR.glob("archive-*.md"):
        used += [int(m) for m in re.findall(rf"^## {prefix}(\d+)", arch.read_text(encoding="utf-8"), re.M)]
    counter = max(used or [0])

    def gen():
        nonlocal counter
        counter += 1
        return f"{prefix}{counter:03d}"
    return gen


def cancel_for_lead(lead_id, reason):
    """Cancel any pending/approved drafts for a lead. Returns count cancelled."""
    drafts = load()
    count = 0
    for d in drafts:
        if d["lead_id"] == lead_id and d["status"] in ACTIVE:
            d["status"] = "cancelled"
            d["note"] = reason
            count += 1
    if count:
        save(drafts)
    return count


def cmd_add(args):
    if args.json == "-":
        items = json.load(sys.stdin)
    else:
        with open(args.json, encoding="utf-8") as fh:
            items = json.load(fh)
    if isinstance(items, dict):
        items = [items]
    leads = {r["lead_id"]: r for r in read_csv("prospects")}
    drafts = load()
    active_leads = {d["lead_id"] for d in drafts if d["status"] in ACTIVE}
    gen = next_id(drafts)
    added, skipped = [], []
    for item in items:
        lead = leads.get(item.get("lead_id", ""))
        if not lead:
            skipped.append({"lead_id": item.get("lead_id"), "reason": "unknown lead_id"})
            continue
        if lead["lead_id"] in active_leads:
            skipped.append({"lead_id": lead["lead_id"], "reason": "already has an active draft"})
            continue
        if not item.get("body"):
            skipped.append({"lead_id": lead["lead_id"], "reason": "empty body"})
            continue
        touch = int(item.get("touch") or int(lead["touch_count"] or 0) + 1)
        draft = {k: "" for k in META_KEYS}
        draft.update(
            id=gen(), status="pending", lead_id=lead["lead_id"], to=lead["email"],
            name=lead["decision_maker"], company=lead["company"],
            inbox=lead["assigned_inbox"] if touch > 1 else "", touch=str(touch),
            subject=(item.get("subject") or "").replace("\n", " ").strip(),
            created=now_iso(), body=item["body"],
        )
        drafts.append(draft)
        active_leads.add(lead["lead_id"])
        added.append(draft["id"])
    save(drafts)
    print_json({"added": added, "skipped": skipped})


def cmd_list(args):
    rows = [d for d in load() if not args.status or d["status"] == args.status]
    if args.json:
        print_json(rows)
        return
    for d in rows:
        print(f"{d['id']}  {d['status']:<9} touch {d['touch']}  {d['inbox'] or '-':<8} "
              f"{d['lead_id']}  {d['company']} <{d['to']}>  | {d['subject']}")
    print(f"{len(rows)} draft(s)")


def cmd_set_status(ids, status, all_pending=False, note=None):
    drafts = load()
    changed = []
    for d in drafts:
        if (all_pending and d["status"] == "pending") or d["id"] in ids:
            d["status"] = status
            if note:
                d["note"] = note
            changed.append(d["id"])
    save(drafts)
    print_json({status: changed})


def cmd_set(args):
    drafts = load()
    for d in drafts:
        if d["id"] == args.id:
            for pair in args.pairs:
                key, _, val = pair.partition("=")
                if key not in META_KEYS:
                    die(f"unknown key {key}")
                if key == "status" and val not in STATUSES:
                    die(f"invalid status {val}")
                d[key] = val
            save(drafts)
            print_json(d)
            return
    die(f"draft {args.id} not found")


def cmd_archive(_args=None):
    drafts = load()
    keep = [d for d in drafts if d["status"] not in DONE]
    done = [d for d in drafts if d["status"] in DONE]
    if done:
        arch = QUEUE_DIR / f"archive-{today_str()[:7]}.md"
        existing = arch.read_text(encoding="utf-8") if arch.exists() else f"# Queue archive {today_str()[:7]}\n\n"
        arch.write_text(existing + "\n".join(render(d) for d in done), encoding="utf-8")
    save(keep)
    print_json({"archived": len(done), "remaining": len(keep)})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("json")
    l = sub.add_parser("list"); l.add_argument("--status"); l.add_argument("--json", action="store_true")
    ap = sub.add_parser("approve"); ap.add_argument("ids", nargs="*"); ap.add_argument("--all", action="store_true")
    r = sub.add_parser("reject"); r.add_argument("ids", nargs="+"); r.add_argument("--reason")
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("pairs", nargs="+")
    sub.add_parser("archive")
    args = p.parse_args()
    if args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "approve":
        cmd_set_status(set(args.ids), "approved", all_pending=args.all)
    elif args.cmd == "reject":
        cmd_set_status(set(args.ids), "rejected", note=args.reason)
    elif args.cmd == "set":
        cmd_set(args)
    elif args.cmd == "archive":
        cmd_archive()


if __name__ == "__main__":
    main()

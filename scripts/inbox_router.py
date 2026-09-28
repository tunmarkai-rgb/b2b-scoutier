#!/usr/bin/env python3
"""Assign queued drafts to sending inboxes without exceeding any inbox's cap.

Capacity for today = warm-up cap - max(sent today per Gmail Sent folder,
sent today per contacted.csv) - drafts already assigned but not yet sent.
Follow-ups stay on the inbox that sent touch 1, so the thread is preserved. If
that inbox is full, the follow-up waits a day instead of switching inboxes.

Usage:
    python scripts/inbox_router.py status [--no-imap]
    python scripts/inbox_router.py assign [--no-imap]
"""
import argparse

import queue_md
from common import print_json, read_csv, today_str
from mail_utils import count_sent_today, daily_cap, load_inboxes


def capacity(use_imap=True):
    today = today_str()
    sends = read_csv("contacted")
    drafts = queue_md.load()
    table = {}
    for inbox in load_inboxes():
        logged = sum(1 for c in sends if c["inbox"] == inbox["id"] and c["status"] == "sent"
                     and c["timestamp"].startswith(today))
        imap_count, imap_error = None, None
        if use_imap:
            try:
                imap_count = count_sent_today(inbox)
            except Exception as exc:  # no password yet, network, auth
                imap_error = str(exc)
        sent = max(logged, imap_count or 0)
        assigned = sum(1 for d in drafts if d["inbox"] == inbox["id"] and d["status"] in queue_md.ACTIVE)
        cap = daily_cap(inbox)
        table[inbox["id"]] = {
            "address": inbox["address"], "cap": cap, "sent_logged": logged,
            "sent_imap": imap_count, "imap_error": imap_error, "assigned_unsent": assigned,
            "remaining": max(cap - sent - assigned, 0),
        }
    return table


def assign(use_imap=True):
    table = capacity(use_imap)
    drafts = queue_md.load()
    assigned, deferred = [], []
    for d in drafts:
        if d["status"] not in queue_md.ACTIVE or d["inbox"]:
            continue
        if int(d["touch"] or 1) > 1:
            deferred.append({"id": d["id"], "reason": "follow-up has no original inbox recorded"})
            continue
        open_inboxes = [k for k, v in table.items() if v["remaining"] > 0]
        if not open_inboxes:
            deferred.append({"id": d["id"], "reason": "all inboxes at cap"})
            continue
        best = max(open_inboxes, key=lambda k: table[k]["remaining"])
        d["inbox"] = best
        table[best]["remaining"] -= 1
        assigned.append({"id": d["id"], "inbox": best})
    # Follow-ups arrive pre-assigned to their original inbox; if that inbox is
    # over cap, send.py stops at the cap and the rest simply wait for tomorrow.
    queue_md.save(drafts)
    return {"assigned": assigned, "deferred": deferred, "capacity": table}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["status", "assign"])
    p.add_argument("--no-imap", action="store_true", help="skip Sent-folder check (offline/testing)")
    args = p.parse_args()
    if args.cmd == "status":
        print_json(capacity(not args.no_imap))
    else:
        print_json(assign(not args.no_imap))


if __name__ == "__main__":
    main()

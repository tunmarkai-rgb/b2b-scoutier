"""Inbox config, credentials, send-locks and IMAP helpers shared by the router,
sender and reply fetcher."""
import imaplib
import os
import re
import time
from datetime import date, datetime

from common import CONFIG, INBOXES_FILE, LOCKS, die, load_env, load_json

LOCK_STALE_SECONDS = 3 * 3600


def load_inboxes(enabled_only=True):
    data = load_json(INBOXES_FILE, default={"inboxes": []})
    inboxes = data.get("inboxes", [])
    return [i for i in inboxes if i.get("enabled", True)] if enabled_only else inboxes


def password_for(inbox):
    load_env()
    return os.environ.get(f"INBOX_{inbox['id'].upper()}_APP_PASSWORD", "").replace(" ", "")


def daily_cap(inbox, today=None):
    """Cap from the warm-up schedule, unless the inbox has daily_cap_override."""
    if inbox.get("daily_cap_override"):
        return int(inbox["daily_cap_override"])
    today = today or date.today()
    start = date.fromisoformat(inbox.get("warmup_start") or today.isoformat())
    days = (today - start).days
    steps = sorted(load_json(CONFIG / "warmup-schedule.json")["steps"], key=lambda s: s["day"])
    cap = 0
    for step in steps:
        if days >= step["day"]:
            cap = step["cap"]
    return min(cap, int(inbox.get("max_cap", 25)))


def imap_connect(inbox):
    pw = password_for(inbox)
    if not pw:
        raise RuntimeError(f"no app password in .env for inbox {inbox['id']} "
                           f"(INBOX_{inbox['id'].upper()}_APP_PASSWORD)")
    conn = imaplib.IMAP4_SSL(inbox.get("imap_host", "imap.gmail.com"), int(inbox.get("imap_port", 993)))
    conn.login(inbox["address"], pw)
    return conn


def find_sent_folder(conn):
    """Locate the Sent folder via the \\Sent special-use flag (locale independent)."""
    status, folders = conn.list()
    if status == "OK":
        for raw in folders:
            line = raw.decode(errors="replace")
            if "\\Sent" in line:
                match = re.search(r'"([^"]+)"\s*$', line) or re.search(r"(\S+)\s*$", line)
                if match:
                    return match.group(1)
    return "[Gmail]/Sent Mail"


def count_sent_today(inbox):
    """Messages in the provider's Sent folder dated today. This is the ground truth
    for caps: it includes manual sends and anything the local log missed."""
    conn = imap_connect(inbox)
    try:
        folder = find_sent_folder(conn)
        conn.select(f'"{folder}"', readonly=True)
        since = date.today().strftime("%d-%b-%Y")
        status, data = conn.search(None, "SINCE", since)
        return len(data[0].split()) if status == "OK" and data and data[0] else 0
    finally:
        try:
            conn.logout()
        except Exception:
            pass


class SendLock:
    """One send batch per inbox at a time, across processes."""

    def __init__(self, inbox_id):
        LOCKS.mkdir(exist_ok=True)
        self.path = LOCKS / f"{inbox_id}.lock"
        self.held = False

    def __enter__(self):
        if self.path.exists() and time.time() - self.path.stat().st_mtime > LOCK_STALE_SECONDS:
            self.path.unlink(missing_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            die(f"inbox lock {self.path.name} is held by another run. If no run is active, delete it.")
        with os.fdopen(fd, "w") as fh:
            fh.write(f"pid={os.getpid()} at={datetime.now().isoformat()}\n")
        self.held = True
        return self

    def __exit__(self, *exc):
        if self.held:
            self.path.unlink(missing_ok=True)

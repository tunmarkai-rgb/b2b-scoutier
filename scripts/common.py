"""Shared paths, config loading and CSV helpers for the B2B Scoutier scripts.

Every script in this folder imports from here so that file locations, CSV
headers and pipeline stages are defined exactly once.
"""
import csv
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

# Windows consoles default to cp1252; company names often contain accents.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
CONTACTS = ROOT / "contacts"
CONFIG = ROOT / "config"
OUTREACH = ROOT / "outreach"
QUEUE_DIR = OUTREACH / "queue"
REPLIES_DIR = OUTREACH / "replies"
REPORTS = ROOT / "reports"
LOCKS = ROOT / ".locks"
SENT_LOG = OUTREACH / "sent-log.md"
QUEUE_FILE = QUEUE_DIR / "outreach-queue.md"
FOLLOWUP_FILE = QUEUE_DIR / "follow-up-queue.md"
INBOXES_FILE = ROOT / "inboxes.json"
ENV_FILE = ROOT / ".env"

CSV_FILES = {
    "prospects": CONTACTS / "prospects.csv",
    "contacted": CONTACTS / "contacted.csv",
    "hot_leads": CONTACTS / "hot-leads.csv",
    "suppression": CONTACTS / "suppression-list.csv",
    "dnc": CONTACTS / "do-not-contact.csv",
}

HEADERS = {
    "prospects": [
        "lead_id", "company", "domain", "website", "city", "country", "category",
        "sells_what", "employees", "decision_maker", "role", "email", "email_source",
        "email_status", "linkedin", "phone", "source", "signals", "signal_notes",
        "icp_score", "stage", "touch_count", "last_touch", "next_follow_up",
        "assigned_inbox", "notes", "created_at", "updated_at",
    ],
    "contacted": [
        "timestamp", "lead_id", "email", "company", "inbox", "touch", "subject",
        "message_id", "status", "draft_id",
    ],
    "hot_leads": [
        "lead_id", "company", "decision_maker", "email", "reply_date",
        "classification", "summary", "next_action", "added_at",
    ],
    "suppression": ["email", "domain", "reason", "added_at"],
    "dnc": ["company", "domain", "email", "reason", "added_at"],
}

STAGES = [
    "Sourced", "Enriched", "Qualified", "Contacted", "Follow-up", "Replied",
    "Interested", "Call Booked", "Proposal Sent", "Won", "Lost", "Disqualified",
]
# Stages where no further automated outreach may happen.
CLOSED_STAGES = {
    "Replied", "Interested", "Call Booked", "Proposal Sent", "Won", "Lost", "Disqualified",
}


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def today_str():
    return date.today().isoformat()


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def norm_email(value):
    return (value or "").strip().lower()


def domain_of(value):
    """Return a bare lowercase domain from a URL, email address or domain."""
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "@" in value and "/" not in value:
        return value.rsplit("@", 1)[1]
    if "://" not in value:
        value = "http://" + value
    host = urlparse(value).hostname or ""
    return host[4:] if host.startswith("www.") else host


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        die(f"missing {path.relative_to(ROOT)}; run `python scripts/init_data.py`")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_settings():
    return load_json(CONFIG / "settings.json")


def load_env():
    """Minimal .env reader so the project has no required dependencies."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def ensure_csv(name):
    path = CSV_FILES[name]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(HEADERS[name])
    return path


def read_csv(name):
    path = ensure_csv(name)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    headers = HEADERS[name]
    return [{h: (row.get(h) or "") for h in headers} for row in rows]


def write_csv(name, rows):
    """Atomically rewrite a CSV (temp file + replace)."""
    path = ensure_csv(name)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADERS[name], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.replace(tmp, path)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        die(f"{path.name} is locked (open in Excel?). Close it and re-run.")


def append_csv(name, row):
    path = ensure_csv(name)
    try:
        with open(path, "a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=HEADERS[name], extrasaction="ignore").writerow(row)
    except PermissionError:
        die(f"{path.name} is locked (open in Excel?). Close it and re-run.")


def blocklists():
    """Suppressed/DNC emails, domains and company names, all lowercase."""
    emails, domains, companies = set(), set(), set()
    for name in ("suppression", "dnc"):
        for row in read_csv(name):
            if row.get("email"):
                emails.add(norm_email(row["email"]))
            if row.get("domain"):
                domains.add(domain_of(row["domain"]))
            if row.get("company"):
                companies.add(row["company"].strip().lower())
    return emails, domains, companies


def has_placeholder(text):
    return bool(re.search(r"TODO|\[.*?\]", text or ""))


def print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))

#!/usr/bin/env python3
"""Lightweight, subscription-free email check: syntax + the domain accepts mail (MX).

This does not prove a mailbox exists (only a paid verifier or a send can), but
it catches typos, dead domains and parked sites before they become bounces.

Usage:
    python scripts/verify_email.py someone@example.com [...]
    python scripts/verify_email.py --leads     # verify every lead that has an unverified email
"""
import argparse
import re
import subprocess

from common import now_iso, print_json, read_csv, write_csv

EMAIL_RE = re.compile(r"^[a-z0-9._%+'-]+@([a-z0-9-]+\.)+[a-z]{2,}$", re.I)
ROLE_PREFIXES = {"info", "sales", "hello", "contact", "admin", "office", "support",
                 "team", "marketing", "enquiries", "inquiries", "hr", "jobs", "careers"}
_cache = {}


def mx_hosts(domain):
    if domain in _cache:
        return _cache[domain]
    hosts = []
    try:
        import dns.resolver  # optional: pip install dnspython
        try:
            hosts = [str(r.exchange).rstrip(".") for r in dns.resolver.resolve(domain, "MX", lifetime=8)]
        except Exception:
            hosts = []
    except ImportError:
        try:
            out = subprocess.run(["nslookup", "-type=mx", domain], capture_output=True,
                                 text=True, timeout=15).stdout
            hosts = re.findall(r"mail exchanger\s*=\s*(?:\d+\s+)?(\S+)", out)
        except (OSError, subprocess.TimeoutExpired):
            hosts = []
    hosts = [h.rstrip(".") for h in hosts if h and h != "."]
    _cache[domain] = hosts
    return hosts


def check(email):
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return {"email": email, "status": "invalid-syntax", "mx": [], "role": False}
    local, domain = email.split("@", 1)
    hosts = mx_hosts(domain)
    return {"email": email, "status": "valid-mx" if hosts else "no-mx",
            "mx": hosts[:3], "role": local.split("+")[0] in ROLE_PREFIXES}


def verify_leads():
    rows = read_csv("prospects")
    results = []
    for row in rows:
        if row["email"] and row["email_status"] in ("", "unverified"):
            res = check(row["email"])
            row["email_status"] = res["status"]
            if res["role"] and "role address" not in row["notes"]:
                row["notes"] = (row["notes"] + " | " if row["notes"] else "") + "role address (lower reply odds)"
            row["updated_at"] = now_iso()
            results.append({"lead_id": row["lead_id"], **res})
    write_csv("prospects", rows)
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("emails", nargs="*")
    p.add_argument("--leads", action="store_true")
    args = p.parse_args()
    if args.leads:
        print_json(verify_leads())
    else:
        print_json([check(e) for e in args.emails])


if __name__ == "__main__":
    main()

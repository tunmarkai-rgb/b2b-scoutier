"""End-to-end tests for the deterministic pipeline scripts.

Runs against a throwaway copy of scripts/ and config/ in a temp folder, with
fake DNS, SMTP and IMAP, so nothing touches the real CRM, network or inboxes.

    python -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="scoutier-test-"))
for folder in ("scripts", "config"):
    shutil.copytree(REPO / folder, TMP / folder)
shutil.copyfile(REPO / "inboxes.example.json", TMP / "inboxes.example.json")
shutil.copyfile(REPO / ".env.example", TMP / ".env.example")
sys.path.insert(0, str(TMP / "scripts"))

import common  # noqa: E402
import compliance  # noqa: E402
import crm  # noqa: E402
import fetch_replies  # noqa: E402
import inbox_router  # noqa: E402
import init_data  # noqa: E402
import queue_md  # noqa: E402
import send  # noqa: E402
import verify_email  # noqa: E402

TODAY = date.today()
BODY = ("Hi Sam,\n\nNoticed you're hiring a BD manager, which usually means pipeline is the "
        "bottleneck. We build and run the full outbound system and hand over booked calls.\n\n"
        "Worth a quick chat?\n\nAlex")


def run(fn, *argv):
    """Call a script's main() with argv, return parsed JSON stdout (or raw text)."""
    old = sys.argv
    sys.argv = ["x", *argv]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            fn()
    finally:
        sys.argv = old
    out = buf.getvalue()
    # Some commands print several JSON documents (e.g. send.py archives first); keep the last.
    decoder, pos, last = json.JSONDecoder(), 0, out
    while True:
        start = min((i for i in (out.find("{", pos), out.find("[", pos)) if i != -1), default=-1)
        if start == -1:
            return last
        try:
            last, pos = decoder.raw_decode(out, start)
        except json.JSONDecodeError:
            pos = start + 1


def write_json(name, data):
    path = TMP / "outreach" / "work" / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


class FakeSMTP:
    sent = []

    def __init__(self, *a, **k): pass
    def starttls(self): pass
    def login(self, *a): pass
    def send_message(self, msg): FakeSMTP.sent.append(msg)
    def quit(self): pass


class FakeIMAP:
    def __init__(self, messages): self.messages = messages
    def select(self, *a, **k): return "OK", [str(len(self.messages)).encode()]
    def search(self, *a): return "OK", [" ".join(str(i + 1) for i in range(len(self.messages))).encode()]
    def fetch(self, num, q): return "OK", [(b"x", self.messages[int(num) - 1])]
    def logout(self): pass


class Pipeline(unittest.TestCase):
    """Ordered scenario: each test builds on the state left by the previous one."""

    @classmethod
    def setUpClass(cls):
        verify_email.mx_hosts = lambda d: [] if "dead" in d else ["mx." + d]
        send.smtplib.SMTP = FakeSMTP
        send.count_sent_today = lambda inbox: 2 if inbox["id"] == "tm1" else 0
        with contextlib.redirect_stdout(io.StringIO()):
            init_data.main()
        settings = json.loads((TMP / "config/settings.json").read_text())
        settings["sender"].update(name="Alex Test", website="https://tunmark.example",
                                  physical_address="1 King St W, Toronto, ON, Canada")
        (TMP / "config/settings.json").write_text(json.dumps(settings))
        inboxes = json.loads((TMP / "inboxes.json").read_text())
        inboxes["inboxes"][0]["warmup_start"] = TODAY.isoformat()                         # cap 5
        inboxes["inboxes"][1].update(enabled=True, warmup_start=(TODAY - timedelta(days=4)).isoformat())  # cap 10
        (TMP / "inboxes.json").write_text(json.dumps(inboxes))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def test_01_add_dedupes_and_respects_blocklists(self):
        run(crm.main, "dnc", "--company", "Client Co", "--domain", "clientco.ca")
        leads = [
            {"company": "Acme Displays", "website": "https://www.acmedisplays.ca", "city": "Toronto", "country": "CA",
             "category": "b2b_products_other", "employees": "11-50", "email": "jane@acmedisplays.ca",
             "email_source": "published", "decision_maker": "Jane Doe", "stage": "Enriched",
             "signals": ["sells_to_businesses_confirmed", "hiring_growth_role"]},
            {"company": "Acme Displays", "website": "acmedisplays.ca", "city": "Toronto"},
            {"company": "Client Co", "website": "clientco.ca", "city": "Toronto"},
            {"company": "Guess Co", "website": "guess.ca", "city": "Toronto", "country": "CA", "category": "b2b_saas",
             "employees": 30, "email": "xi@guess.ca", "email_source": "pattern", "decision_maker": "Xi",
             "stage": "Enriched", "signals": ["hiring_growth_role", "sells_to_businesses_confirmed"]},
            {"company": "Dead Domain Ltd", "website": "dead.co.uk", "city": "London", "country": "UK",
             "category": "marketing_agency", "employees": 10, "email": "a@dead.co.uk", "email_source": "pattern",
             "decision_maker": "A", "stage": "Enriched", "signals": ["hiring_growth_role"]},
        ] + [
            {"company": f"UK Firm {i}", "website": f"ukfirm{i}.co.uk", "city": "London", "country": "UK",
             "category": "marketing_agency", "employees": 15, "email": f"sam{i}@ukfirm{i}.co.uk",
             "email_source": "pattern", "decision_maker": f"Sam {i}", "stage": "Enriched",
             "signals": ["hiring_growth_role", "sells_to_businesses_confirmed"]}
            for i in range(20)
        ]
        out = run(crm.main, "add", write_json("leads.json", leads))
        self.assertEqual(len(out["added"]), 23)
        reasons = sorted(s["reason"] for s in out["skipped"])
        self.assertEqual(reasons, ["duplicate", "on suppression/do-not-contact list"])
        self.assertEqual(common.read_csv("prospects")[0]["domain"], "acmedisplays.ca")

    def test_02_verify_and_score(self):
        run(verify_email.main, "--leads")
        status = {r["company"]: r["email_status"] for r in common.read_csv("prospects")}
        self.assertEqual(status["Dead Domain Ltd"], "no-mx")
        self.assertEqual(status["UK Firm 0"], "valid-mx")
        run(crm.main, "score")
        stages = {r["company"]: r["stage"] for r in common.read_csv("prospects")}
        self.assertEqual(stages["Acme Displays"], "Qualified")
        self.assertTrue(all(s != "Enriched" for s in stages.values()))

    def test_03_compliance_blocks_casl_and_unverified(self):
        out = run(compliance.main, "leads")
        blocked = {b["lead_id"]: " ".join(b["reasons"]) for b in out["blocked"]}
        by_company = {r["company"]: r["lead_id"] for r in common.read_csv("prospects")}
        self.assertIn("CASL", blocked[by_company["Guess Co"]])
        self.assertIn("not verified", blocked[by_company["Dead Domain Ltd"]])
        self.assertIn(by_company["Acme Displays"], out["passed"])
        self.assertEqual(len(out["passed"]), 21)
        Pipeline.passed = out["passed"]

    def test_04_queue_add_rejects_duplicates_and_unknown(self):
        drafts = [{"lead_id": lid, "subject": "quick question", "body": BODY} for lid in Pipeline.passed]
        drafts += [{"lead_id": Pipeline.passed[0], "subject": "dup", "body": BODY},
                   {"lead_id": "L-99999", "subject": "x", "body": BODY}]
        out = run(queue_md.main, "add", write_json("drafts.json", drafts))
        self.assertEqual(len(out["added"]), 21)
        self.assertEqual(len(out["skipped"]), 2)
        out = run(compliance.main, "queue")
        self.assertEqual(len(out["passed"]), 21)

    def test_05_router_respects_warmup_caps(self):
        out = run(inbox_router.main, "assign", "--no-imap")
        self.assertEqual(len(out["assigned"]), 15)  # 5 (tm1) + 10 (tm2)
        self.assertEqual(len(out["deferred"]), 6)

    def test_06_dry_run_sends_nothing(self):
        run(queue_md.main, "approve", "--all")
        out = run(send.main)
        self.assertEqual(out["mode"], "dry-run")
        self.assertEqual(FakeSMTP.sent, [])
        self.assertEqual(common.read_csv("contacted"), [])
        preview = (TMP / "outreach" / "dry-run-preview.md").read_text(encoding="utf-8")
        self.assertIn("1 King St W", preview)
        self.assertIn('reply "stop"', preview)

    def test_07_live_send_uses_sent_folder_as_ground_truth(self):
        out = run(send.main, "--live", "--no-delay")
        per_inbox = {}
        for s in out["sent"]:
            per_inbox[s["inbox"]] = per_inbox.get(s["inbox"], 0) + 1
        self.assertEqual(per_inbox, {"tm1": 3, "tm2": 10})  # tm1: cap 5 minus 2 manual sends
        self.assertEqual(len(out["held_for_cap"]), 2)
        msg = FakeSMTP.sent[0]
        self.assertTrue(msg["List-Unsubscribe"].startswith("<mailto:"))
        self.assertIn("Alex Test", msg.get_content())
        lead = next(r for r in common.read_csv("prospects") if r["email"] == msg["To"].addresses[0].addr_spec)
        self.assertEqual((lead["stage"], lead["touch_count"]), ("Contacted", "1"))
        self.assertEqual(lead["next_follow_up"], (TODAY + timedelta(days=3)).isoformat())
        self.assertEqual(len(common.read_csv("contacted")), 13)

    def test_08_followup_threads_on_original_inbox(self):
        rows = common.read_csv("prospects")
        lead = next(r for r in rows if r["assigned_inbox"] == "tm2")
        run(crm.main, "update", lead["lead_id"], "--set", f"next_follow_up={TODAY.isoformat()}")
        due = run(crm.main, "due-followups")
        self.assertEqual([d["lead_id"] for d in due], [lead["lead_id"]])
        run(queue_md.main, "add", write_json("fu.json", [{"lead_id": lead["lead_id"], "subject": "", "body": BODY}]))
        draft = next(d for d in queue_md.load() if d["lead_id"] == lead["lead_id"] and d["status"] == "pending")
        self.assertEqual((draft["inbox"], draft["touch"]), ("tm2", "2"))
        # tm2 is at today's cap, so the follow-up is held...
        run(queue_md.main, "approve", draft["id"])
        out = run(send.main, "--live", "--no-delay", "--inbox", "tm2")
        self.assertIn(draft["id"], out["held_for_cap"])
        # ...until there is room.
        inboxes = json.loads((TMP / "inboxes.json").read_text())
        inboxes["inboxes"][1]["daily_cap_override"] = 20
        (TMP / "inboxes.json").write_text(json.dumps(inboxes))
        FakeSMTP.sent.clear()
        run(send.main, "--live", "--no-delay", "--inbox", "tm2", "--limit", "1")
        msg = next(m for m in FakeSMTP.sent if m["To"].addresses[0].addr_spec == lead["email"])
        self.assertEqual(msg["Subject"], "Re: quick question")
        self.assertTrue(msg["In-Reply-To"])
        updated = crm._find(common.read_csv("prospects"), lead["lead_id"])
        self.assertEqual((updated["stage"], updated["touch_count"]), ("Follow-up", "2"))
        self.assertEqual(updated["next_follow_up"], (TODAY + timedelta(days=4)).isoformat())

    def test_09_replies_bounces_and_auto_replies(self):
        sent = [c for c in common.read_csv("contacted") if c["touch"] == "1"]
        replier, bouncer, away = sent[1]["email"], sent[2]["email"], sent[3]["email"]
        messages = [
            f"From: Sam <{replier}>\r\nSubject: Re: quick question\r\nMessage-ID: <r1@x>\r\n\r\n"
            "Yes, interested.\r\n\r\nOn Mon, Alex wrote:\r\n> Hi Sam\r\n".encode(),
            f"From: mailer-daemon@googlemail.com\r\nSubject: Delivery Status Notification (Failure)\r\n"
            f"Message-ID: <b1@x>\r\nX-Failed-Recipients: {bouncer}\r\n\r\nAddress not found\r\n".encode(),
            f"From: {away}\r\nSubject: Automatic reply\r\nMessage-ID: <o1@x>\r\nAuto-Submitted: auto-replied\r\n\r\nAway\r\n".encode(),
            b"From: stranger@elsewhere.com\r\nSubject: hi\r\nMessage-ID: <z1@x>\r\n\r\nhi\r\n",
        ]
        fetch_replies.imap_connect = lambda inbox: FakeIMAP(messages)  # same mail visible in both inboxes
        out = run(fetch_replies.main)
        self.assertEqual(out["counts"], {"reply": 1, "bounce": 1, "auto_reply": 1})
        self.assertEqual(out["replies"][0]["text"], "Yes, interested.")
        by_email = {r["email"]: r for r in common.read_csv("prospects")}
        self.assertEqual((by_email[replier]["stage"], by_email[replier]["next_follow_up"]), ("Replied", ""))
        self.assertEqual((by_email[bouncer]["stage"], by_email[bouncer]["email_status"]), ("Lost", "bounced"))
        self.assertIn(by_email[away]["stage"], ("Contacted", "Follow-up"))  # sequence continues
        self.assertNotEqual(by_email[away]["next_follow_up"], "")
        self.assertEqual(run(fetch_replies.main)["replies"], [])  # never processed twice

    def test_10_suppress_cancels_drafts_and_blocks_send(self):
        pending = next(d for d in queue_md.load() if d["status"] == "approved")
        run(crm.main, "suppress", pending["to"], "--reason", "unsubscribe")
        draft = next(d for d in queue_md.load() if d["id"] == pending["id"])
        self.assertEqual(draft["status"], "cancelled")
        lead = crm._find(common.read_csv("prospects"), pending["lead_id"])
        self.assertEqual(compliance.check_lead(lead, common.load_json(TMP / "config/settings.json"),
                                               common.blocklists())[0], "on suppression / do-not-contact list")

    def test_11_report_renders(self):
        with contextlib.redirect_stdout(io.StringIO()):
            import report
            report.main()
        html = (TMP / "reports" / "daily-report.html").read_text(encoding="utf-8")
        self.assertIn("Scoutier Pipeline", html)
        self.assertNotIn("__DATA__", html)
        stats = crm.compute_stats()
        self.assertEqual(stats["bounced"], 1)
        self.assertGreater(stats["reply_rate"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

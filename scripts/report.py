#!/usr/bin/env python3
"""Build reports/daily-report.html, a self-contained pipeline dashboard.

The CRM data is embedded in the page (browsers block file:// CSV reads), so the
file opens with a double-click, needs no server, and is rebuilt every run.

    python scripts/report.py
"""
import json

from common import REPORTS, STAGES, load_json, now_iso, read_csv, CONFIG
from crm import compute_stats
from inbox_router import capacity

CARD_FIELDS = ["lead_id", "company", "city", "country", "category", "decision_maker", "role",
               "email", "icp_score", "stage", "touch_count", "last_touch", "next_follow_up",
               "assigned_inbox", "email_status"]

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scoutier Pipeline</title>
<style>
:root {
  --bg: #f6f5f1; --panel: #ffffff; --ink: #1c1d1f; --muted: #6b6e76; --line: #e3e1da;
  --accent: #1f5f4a; --accent-soft: #e2efe9; --warn: #a3471b; --warn-soft: #f7e6dc;
  --col: #efede7; --shadow: 0 1px 2px rgba(0,0,0,.06);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #141517; --panel: #1d1f22; --ink: #ecebe6; --muted: #9a9ca3; --line: #2c2f33;
    --accent: #6fc3a1; --accent-soft: #1f3a30; --warn: #f0a07a; --warn-soft: #3d2519;
    --col: #191b1e; --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #141517; --panel: #1d1f22; --ink: #ecebe6; --muted: #9a9ca3; --line: #2c2f33;
  --accent: #6fc3a1; --accent-soft: #1f3a30; --warn: #f0a07a; --warn-soft: #3d2519;
  --col: #191b1e; --shadow: none;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
.wrap { max-width: 1400px; margin: 0 auto; padding: 24px 16px 48px; }
header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; }
h1 { font-size: 22px; margin: 0; letter-spacing: -.01em; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 28px 0 10px; }
.sub { color: var(--muted); font-size: 13px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-top: 18px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; box-shadow: var(--shadow); }
.kpi .v { font-size: 26px; font-weight: 650; font-variant-numeric: tabular-nums; }
.kpi .l { color: var(--muted); font-size: 12px; }
.kpi .t { font-size: 12px; margin-top: 2px; }
.good { color: var(--accent); } .bad { color: var(--warn); }
.inboxes { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
.inbox { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; }
.bar { height: 6px; background: var(--col); border-radius: 3px; overflow: hidden; margin-top: 6px; }
.bar i { display: block; height: 100%; background: var(--accent); }
.tools { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
input, select { background: var(--panel); color: var(--ink); border: 1px solid var(--line);
  border-radius: 8px; padding: 7px 10px; font: inherit; min-width: 0; }
input { flex: 1 1 220px; }
.board { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; }
.col { flex: 0 0 240px; background: var(--col); border-radius: 10px; padding: 8px; max-height: 70vh; overflow-y: auto; }
.col h3 { font-size: 12px; margin: 2px 4px 8px; display: flex; justify-content: space-between; color: var(--muted); }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; margin-bottom: 6px; box-shadow: var(--shadow); }
.card b { display: block; font-size: 13px; }
.card .m { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.pill { display: inline-block; font-size: 11px; padding: 0 6px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); margin-right: 4px; }
.pill.w { background: var(--warn-soft); color: var(--warn); }
table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 12px; color: var(--muted); font-weight: 600; }
.tablewrap { overflow-x: auto; }
.empty { color: var(--muted); padding: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Scoutier Pipeline</h1>
    <span class="sub">Generated __GENERATED__ &middot; active city: <b id="city"></b> &middot; review mode: <b id="mode"></b></span>
  </header>
  <div class="kpis" id="kpis"></div>

  <h2>Inboxes today</h2>
  <div class="inboxes" id="inboxes"></div>

  <h2>Pipeline</h2>
  <div class="tools">
    <input id="q" placeholder="Search company, contact, email..." aria-label="Search leads">
    <select id="fcity" aria-label="Filter by city"><option value="">All cities</option></select>
  </div>
  <div class="board" id="board"></div>

  <h2>Hot leads</h2>
  <div class="tablewrap" id="hot"></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = x => (x * 100).toFixed(1) + '%';
const S = D.stats;
document.getElementById('city').textContent = D.activeCity || '-';
document.getElementById('mode').textContent = D.reviewMode;
const kpi = (v, l, t, cls) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div>${t ? `<div class="t ${cls||''}">${t}</div>` : ''}</div>`;
document.getElementById('kpis').innerHTML = [
  kpi(S.sent_today, 'Sent today', `aggregate cap ${D.totalCap}`),
  kpi(S.sent_7d, 'Sent last 7 days'),
  kpi(pct(S.reply_rate), 'Reply rate', 'target 20%', S.leads_contacted ? (S.reply_rate >= .2 ? 'good' : 'bad') : ''),
  kpi(pct(S.bounce_rate), 'Bounce rate', 'keep under 3%', S.leads_contacted ? (S.bounce_rate <= .03 ? 'good' : 'bad') : ''),
  kpi(S.hot_leads, 'Hot leads'),
  kpi(S.due_follow_ups, 'Follow-ups due'),
  kpi(S.leads_total, 'Leads in CRM'),
].join('');
const ib = Object.entries(D.inboxes);
document.getElementById('inboxes').innerHTML = ib.length ? ib.map(([id, v]) => {
  const used = v.cap - v.remaining;
  return `<div class="inbox"><b>${esc(id)}</b> <span class="sub">${esc(v.address)}</span>
    <div class="sub">${used} / ${v.cap} used (${v.sent_logged} sent, ${v.assigned_unsent} queued)</div>
    <div class="bar"><i style="width:${v.cap ? Math.min(100, used / v.cap * 100) : 0}%"></i></div></div>`;
}).join('') : '<div class="empty">No inboxes configured yet (inboxes.json).</div>';
const cities = [...new Set(D.leads.map(l => l.city).filter(Boolean))].sort();
const fc = document.getElementById('fcity');
cities.forEach(c => fc.insertAdjacentHTML('beforeend', `<option>${esc(c)}</option>`));
function card(l) {
  const flags = [];
  if (l.icp_score) flags.push(`<span class="pill">ICP ${esc(l.icp_score)}</span>`);
  if (l.email_status === 'bounced') flags.push('<span class="pill w">bounced</span>');
  if (l.next_follow_up && l.next_follow_up <= D.today) flags.push('<span class="pill w">follow-up due</span>');
  return `<div class="card"><b>${esc(l.company)}</b>
    <div class="m">${esc(l.decision_maker)}${l.role ? ' &middot; ' + esc(l.role) : ''}</div>
    <div class="m">${esc(l.city)}${l.category ? ' &middot; ' + esc(l.category) : ''}</div>
    ${l.last_touch ? `<div class="m">touch ${esc(l.touch_count)} on ${esc(l.last_touch)}${l.assigned_inbox ? ' via ' + esc(l.assigned_inbox) : ''}</div>` : ''}
    <div>${flags.join('')}</div></div>`;
}
function draw() {
  const q = document.getElementById('q').value.toLowerCase(), c = fc.value;
  const rows = D.leads.filter(l => (!c || l.city === c) &&
    (!q || [l.company, l.decision_maker, l.email, l.lead_id].join(' ').toLowerCase().includes(q)));
  document.getElementById('board').innerHTML = D.stages.map(s => {
    const items = rows.filter(l => l.stage === s);
    return `<div class="col"><h3><span>${esc(s)}</span><span>${items.length}</span></h3>${items.map(card).join('')}</div>`;
  }).join('');
}
document.getElementById('q').addEventListener('input', draw);
fc.addEventListener('change', draw);
draw();
document.getElementById('hot').innerHTML = D.hot.length ? `<table><thead><tr><th>Company</th><th>Contact</th><th>Replied</th><th>Type</th><th>Summary</th><th>Next action</th></tr></thead><tbody>${
  D.hot.slice().reverse().map(h => `<tr><td>${esc(h.company)}</td><td>${esc(h.decision_maker)}<div class="sub">${esc(h.email)}</div></td><td>${esc(h.reply_date)}</td><td>${esc(h.classification)}</td><td>${esc(h.summary)}</td><td>${esc(h.next_action)}</td></tr>`).join('')
}</tbody></table>` : '<div class="empty">No hot leads yet.</div>';
</script>
</body>
</html>
"""


def main():
    settings = load_json(CONFIG / "settings.json")
    cities = load_json(CONFIG / "cities.json")["cities"]
    active = next((c["city"] for c in cities if c.get("status") == "active"), "")
    inboxes = capacity(use_imap=False)
    data = {
        "today": now_iso()[:10], "activeCity": active, "reviewMode": settings["review_mode"],
        "stages": STAGES, "stats": compute_stats(), "inboxes": inboxes,
        "totalCap": sum(v["cap"] for v in inboxes.values()),
        "leads": [{k: r[k] for k in CARD_FIELDS} for r in read_csv("prospects")],
        "hot": read_csv("hot_leads"),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__GENERATED__", now_iso().replace("T", " ")).replace("__DATA__", payload)
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "daily-report.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

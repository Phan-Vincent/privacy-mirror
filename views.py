"""HTML rendering. Plain string templates, no template engine dependency."""

import html

import db
import mailer

# kept in sync with server.py REDIRECT_URI (shown to the user during Gmail setup)
REDIRECT_URI = "http://127.0.0.1:8765/oauth/gmail/callback"

STATUS_COLORS = {
    "pending": "#b58900", "queued": "#268bd2", "sent": "#268bd2",
    "acknowledged": "#6c71c4", "completed": "#2aa198", "rejected": "#dc322f",
    "needs_action": "#cb4b16", "overdue": "#dc322f",
}

STATUS_LABELS = {
    "pending": "Pending (ready to send)", "queued": "Queued", "sent": "Sent — awaiting reply",
    "acknowledged": "Acknowledged", "completed": "Completed", "rejected": "Rejected",
    "needs_action": "Needs manual action", "overdue": "Overdue — follow-up sent",
}


def e(s):
    return html.escape(str(s if s is not None else ""))


CSS = """
:root{--bg:#0f1419;--panel:#1a2029;--panel2:#222b36;--line:#2d3845;--fg:#e6edf3;
--muted:#8b98a5;--accent:#3b82f6;--accent2:#2563eb;--ok:#2aa198;--warn:#cb4b16}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
background:var(--bg);color:var(--fg)}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{background:var(--panel);border-bottom:1px solid var(--line);padding:0 24px;
display:flex;align-items:center;gap:24px;position:sticky;top:0;z-index:10}
header .brand{font-weight:700;font-size:18px;padding:16px 0;color:var(--fg)}
header .brand span{color:var(--accent)}
nav{display:flex;gap:4px}
nav a{padding:18px 14px;color:var(--muted);border-bottom:2px solid transparent}
nav a.active,nav a:hover{color:var(--fg);border-bottom-color:var(--accent);text-decoration:none}
.wrap{max-width:1100px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 12px}
.sub{color:var(--muted);margin:0 0 20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:24px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.card .n{font-size:28px;font-weight:700}.card .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px;margin-bottom:20px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
tr:hover td{background:var(--panel2)}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;font-weight:600;color:#fff;white-space:nowrap}
.btn{display:inline-block;background:var(--accent);color:#fff;border:0;border-radius:7px;
padding:8px 14px;font-size:13px;cursor:pointer;font-weight:600}
.btn:hover{background:var(--accent2);text-decoration:none}
.btn.sm{padding:5px 10px;font-size:12px}
.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--fg)}
.btn.danger{background:#dc322f}.btn.warn{background:var(--warn)}
input,textarea,select{width:100%;background:var(--bg);border:1px solid var(--line);color:var(--fg);
border-radius:7px;padding:9px 11px;font:inherit}
textarea{min-height:90px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px}
label{display:block;color:var(--muted);font-size:12px;margin:14px 0 5px;text-transform:uppercase;letter-spacing:.03em}
.row{display:flex;gap:16px;flex-wrap:wrap}.row>div{flex:1;min-width:220px}
.banner{border-radius:9px;padding:12px 16px;margin-bottom:18px;border:1px solid}
.banner.warn{background:#2b2310;border-color:#6b5320;color:#f0d27a}
.banner.ok{background:#0f2620;border-color:#1d5246;color:#7fe0cd}
.banner.info{background:#10243a;border-color:#1d4a73;color:#9cd2ff}
.muted{color:var(--muted)}.mono{font-family:ui-monospace,Consolas,monospace}
.flex{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.spacer{flex:1}
.toggle{display:flex;align-items:center;gap:10px;margin:8px 0}
.pill{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--panel2);color:var(--muted)}
 pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:14px;font-size:12.5px;overflow:auto}
.small{font-size:12px}
"""


def layout(title, active, body, flash=None):
    nav_items = [("/", "Dashboard"), ("/requests", "Requests"), ("/brokers", "Brokers"),
                 ("/profile", "Profile"), ("/settings", "Settings")]
    nav = "".join(
        f'<a href="{href}" class="{"active" if active==href else ""}">{e(label)}</a>'
        for href, label in nav_items
    )
    flash_html = ""
    if flash:
        kind, msg = flash
        flash_html = f'<div class="banner {e(kind)}">{e(msg)}</div>'
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · PrivacyMirror</title><style>{CSS}</style></head><body>
<header><div class="brand">Privacy<span>Mirror</span></div><nav>{nav}</nav></header>
<div class="wrap">{flash_html}{body}</div></body></html>"""


# ---------- pages ----------

def dashboard():
    counts = {r["status"]: r["c"] for r in
              db.query("SELECT status, COUNT(*) c FROM requests GROUP BY status")}
    total = sum(counts.values())
    brokers_n = db.query_one("SELECT COUNT(*) c FROM brokers")["c"]
    enabled_n = db.query_one("SELECT COUNT(*) c FROM brokers WHERE enabled=1")["c"]
    completed = counts.get("completed", 0)
    in_flight = counts.get("sent", 0) + counts.get("overdue", 0) + counts.get("acknowledged", 0)
    needs_action = counts.get("needs_action", 0)
    pending = counts.get("pending", 0)

    auto = db.get_setting("auto_send_enabled") == "1"
    dry = db.get_setting("dry_run") == "1"
    sender_ok = mailer.sender_ready()
    prov = mailer.provider()
    profile_ok = db.profile_is_complete()

    banners = []
    if not profile_ok:
        banners.append('<div class="banner warn">⚠ Your profile is incomplete. '
                       '<a href="/profile">Add your name and at least one email or address</a> '
                       'so requests can identify your records.</div>')
    if auto and not dry and not sender_ok:
        banners.append(f'<div class="banner warn">⚠ Auto-send + live mode are on but your '
                       f'<b>{e(prov)}</b> sender is not configured. <a href="/settings">Finish setup</a>.</div>')
    if (db.get_setting("ingest_replies_enabled") == "1" and mailer.gmail_ready()
            and not mailer.gmail_can_read()):
        banners.append('<div class="banner info">Reply tracking is on, but Gmail is connected '
                       'without read access. <a href="/settings">Reconnect Gmail</a> to let the app '
                       'read broker replies and update statuses automatically.</div>')
    mode = ('<span class="badge" style="background:#dc322f">LIVE SENDING</span>'
            if (auto and not dry) else
            ('<span class="badge" style="background:#268bd2">DRY RUN</span>' if auto else
             '<span class="badge" style="background:#586e75">AUTO-SEND OFF</span>'))

    cards = f"""
    <div class="cards">
      <div class="card"><div class="n">{enabled_n}/{brokers_n}</div><div class="l">Brokers targeted</div></div>
      <div class="card"><div class="n">{pending}</div><div class="l">Pending send</div></div>
      <div class="card"><div class="n">{in_flight}</div><div class="l">In flight</div></div>
      <div class="card"><div class="n">{needs_action}</div><div class="l">Needs you</div></div>
      <div class="card"><div class="n" style="color:var(--ok)">{completed}</div><div class="l">Completed</div></div>
    </div>"""

    progress = ""
    if total:
        pct = round(100 * completed / total)
        progress = (f'<div class="panel"><div class="flex"><b>Removal progress</b>'
                    f'<span class="spacer"></span><span class="muted">{completed} of {total} done</span></div>'
                    f'<div style="background:var(--bg);border-radius:8px;height:14px;margin-top:10px;overflow:hidden">'
                    f'<div style="width:{pct}%;height:100%;background:var(--ok)"></div></div></div>')

    recent = db.query("""SELECT ev.ts, ev.kind, ev.detail, b.name
                         FROM events ev LEFT JOIN requests r ON ev.request_id=r.id
                         LEFT JOIN brokers b ON r.broker_id=b.id
                         ORDER BY ev.id DESC LIMIT 12""")
    rows = "".join(
        f"<tr><td class='muted mono small'>{e(x['ts'])}</td>"
        f"<td><span class='pill'>{e(x['kind'])}</span></td>"
        f"<td>{e(x['name'] or '')}</td><td>{e(x['detail'])}</td></tr>"
        for x in recent
    ) or "<tr><td colspan=4 class='muted'>No activity yet.</td></tr>"

    body = f"""
    <h1>Dashboard</h1>
    <p class="sub">Your personal data-removal control center. Mode: {mode}</p>
    {''.join(banners)}
    {cards}
    {progress}
    <div class="panel">
      <div class="flex">
        <b>Removal runs</b><span class="spacer"></span>
        <form method="post" action="/actions/generate" style="display:inline">
          <button class="btn ghost sm">Generate requests for enabled brokers</button>
        </form>
        <form method="post" action="/actions/sync-replies" style="display:inline">
          <button class="btn ghost sm">Sync replies now</button>
        </form>
        <form method="post" action="/actions/run-pass" style="display:inline">
          <button class="btn sm">Run a send pass now</button>
        </form>
      </div>
      <p class="muted small" style="margin-top:10px">
        "Generate" creates a request per enabled broker. "Run a send pass" re-generates any
        due recurring re-removals (if enabled), emails all pending email-capable requests
        (respecting your dry-run / auto-send settings), and queues follow-ups for anything
        past its legal deadline.</p>
    </div>
    <h2>Recent activity</h2>
    <div class="panel" style="padding:6px 0">
      <table><tr><th>When (UTC)</th><th>Event</th><th>Broker</th><th>Detail</th></tr>{rows}</table>
    </div>"""
    return layout("Dashboard", "/", body)


def requests_page(filter_status=None):
    where = ""
    params = ()
    if filter_status:
        where = "WHERE r.status = ?"
        params = (filter_status,)
    reqs = db.query(f"""SELECT r.*, b.name broker_name, b.method bmethod, b.opt_out_url,
                        b.privacy_email FROM requests r JOIN brokers b ON r.broker_id=b.id
                        {where} ORDER BY
                        CASE r.status WHEN 'needs_action' THEN 0 WHEN 'pending' THEN 1
                        WHEN 'overdue' THEN 2 ELSE 3 END, r.id DESC""", params)

    filters = ['<a class="pill" href="/requests">all</a>']
    for st in ("pending", "sent", "needs_action", "overdue", "completed", "rejected"):
        filters.append(f'<a class="pill" href="/requests?status={st}">{e(st)}</a>')

    rows = []
    for r in reqs:
        color = STATUS_COLORS.get(r["status"], "#586e75")
        badge = f'<span class="badge" style="background:{color}">{e(STATUS_LABELS.get(r["status"], r["status"]))}</span>'
        actions = []
        if r["bmethod"] == "email" and r["privacy_email"]:
            if r["status"] in ("pending", "overdue"):
                actions.append(f'<form method="post" action="/actions/send/{r["id"]}" style="display:inline">'
                               f'<button class="btn sm">Send now</button></form>')
        else:
            actions.append(f'<a class="btn ghost sm" href="{e(r["opt_out_url"])}" target="_blank">Open opt-out ↗</a>')
        if r["status"] not in ("completed",):
            actions.append(f'<form method="post" action="/actions/status/{r["id"]}" style="display:inline">'
                           f'<input type="hidden" name="status" value="completed">'
                           f'<button class="btn ghost sm">Mark done</button></form>')
        deadline = e(r["deadline_at"][:10]) if r["deadline_at"] else "—"
        rows.append(
            f"<tr><td><a href='/requests/{r['id']}'><b>{e(r['broker_name'])}</b></a><br>"
            f"<span class='muted small'>{e(r['bmethod'])}</span></td>"
            f"<td>{badge}</td><td class='muted small'>{deadline}</td>"
            f"<td class='flex'>{''.join(actions)}</td></tr>"
        )
    table = ("".join(rows) or "<tr><td colspan=4 class='muted'>No requests yet — "
             "click <b>Generate requests</b> on the dashboard.</td></tr>")
    body = f"""
    <h1>Requests</h1>
    <p class="sub">Every removal request and where it stands.</p>
    <div class="flex" style="margin-bottom:14px">{''.join(filters)}</div>
    <div class="panel" style="padding:6px 0">
      <table><tr><th>Broker</th><th>Status</th><th>Deadline</th><th>Actions</th></tr>{table}</table>
    </div>"""
    return layout("Requests", "/requests", body)


def request_detail(req_id):
    r = db.query_one("""SELECT r.*, b.name broker_name, b.method bmethod, b.opt_out_url,
                        b.privacy_email, b.website, b.requires_id, b.jurisdiction
                        FROM requests r JOIN brokers b ON r.broker_id=b.id WHERE r.id=?""", (req_id,))
    if not r:
        return None
    import letters
    broker = db.query_one("SELECT * FROM brokers WHERE id=?", (r["broker_id"],))
    instructions = letters.manual_instructions(broker) if r["bmethod"] != "email" else ""
    events = db.query("SELECT * FROM events WHERE request_id=? ORDER BY id DESC", (req_id,))
    ev_rows = "".join(
        f"<tr><td class='muted mono small'>{e(x['ts'])}</td><td><span class='pill'>{e(x['kind'])}</span></td>"
        f"<td>{e(x['detail'])}</td></tr>" for x in events
    ) or "<tr><td colspan=3 class='muted'>No events.</td></tr>"

    color = STATUS_COLORS.get(r["status"], "#586e75")
    idflag = ('<span class="pill" style="color:#f0d27a">requires ID verification</span>'
              if r["requires_id"] else "")
    manual = (f'<div class="banner info">{e(instructions)}</div>' if instructions else "")
    send_btn = ""
    if r["bmethod"] == "email" and r["privacy_email"] and r["status"] in ("pending", "overdue"):
        send_btn = (f'<form method="post" action="/actions/send/{req_id}" style="display:inline">'
                    f'<button class="btn">Send now</button></form>')

    status_form = f"""
    <form method="post" action="/actions/status/{req_id}" class="flex" style="margin-top:8px">
      <select name="status" style="max-width:220px">
        {''.join(f'<option value="{s}" {"selected" if s==r["status"] else ""}>{e(STATUS_LABELS[s])}</option>' for s in STATUS_LABELS)}
      </select>
      <input name="note" placeholder="response note (optional)" style="flex:1">
      <button class="btn ghost">Update status</button>
    </form>"""

    body = f"""
    <p><a href="/requests" class="muted">← All requests</a></p>
    <h1>{e(r['broker_name'])}</h1>
    <p class="sub"><span class="badge" style="background:{color}">{e(STATUS_LABELS.get(r['status'], r['status']))}</span>
       &nbsp; <span class="pill">{e(r['bmethod'])}</span> {idflag}</p>
    {manual}
    <div class="row">
      <div class="panel">
        <b>Broker</b>
        <p class="small"><a href="{e(r['website'])}" target="_blank">{e(r['website'])} ↗</a></p>
        <p class="small">Opt-out: <a href="{e(r['opt_out_url'])}" target="_blank">{e(r['opt_out_url'])} ↗</a></p>
        <p class="small">Privacy email: <span class="mono">{e(r['privacy_email'] or '—')}</span></p>
        <p class="small">Jurisdiction: {e(r['jurisdiction'])} · Deadline: {e(r['deadline_at'][:10] if r['deadline_at'] else '—')}</p>
        <div class="flex" style="margin-top:10px">{send_btn}</div>
        {status_form}
      </div>
    </div>
    <h2>Generated request</h2>
    <div class="panel">
      <div class="muted small">Subject</div><pre>{e(r['subject'])}</pre>
      <div class="muted small">Body</div><pre>{e(r['body'])}</pre>
    </div>
    <h2>Timeline</h2>
    <div class="panel" style="padding:6px 0">
      <table><tr><th>When (UTC)</th><th>Event</th><th>Detail</th></tr>{ev_rows}</table>
    </div>"""
    return layout(r["broker_name"], "/requests", body)


def brokers_page():
    brokers = db.query("SELECT * FROM brokers ORDER BY enabled DESC, name")
    rows = []
    for b in brokers:
        checked = "checked" if b["enabled"] else ""
        idflag = '<span class="pill" style="color:#f0d27a">ID</span>' if b["requires_id"] else ""
        rows.append(
            f"<tr><td>"
            f"<form method='post' action='/actions/toggle-broker/{b['id']}' style='display:inline'>"
            f"<input type='checkbox' style='width:auto' onchange='this.form.submit()' {checked}></form></td>"
            f"<td><b>{e(b['name'])}</b><br><span class='muted small'>{e(b['website'])}</span></td>"
            f"<td><span class='pill'>{e(b['category'])}</span></td>"
            f"<td><span class='pill'>{e(b['method'])}</span> {idflag}</td>"
            f"<td class='small'>{e(b['jurisdiction'])}</td>"
            f"<td class='small'><a href='{e(b['opt_out_url'])}' target='_blank'>opt-out ↗</a></td></tr>"
        )
    body = f"""
    <h1>Data brokers</h1>
    <p class="sub">{len(brokers)} curated brokers. Toggle which ones to target. "ID" = broker
       may demand identity verification — review before sending.</p>
    <div class="panel" style="padding:6px 0">
      <table><tr><th>On</th><th>Broker</th><th>Type</th><th>Method</th><th>Region</th><th>Link</th></tr>
      {''.join(rows)}</table>
    </div>"""
    return layout("Brokers", "/brokers", body)


def profile_page():
    p = db.get_profile()
    body = f"""
    <h1>Your profile</h1>
    <p class="sub">The identifiers brokers use to find your records. Stored locally in
       <span class="mono">privacymirror.db</span> on this machine only. One value per line where noted.</p>
    <form method="post" action="/actions/profile">
      <div class="panel">
        <label>Full name</label>
        <input name="full_name" value="{e(p.get('full_name',''))}" placeholder="Jane Q. Public">
        <div class="row">
          <div><label>Other names / aliases (one per line)</label>
            <textarea name="aliases">{e(chr(10).join(p.get('aliases',[])))}</textarea></div>
          <div><label>Date of birth</label>
            <input name="date_of_birth" value="{e(p.get('date_of_birth',''))}" placeholder="1990-01-31 or 1990"></div>
        </div>
        <div class="row">
          <div><label>Email addresses (one per line)</label>
            <textarea name="emails">{e(chr(10).join(p.get('emails',[])))}</textarea></div>
          <div><label>Phone numbers (one per line)</label>
            <textarea name="phones">{e(chr(10).join(p.get('phones',[])))}</textarea></div>
        </div>
        <label>Addresses (one per line — full address per line)</label>
        <textarea name="addresses">{e(chr(10).join(p.get('addresses',[])))}</textarea>
        <label>Notes (optional)</label>
        <textarea name="notes">{e(p.get('notes',''))}</textarea>
        <div style="margin-top:16px"><button class="btn">Save profile</button></div>
      </div>
    </form>
    <div class="banner info small">The first email in your list is used as the reply-to / contact
      address inside generated request letters. Consider using a dedicated address you control.</div>
    """
    return layout("Profile", "/profile", body)


def settings_page():
    s = db.all_settings()
    def ck(v):
        return "checked" if s.get(v) == "1" else ""
    def sel(key, val):
        return "selected" if s.get(key) == val else ""
    smtp_ok = mailer.smtp_ready()
    gmail_ok = mailer.gmail_ready()
    gmail_read = mailer.gmail_can_read()
    gmail_email = s.get("gmail_email", "")
    if gmail_read:
        gmail_read_note = '<span class="pill" style="color:#7fe0cd">read access granted</span>'
    elif gmail_ok:
        gmail_read_note = ('<span class="pill" style="color:#f0d27a">no read access — '
                           'reconnect Gmail to enable</span>')
    else:
        gmail_read_note = '<span class="muted">(requires Gmail connected with read access)</span>'

    gmail_status = (f'<span class="pill" style="color:#7fe0cd">connected as {e(gmail_email)}</span>'
                    if gmail_ok else '<span class="pill" style="color:#f0d27a">not connected</span>')
    smtp_status = ('<span class="pill" style="color:#7fe0cd">configured</span>'
                   if smtp_ok else '<span class="pill" style="color:#f0d27a">not configured</span>')

    # Connect/disconnect are separate POSTs (can't nest forms), rendered after the main form.
    connect_block = (
        '<form method="post" action="/actions/disconnect-gmail" style="display:inline">'
        '<button class="btn ghost">Disconnect Gmail</button></form>'
        if gmail_ok else
        '<form method="post" action="/actions/connect-gmail" style="display:inline">'
        '<button class="btn">Connect Gmail →</button></form>'
    )

    body = f"""
    <h1>Settings</h1>
    <p class="sub">Choose how removal emails are sent, then tune automation.</p>

    <form method="post" action="/actions/settings">

      <div class="panel">
        <h2 style="margin-top:0">Sending provider</h2>
        <div class="row">
          <div><label>Send removal emails via</label>
            <select name="send_provider">
              <option value="smtp" {sel('send_provider','smtp')}>SMTP (any account / app password)</option>
              <option value="gmail" {sel('send_provider','gmail')}>Gmail API (your connected Gmail — no app password)</option>
            </select></div>
          <div><label>Gmail action</label>
            <select name="gmail_mode">
              <option value="send" {sel('gmail_mode','send')}>Send immediately (lands in your Sent)</option>
              <option value="draft" {sel('gmail_mode','draft')}>Create draft in Gmail to review first</option>
            </select></div>
        </div>
        <p class="muted small" style="margin-top:6px">Only the selected provider is used. Configure it below.</p>
      </div>

      <div class="panel">
        <h2 style="margin-top:0">Gmail API {gmail_status}</h2>
        <ol class="small muted" style="margin:0 0 12px 18px">
          <li>In Google Cloud Console → APIs &amp; Services → Credentials, create an OAuth
              <b>Desktop app</b> client (and enable the Gmail API for the project).</li>
          <li>Paste its Client ID + Secret below, then <b>Save settings</b>.</li>
          <li>Use the <b>Connect Gmail</b> button (below the form) and approve consent.
              Redirect URI is <span class="mono">{e(REDIRECT_URI)}</span> — loopback, no registration needed.</li>
        </ol>
        <div class="row">
          <div><label>Client ID</label><input name="gmail_client_id" value="{e(s.get('gmail_client_id',''))}"></div>
          <div><label>Client Secret</label><input type="password" name="gmail_client_secret" value="{e(s.get('gmail_client_secret',''))}" placeholder="(re-enter to change)"></div>
        </div>
      </div>

      <div class="panel">
        <h2 style="margin-top:0">SMTP {smtp_status}</h2>
        <div class="row">
          <div><label>SMTP host</label><input name="smtp_host" value="{e(s.get('smtp_host',''))}" placeholder="smtp.gmail.com"></div>
          <div><label>Port</label><input name="smtp_port" value="{e(s.get('smtp_port','587'))}" placeholder="587"></div>
        </div>
        <div class="row">
          <div><label>Username</label><input name="smtp_user" value="{e(s.get('smtp_user',''))}"></div>
          <div><label>Password / app password</label><input type="password" name="smtp_password" value="{e(s.get('smtp_password',''))}" placeholder="(re-enter to change)"></div>
        </div>
        <div class="toggle"><input type="checkbox" style="width:auto" name="smtp_use_tls" value="1" {ck('smtp_use_tls')}>
          <span>Use STARTTLS (standard for port 587; port 465 uses SSL automatically)</span></div>
        <div class="row">
          <div><label>From email</label><input name="from_email" value="{e(s.get('from_email',''))}"></div>
          <div><label>From name</label><input name="from_name" value="{e(s.get('from_name',''))}"></div>
        </div>
      </div>

      <div class="panel">
        <h2 style="margin-top:0">Automation</h2>
        <div class="banner warn small">Auto-send is the master switch. With dry-run ON, a "send"
          only logs what it <i>would</i> do — nothing leaves your machine. Turn dry-run OFF only
          after you've verified your profile, broker list, and a test message.</div>
        <div class="toggle"><input type="checkbox" style="width:auto" name="auto_send_enabled" value="1" {ck('auto_send_enabled')}>
          <span><b>Enable auto-send</b> — background scheduler sends pending requests + follow-ups</span></div>
        <div class="toggle"><input type="checkbox" style="width:auto" name="dry_run" value="1" {ck('dry_run')}>
          <span><b>Dry run</b> — simulate sends (log only). Recommended ON until tested.</span></div>
        <div class="row">
          <div><label>Run interval (minutes)</label><input name="send_interval_minutes" value="{e(s.get('send_interval_minutes','1440'))}"></div>
          <div><label>Max sends per pass</label><input name="max_sends_per_pass" value="{e(s.get('max_sends_per_pass','5'))}"></div>
          <div><label>Follow-up after (days)</label><input name="follow_up_after_days" value="{e(s.get('follow_up_after_days','35'))}"></div>
        </div>
        <hr style="border:none;border-top:1px solid var(--line);margin:18px 0">
        <div class="toggle"><input type="checkbox" style="width:auto" name="recheck_enabled" value="1" {ck('recheck_enabled')}>
          <span><b>Recurring re-removal</b> — periodically re-generate requests so brokers that
            re-list you get re-requested. Runs even with auto-send off (it just queues the work).</span></div>
        <div class="row">
          <div><label>Re-request a broker every (days)</label><input name="recheck_interval_days" value="{e(s.get('recheck_interval_days','90'))}"></div>
          <div></div><div></div>
        </div>
        <hr style="border:none;border-top:1px solid var(--line);margin:18px 0">
        <div class="toggle"><input type="checkbox" style="width:auto" name="ingest_replies_enabled" value="1" {ck('ingest_replies_enabled')}>
          <span><b>Read broker replies</b> (Gmail only) — find replies from brokers you contacted
            and advance status automatically. {gmail_read_note}</span></div>
        <div class="row">
          <div><label>Reply handling</label>
            <select name="reply_classify_mode">
              <option value="ack" {sel('reply_classify_mode','ack')}>Acknowledge + flag (suggest Completed/Rejected, you confirm)</option>
              <option value="full" {sel('reply_classify_mode','full')}>Full auto-classify (auto-set Completed/Rejected)</option>
              <option value="off" {sel('reply_classify_mode','off')}>Log only (never change status)</option>
            </select></div>
          <div></div>
        </div>
      </div>

      <button class="btn">Save settings</button>
    </form>

    <div class="panel">
      <h2 style="margin-top:0">Connect Gmail</h2>
      <p class="muted small">Save your Client ID + Secret first, then connect. {e(gmail_email) and ('Currently connected as ' + e(gmail_email) + '.') or ''}</p>
      {connect_block}
    </div>

    <div class="panel">
      <h2 style="margin-top:0">Test sending</h2>
      <p class="muted small">Sends one real test message via the selected provider (ignores dry-run).
        In Gmail draft mode it creates a draft instead.</p>
      <form method="post" action="/actions/test-smtp" class="flex">
        <input name="to" placeholder="your@email.com" style="flex:1">
        <button class="btn ghost">Send test</button>
      </form>
    </div>
    <div class="banner info small">For <b>SMTP</b>, Gmail/Outlook require an app password + 2FA.
      For the <b>Gmail API</b>, no app password is needed. Either way, credentials are stored in
      plaintext in the local SQLite file — this is a personal, single-machine tool.</div>
    """
    return layout("Settings", "/settings", body)

# PrivacyMirror

A personal, self-hosted service that mirrors what [Incogni](https://incogni.com) does:
it keeps a list of **data brokers**, holds a **profile** of your personal identifiers,
generates **law-grounded deletion requests** (CCPA/CPRA + GDPR Article 17), **sends**
them, and **tracks** each one through its legal response deadline — including automatic
follow-ups when a broker misses the deadline.

Everything runs locally on your machine. Your data lives in a single SQLite file
(`privacymirror.db`) and never leaves your computer except as the deletion emails you send.

- **Stack:** Python standard library only — no `pip install`, no external services.
- **Storage:** local SQLite (`privacymirror.db`).
- **UI:** a small web dashboard at `http://127.0.0.1:8765`.

---

## Quick start

```powershell
# from this folder
python server.py
```

…or just double-click **`run.bat`**. Your browser opens to the dashboard automatically.

Then:

1. **Profile** → enter your name, emails, phones, addresses. These are the identifiers
   brokers use to find your records. (Tip: use a dedicated email you control as the first one.)
2. **Brokers** → review the 25 seeded brokers; toggle off any you don't care about.
3. **Dashboard** → **Generate requests for enabled brokers**. This creates one request per broker:
   - email-capable brokers become **Pending** (can be auto-sent),
   - form/phone-only brokers become **Needs manual action** with a direct opt-out link.
4. **Settings** → configure SMTP and the automation switches (see below).
5. **Dashboard** → **Run a send pass now**, or let the background scheduler do it.

---

## Safety model (read this before turning on sending)

The app ships **safe by default**:

| Switch | Default | Meaning |
|---|---|---|
| **Auto-send** | OFF | Master switch. While off, the scheduler runs but sends nothing. |
| **Dry run** | ON | A "send" only **logs what it would do** — no email touches SMTP. |

Nothing is ever emailed until **all** of these are true: your profile is complete, SMTP is
configured, **Auto-send is ON**, and **Dry run is OFF**. Recommended path:

1. Fill profile + pick brokers.
2. Configure SMTP, click **Send test email**, confirm you receive it.
3. Keep **Dry run ON**, run a pass, and read the request letters on each request's detail page.
4. Only then turn **Dry run OFF** to send for real.

Only brokers whose removal method is **email** are ever auto-sent. Form/phone brokers always
require you to act manually (the app gives you the exact link and tracks the status you set).

---

## How sending works

- **Pending email requests** are sent (CCPA gives brokers 45 days to respond; GDPR 30).
- Each send sets a **deadline**. When a deadline passes with no response, the next scheduler
  pass marks the request **Overdue** and sends a **follow-up** (up to 2 follow-ups).
- `max_sends_per_pass` rate-limits each pass so you don't blast everything at once.
- Update a request's status manually (Acknowledged / Completed / Rejected) as brokers reply.

### Recurring re-removal (Settings → Automation)
Data brokers re-acquire and re-list people over time — this is exactly why Incogni is a
subscription. Turn on **Recurring re-removal** and the scheduler will, on each pass:

- create a request for any enabled broker that has none,
- leave in-progress brokers alone, and
- **re-request** a broker once **Re-request every (N days)** has elapsed since its last
  request was **Completed** or **Rejected** (default 90 days).

It runs even with auto-send **off** — in that case it just queues the new requests for you
to review and send manually. With auto-send on, the re-generated requests are sent on the
same pass (subject to the per-pass limit).

### Automated reply tracking (Gmail only)
Closes the last big manual loop: instead of you watching your inbox and marking each
broker's response, the app reads replies for you. Requires Gmail connected **with read
access** (the `gmail.readonly` scope — if you connected before this feature, click
**Connect Gmail** again to grant it). On each pass (or via **Sync replies now**) it
searches Gmail for messages from each contacted broker's domain, attaches them to the
request timeline, and advances status per **Reply handling**:

- **Acknowledge + flag** (default, recommended): any reply → **Acknowledged**; replies
  asking you to verify/confirm → **Needs action**; replies that look like a completion or
  rejection are **suggested** (one click to confirm in Requests) but never finalized.
- **Full auto-classify**: also auto-sets **Completed** / **Rejected** on high-confidence
  phrases. Most hands-off; small risk of a misread.
- **Log only**: attach replies to the timeline, never change status.

It only reads mail from domains of brokers you actually contacted, and ingests each
message once.

---

## How automated can this get? (the "sound" boundary)

Fully hands-off, once configured: **generation → sending → follow-ups → recurring
re-removal → reply tracking → background runs**. Turn on auto-send (live), recurring
re-removal, and reply tracking, install the scheduled task, and email-based removals run
end-to-end without you.

Deliberately kept **manual** because automating them isn't sound:

- **Web-form opt-outs (~18 of 25 brokers):** most people-search sites only accept removals
  through a web form behind a CAPTCHA, and their terms forbid bots. The app gives you a
  precise per-broker checklist + deep link instead of scripting a fragile, ToS-violating
  browser bot. Mark these **Sent** once you submit them.
- **Clicking verification links** in broker emails: programmatically clicking links from
  email is a security risk, so these are surfaced as **Needs action** for you to handle.
- **Finalizing "Completed"** from a fuzzy keyword match (in the default mode): a misread
  could make you believe you're removed when you aren't, so it's a one-click confirm.

---

## Run passes even when the app is closed (Windows Task Scheduler)

The dashboard runs an in-process scheduler only while `server.py` is open. To keep
removals and recurring re-removals firing in the background, install a Windows Scheduled
Task that runs a single headless pass daily:

```powershell
# from this folder, in PowerShell
.\schedule-task.ps1                 # daily at 09:00 (default)
.\schedule-task.ps1 -Time 18:30     # pick your own time
```

No admin rights required — the task runs as you, only when you're logged on, with no
console window. It invokes **`runpass.py`**, which runs one pass (re-generate due
requests → send → follow-ups, per your settings) and exits.

```powershell
Start-ScheduledTask -TaskName PrivacyMirror   # run it now to test
.\schedule-task.ps1 -Uninstall                # remove it
```

You can also run a pass by hand at any time: `python runpass.py`. Results land in the
dashboard's **Recent activity** and in `runpass.log`. The headless runner and the web app
safely share the database (SQLite WAL + busy timeout), so it's fine to leave both around.

### Choosing a sending provider (Settings → Sending provider)

**Option A — Gmail API (recommended, no app password).** Sends from your real Gmail
account; sent requests land in your **Sent** folder as a paper trail. Uses OAuth2 over
pure stdlib — no extra packages. One-time setup:

1. In [Google Cloud Console](https://console.cloud.google.com/) → *APIs & Services*:
   enable the **Gmail API**, then under *Credentials* create an **OAuth client ID** of
   type **Desktop app**.
2. In PrivacyMirror → **Settings → Gmail API**, paste the **Client ID** and **Client
   Secret**, click **Save settings**.
3. Click **Connect Gmail** and approve consent in your browser. The app stores a refresh
   token locally and sets the provider to Gmail. (Redirect URI is the loopback
   `http://127.0.0.1:8765/oauth/gmail/callback` — Desktop-app clients allow this with no
   registration.)
4. Pick a **Gmail action**: *Send immediately*, or *Create draft in Gmail to review first*
   (draft mode parks the request as **Queued** with no deadline until you send it from Gmail).

**Option B — SMTP.** Works with any email account. Gmail/Outlook require an **app
password** (with 2FA enabled), not your normal password.
- Gmail: `smtp.gmail.com`, port `587`, STARTTLS on. Port `465` uses implicit SSL.

Either way, credentials are stored in plaintext in the local SQLite file — this is a
single-machine personal tool, so treat the file accordingly.

---

## Files

| File | Purpose |
|---|---|
| `server.py` | HTTP server, routing, app entry point (`python server.py`) |
| `views.py` | HTML rendering for every page |
| `db.py` | SQLite schema + storage helpers |
| `seed.py` | The curated ~25-broker starter list |
| `letters.py` | CCPA/GDPR request-letter generation |
| `mailer.py` | Provider-agnostic sending + the background removal scheduler |
| `gmail.py` | Gmail API send/draft/read over OAuth2 (stdlib only) |
| `inbox.py` | Reads broker replies and advances request status |
| `runpass.py` | Headless one-shot pass runner (for the scheduled task / cron) |
| `schedule-task.ps1` | Installs/removes the Windows Scheduled Task |
| `privacymirror.db` | Your local database (created on first run) |

## Adding or editing brokers
Edit `seed.py` to add entries (they seed on first run), or toggle existing ones in the
**Brokers** page. Set `method="email"` + a `privacy_email` to make a broker auto-sendable.

---

## Disclaimers
- The generated letters are **templates, not legal advice**.
- Broker opt-out URLs, emails, and procedures **change frequently** — verify before relying on them.
- Some brokers re-list you over time; re-run generation periodically (this is exactly why
  Incogni charges a subscription). You can schedule `server.py` to stay running.
- Respect each broker's process and applicable law. This tool sends *your own* lawful
  data-subject requests about *your own* data.

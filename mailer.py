"""Email sending + the automated removal scheduler.

Safety model:
  - dry_run=1 (default): "sending" only writes an event log entry; no SMTP.
  - auto_send_enabled=0 (default): the scheduler loop runs but sends nothing.
  - Only brokers with method="email" and a privacy_email are ever auto-sent.
    form/phone/mail brokers are flagged needs_action for the human.
Nothing leaves the machine until SMTP is configured AND both switches are on.
"""

import smtplib
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import db
import gmail
import letters

_SCHEDULER_THREAD = None
_STOP = threading.Event()


# ---------- low-level send ----------

def _smtp_config():
    s = db.all_settings()
    return {
        "host": s.get("smtp_host", ""),
        "port": int(s.get("smtp_port") or 587),
        "user": s.get("smtp_user", ""),
        "password": s.get("smtp_password", ""),
        "use_tls": s.get("smtp_use_tls", "1") == "1",
        "from_email": s.get("from_email", "") or s.get("smtp_user", ""),
        "from_name": s.get("from_name", ""),
    }


def smtp_ready():
    c = _smtp_config()
    return bool(c["host"] and c["from_email"])


def gmail_ready():
    s = db.all_settings()
    return bool(s.get("gmail_client_id") and s.get("gmail_client_secret")
                and s.get("gmail_refresh_token") and s.get("gmail_email"))


def gmail_can_read():
    """True if Gmail is connected AND the readonly scope was granted."""
    return gmail_ready() and (gmail.READ_SCOPE in (db.get_setting("gmail_scopes") or ""))


def provider():
    return db.get_setting("send_provider", "smtp")


def sender_ready():
    """Is the currently-selected provider configured to send?"""
    return gmail_ready() if provider() == "gmail" else smtp_ready()


def _send_via_gmail(to_addr, subject, body):
    s = db.all_settings()
    access = gmail.get_access_token(s["gmail_client_id"], s["gmail_client_secret"],
                                    s["gmail_refresh_token"])
    from_addr = s.get("gmail_email", "")
    if s.get("gmail_mode") == "draft":
        gmail.create_draft(access, from_addr, to_addr, subject, body)
        return "draft"
    gmail.send_message(access, from_addr, to_addr, subject, body)
    return "sent"


def send_email(to_addr, subject, body):
    """Deliver an email via the selected provider. Raises on failure.

    Returns a short verb describing what happened ("sent" or "draft").
    """
    if provider() == "gmail":
        if not gmail_ready():
            raise RuntimeError("Gmail not connected")
        return _send_via_gmail(to_addr, subject, body)
    return _send_via_smtp(to_addr, subject, body)


def _send_via_smtp(to_addr, subject, body):
    c = _smtp_config()
    if not c["host"]:
        raise RuntimeError("SMTP host not configured")
    msg = EmailMessage()
    from_hdr = f'{c["from_name"]} <{c["from_email"]}>' if c["from_name"] else c["from_email"]
    msg["From"] = from_hdr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    if c["port"] == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(c["host"], c["port"], context=ctx, timeout=30) as server:
            if c["user"]:
                server.login(c["user"], c["password"])
            server.send_message(msg)
    else:
        with smtplib.SMTP(c["host"], c["port"], timeout=30) as server:
            if c["use_tls"]:
                server.starttls(context=ssl.create_default_context())
            if c["user"]:
                server.login(c["user"], c["password"])
            server.send_message(msg)
    return "sent"


def send_test_email(to_addr):
    verb = send_email(to_addr, "PrivacyMirror test",
                      "This is a test message from your PrivacyMirror instance. "
                      "If you received it (or see it in Drafts), sending works.")
    return verb


# ---------- request lifecycle ----------

def _insert_request(broker, profile, recheck=False):
    """Insert one fresh request for a broker and log it. Returns the new row id."""
    subject = letters.build_subject(broker)
    body = letters.build_body(broker, profile)
    # email-capable brokers go to 'pending' (auto-sendable); others need a human.
    status = "pending" if (broker["method"] == "email" and broker["privacy_email"]) else "needs_action"
    cur = db.execute(
        """INSERT INTO requests
           (broker_id, status, method, subject, body, created_at, last_update)
           VALUES (?,?,?,?,?,?,?)""",
        (broker["id"], status, broker["method"], subject, body, db.now_iso(), db.now_iso()),
    )
    kind = "recheck" if recheck else "created"
    verb = "Recurring re-removal request created" if recheck else "Request created"
    db.log_event(cur.lastrowid, kind,
                 f"{verb} for {broker['name']} (method={broker['method']}, status={status})")
    return cur.lastrowid


def create_requests_for_enabled(only_missing=True):
    """Create a removal request row per enabled broker. Returns count created."""
    profile = db.get_profile()
    brokers = db.query("SELECT * FROM brokers WHERE enabled = 1")
    created = 0
    for b in brokers:
        if only_missing:
            existing = db.query_one(
                "SELECT id FROM requests WHERE broker_id = ? AND status NOT IN ('completed','rejected')",
                (b["id"],),
            )
            if existing:
                continue
        _insert_request(b, profile)
        created += 1
    return created


def create_recheck_requests(interval_days):
    """Recurring re-removal: (re)generate requests for enabled brokers.

    - A broker with an in-progress (non-terminal) request is left alone.
    - A broker never requested gets a fresh request.
    - A broker whose latest request finished (completed/rejected) gets a NEW
      request once `interval_days` have elapsed since that request's last update,
      because brokers re-list people over time. Returns count created.
    """
    profile = db.get_profile()
    now = datetime.now(timezone.utc)
    brokers = db.query("SELECT * FROM brokers WHERE enabled = 1")
    created = 0
    for b in brokers:
        active = db.query_one(
            "SELECT id FROM requests WHERE broker_id = ? AND status NOT IN ('completed','rejected')",
            (b["id"],),
        )
        if active:
            continue  # already working on this broker
        latest = db.query_one(
            "SELECT * FROM requests WHERE broker_id = ? ORDER BY id DESC LIMIT 1", (b["id"],)
        )
        if latest is None:
            _insert_request(b, profile)            # never requested
            created += 1
            continue
        # latest is terminal — only re-request after the interval elapses
        try:
            last = datetime.strptime(latest["last_update"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            last = now  # malformed timestamp -> wait a full interval from now
        if (now - last).days >= int(interval_days):
            _insert_request(b, profile, recheck=True)
            created += 1
    return created


def _mark_sent(req, broker):
    """Record a real send: start the legal response clock."""
    days = 30 if broker.get("jurisdiction") == "EU" else 45
    deadline = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "UPDATE requests SET status='sent', sent_at=?, deadline_at=?, last_update=? WHERE id=?",
        (db.now_iso(), deadline, db.now_iso(), req["id"]),
    )
    db.log_event(req["id"], "sent", f"Emailed {broker['privacy_email']} via {provider()}")


def send_request(req_id, force=False):
    """Send a single request now. Honors dry_run unless force=True (real send).

    Returns (ok, message). In Gmail 'draft' mode a draft is created for review and
    the request is parked as 'queued' (no deadline yet — you send it from Gmail).
    """
    req = db.query_one("SELECT * FROM requests WHERE id = ?", (req_id,))
    if not req:
        return False, "request not found"
    broker = db.query_one("SELECT * FROM brokers WHERE id = ?", (req["broker_id"],))
    if broker["method"] != "email" or not broker["privacy_email"]:
        return False, "broker is not email-capable; complete the opt-out manually"

    dry_run = db.get_setting("dry_run", "1") == "1" and not force
    if dry_run:
        _mark_sent(req, broker)  # simulate the lifecycle transition
        # _mark_sent logged 'sent'; relabel as a dry run for clarity
        db.log_event(req["id"], "dry_run",
                     f"[DRY RUN] Would email {broker['privacy_email']} via {provider()}")
        return True, "dry-run logged (no email sent)"

    if not sender_ready():
        return False, f"{provider()} not configured"
    try:
        verb = send_email(broker["privacy_email"], req["subject"], req["body"])
    except Exception as e:  # noqa: BLE001 — surface any send error to the UI
        db.log_event(req_id, "error", f"Send failed: {e}")
        return False, f"send failed: {e}"

    if verb == "draft":
        db.execute("UPDATE requests SET status='queued', last_update=? WHERE id=?",
                   (db.now_iso(), req_id))
        db.execute("UPDATE requests SET response_notes=? WHERE id=?",
                   ("Draft created in Gmail — review and send it, then mark as Sent.", req_id))
        db.log_event(req_id, "draft", f"Draft created in Gmail for {broker['privacy_email']}")
        return True, "draft created in Gmail (review & send it there)"

    _mark_sent(req, broker)
    return True, "sent"


def set_status(req_id, status, note=""):
    db.execute("UPDATE requests SET status=?, last_update=? WHERE id=?",
               (status, db.now_iso(), req_id))
    db.log_event(req_id, "status_change", f"-> {status}" + (f": {note}" if note else ""))
    if note:
        db.execute("UPDATE requests SET response_notes=? WHERE id=?", (note, req_id))


# ---------- scheduler ----------

def run_pass():
    """One automated pass: (re)generate due requests, send, flag overdue, follow up.

    Recurring generation is gated by `recheck_enabled` and runs even if auto-send
    is off (so you can have it queue work for manual review). Sending is gated
    separately by `auto_send_enabled`.
    """
    parts = []
    profile_ok = db.profile_is_complete()

    # 0a) ingest broker replies (read-only) and advance status
    if db.get_setting("ingest_replies_enabled", "1") == "1" and gmail_can_read():
        import inbox  # lazy import avoids a circular dependency at module load
        res = inbox.ingest_replies()
        if res.get("ok") and res.get("found"):
            parts.append(f"{res['found']} reply(ies) ingested")

    # 0) recurring re-removal: (re)generate requests on the configured cadence
    if db.get_setting("recheck_enabled", "0") == "1":
        if not profile_ok:
            parts.append("recheck skipped (profile incomplete)")
        else:
            n = create_recheck_requests(int(db.get_setting("recheck_interval_days") or 90))
            parts.append(f"{n} request(s) (re)generated" if n else "no rechecks due")

    if db.get_setting("auto_send_enabled", "0") != "1":
        parts.append("auto-send off")
        return "; ".join(parts) or "auto-send off"
    if not profile_ok:
        parts.append("not sending (profile incomplete)")
        return "; ".join(parts)

    max_sends = int(db.get_setting("max_sends_per_pass") or 5)
    follow_after = int(db.get_setting("follow_up_after_days") or 35)
    sent = 0

    # 1) send pending email requests
    pending = db.query(
        "SELECT * FROM requests WHERE status='pending' AND method='email' ORDER BY id"
    )
    for req in pending:
        if sent >= max_sends:
            break
        ok, _ = send_request(req["id"])
        if ok:
            sent += 1

    # 2) flag overdue sent requests + queue a follow-up
    now = datetime.now(timezone.utc)
    in_flight = db.query("SELECT * FROM requests WHERE status='sent' AND deadline_at IS NOT NULL")
    for req in in_flight:
        try:
            deadline = datetime.strptime(req["deadline_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if now > deadline:
            if (req.get("follow_up_count") or 0) < 2 and sent < max_sends:
                broker = db.query_one("SELECT * FROM brokers WHERE id=?", (req["broker_id"],))
                dry = db.get_setting("dry_run", "1") == "1"
                follow_subject = "Follow-up: " + req["subject"]
                follow_body = ("This is a follow-up to my prior request, to which I have not "
                               "received a response within the statutory deadline.\n\n" + req["body"])
                if not dry and sender_ready() and broker["privacy_email"]:
                    try:
                        send_email(broker["privacy_email"], follow_subject, follow_body)
                    except Exception as e:  # noqa: BLE001
                        db.log_event(req["id"], "error", f"Follow-up failed: {e}")
                        continue
                db.execute(
                    "UPDATE requests SET status='overdue', follow_up_count=follow_up_count+1, last_update=? WHERE id=?",
                    (db.now_iso(), req["id"]),
                )
                db.log_event(req["id"], "follow_up",
                             ("[DRY RUN] " if dry else "") + "Sent follow-up past deadline")
                sent += 1
            else:
                db.execute("UPDATE requests SET status='overdue', last_update=? WHERE id=?",
                           (db.now_iso(), req["id"]))
    parts.append(f"{sent} message(s) processed")
    return "; ".join(parts)


def _loop():
    # small startup delay so the web server is up first
    _STOP.wait(5)
    while not _STOP.is_set():
        try:
            interval_min = int(db.get_setting("send_interval_minutes") or 1440)
            run_pass()
        except Exception as e:  # noqa: BLE001 — scheduler must never die
            try:
                db.log_event(None, "error", f"scheduler pass error: {e}")
            except Exception:
                pass
            interval_min = 1440
        # sleep in short chunks so stop() is responsive
        slept = 0
        while slept < interval_min * 60 and not _STOP.is_set():
            _STOP.wait(10)
            slept += 10


def start_scheduler():
    global _SCHEDULER_THREAD
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return
    _STOP.clear()
    _SCHEDULER_THREAD = threading.Thread(target=_loop, name="pm-scheduler", daemon=True)
    _SCHEDULER_THREAD.start()


def stop_scheduler():
    _STOP.set()

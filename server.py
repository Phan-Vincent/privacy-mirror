"""PrivacyMirror — a local, single-user web app that mirrors what Incogni does:
finds data brokers, sends law-grounded deletion requests, and tracks them.

Run:   python server.py
Then open http://127.0.0.1:8765 in your browser.

Stdlib only. Storage is a local SQLite file (privacymirror.db).
"""

import html as _html
import re
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
import gmail
import mailer
import views

HOST = "127.0.0.1"
PORT = 8765
REDIRECT_URI = f"http://{HOST}:{PORT}/oauth/gmail/callback"

# transient OAuth state tokens (CSRF protection for the loopback flow)
_OAUTH_STATES = set()

# list-style profile fields parsed from textareas (one value per line)
LIST_FIELDS = ("aliases", "emails", "phones", "addresses")


def _lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _flash_into(html_doc, flash):
    if not flash:
        return html_doc
    kind, msg = flash
    banner = f'<div class="banner {_html.escape(kind)}">{_html.escape(msg)}</div>'
    return html_doc.replace('<div class="wrap">', '<div class="wrap">' + banner, 1)


class Handler(BaseHTTPRequestHandler):
    server_version = "PrivacyMirror/1.0"

    def log_message(self, fmt, *args):  # quieter console
        return

    # ---- helpers ----
    def _send(self, body, status=200, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location, flash=None):
        if flash:
            sep = "&" if "?" in location else "?"
            location = f"{location}{sep}_k={urllib.parse.quote(flash[0])}&_m={urllib.parse.quote(flash[1])}"
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _read_form(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    def _query(self):
        q = urllib.parse.urlparse(self.path).query
        parsed = urllib.parse.parse_qs(q)
        return {k: v[0] for k, v in parsed.items()}

    # ---- GET ----
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        q = self._query()
        flash = None
        if q.get("_k") and q.get("_m"):
            flash = (q["_k"], q["_m"])

        try:
            if path == "/":
                return self._send(_flash_into(views.dashboard(), flash))
            if path == "/requests":
                return self._send(_flash_into(views.requests_page(q.get("status")), flash))
            m = re.match(r"^/requests/(\d+)$", path)
            if m:
                doc = views.request_detail(int(m.group(1)))
                if doc is None:
                    return self._send("Not found", 404, "text/plain")
                return self._send(_flash_into(doc, flash))
            if path == "/brokers":
                return self._send(_flash_into(views.brokers_page(), flash))
            if path == "/profile":
                return self._send(_flash_into(views.profile_page(), flash))
            if path == "/settings":
                return self._send(_flash_into(views.settings_page(), flash))
            if path == "/oauth/gmail/callback":
                return self._gmail_callback(q)
            if path == "/favicon.ico":
                return self._send(b"", 204, "image/x-icon")
            return self._send("Not found", 404, "text/plain")
        except Exception as e:  # noqa: BLE001
            return self._send(f"<pre>Server error: {_html.escape(str(e))}</pre>", 500)

    # ---- Gmail OAuth ----
    def _gmail_callback(self, q):
        state = q.get("state", "")
        if state not in _OAUTH_STATES:
            return self._redirect("/settings", ("warn", "OAuth state mismatch — try again."))
        _OAUTH_STATES.discard(state)
        if q.get("error"):
            return self._redirect("/settings", ("warn", f"Google denied access: {q['error']}"))
        code = q.get("code", "")
        if not code:
            return self._redirect("/settings", ("warn", "No authorization code returned."))
        s = db.all_settings()
        try:
            tok = gmail.exchange_code(s["gmail_client_id"], s["gmail_client_secret"],
                                      code, REDIRECT_URI)
            refresh = tok.get("refresh_token")
            access = tok.get("access_token")
            if not refresh:
                return self._redirect("/settings",
                                      ("warn", "Google did not return a refresh token. "
                                       "Remove the app's access in your Google account, then reconnect."))
            email = gmail.get_user_email(access) if access else ""
            db.set_setting("gmail_refresh_token", refresh)
            db.set_setting("gmail_email", email)
            db.set_setting("gmail_scopes", tok.get("scope", ""))
            db.set_setting("send_provider", "gmail")
            read = "with reply-reading" if gmail.READ_SCOPE in tok.get("scope", "") else "send-only"
            return self._redirect("/settings",
                                  ("ok", f"Gmail connected as {email} ({read}). Provider set to Gmail."))
        except Exception as e:  # noqa: BLE001
            return self._redirect("/settings", ("warn", f"Gmail connection failed: {e}"))

    # ---- POST ----
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            form = self._read_form()

            if path == "/actions/profile":
                data = {
                    "full_name": form.get("full_name", "").strip(),
                    "date_of_birth": form.get("date_of_birth", "").strip(),
                    "notes": form.get("notes", "").strip(),
                }
                for f in LIST_FIELDS:
                    data[f] = _lines(form.get(f, ""))
                db.save_profile(data)
                return self._redirect("/profile", ("ok", "Profile saved."))

            if path == "/actions/settings":
                checkboxes = ("auto_send_enabled", "dry_run", "smtp_use_tls",
                              "recheck_enabled", "ingest_replies_enabled")
                text_keys = ("send_provider", "gmail_mode", "gmail_client_id",
                             "gmail_client_secret", "smtp_host", "smtp_port",
                             "smtp_user", "smtp_password", "from_email", "from_name",
                             "send_interval_minutes", "max_sends_per_pass",
                             "follow_up_after_days", "recheck_interval_days",
                             "reply_classify_mode")
                for k in text_keys:
                    if k in form:
                        db.set_setting(k, form.get(k, "").strip())
                for k in checkboxes:
                    db.set_setting(k, "1" if form.get(k) == "1" else "0")
                msg = "Settings saved."
                if form.get("auto_send_enabled") == "1" and form.get("dry_run") != "1":
                    msg += " LIVE sending is now ON."
                return self._redirect("/settings", ("ok", msg))

            if path == "/actions/test-smtp":
                to = form.get("to", "").strip()
                if not to:
                    return self._redirect("/settings", ("warn", "Enter an address to test."))
                try:
                    verb = mailer.send_test_email(to)
                    word = "drafted in Gmail" if verb == "draft" else "sent"
                    return self._redirect("/settings", ("ok", f"Test message {word} (to {to})."))
                except Exception as e:  # noqa: BLE001
                    return self._redirect("/settings", ("warn", f"Test failed: {e}"))

            if path == "/actions/connect-gmail":
                cid = db.get_setting("gmail_client_id", "")
                csec = db.get_setting("gmail_client_secret", "")
                if not cid or not csec:
                    return self._redirect("/settings",
                                          ("warn", "Save your Gmail Client ID and Secret first."))
                state = secrets.token_urlsafe(24)
                _OAUTH_STATES.add(state)
                return self._redirect(gmail.build_auth_url(cid, REDIRECT_URI, state))

            if path == "/actions/disconnect-gmail":
                db.set_setting("gmail_refresh_token", "")
                db.set_setting("gmail_email", "")
                db.set_setting("send_provider", "smtp")
                return self._redirect("/settings", ("ok", "Gmail disconnected. Provider set back to SMTP."))

            if path == "/actions/generate":
                if not db.profile_is_complete():
                    return self._redirect("/", ("warn", "Complete your profile first."))
                n = mailer.create_requests_for_enabled()
                return self._redirect("/requests", ("ok", f"Generated {n} new request(s)."))

            if path == "/actions/run-pass":
                result = mailer.run_pass()
                return self._redirect("/", ("info", f"Send pass: {result}"))

            if path == "/actions/sync-replies":
                import inbox
                res = inbox.ingest_replies()
                if not res.get("ok"):
                    return self._redirect("/", ("warn", f"Reply sync: {res.get('reason')}"))
                acts = ", ".join(f"{k}:{v}" for k, v in res.get("actions", {}).items()) or "no new replies"
                return self._redirect("/", ("ok", f"Reply sync ({res['mode']}): {res['found']} ingested — {acts}"))

            m = re.match(r"^/actions/send/(\d+)$", path)
            if m:
                ok, msg = mailer.send_request(int(m.group(1)))
                return self._redirect(f"/requests/{m.group(1)}",
                                      ("ok" if ok else "warn", msg))

            m = re.match(r"^/actions/status/(\d+)$", path)
            if m:
                mailer.set_status(int(m.group(1)), form.get("status", "pending"),
                                  form.get("note", "").strip())
                return self._redirect(f"/requests/{m.group(1)}", ("ok", "Status updated."))

            m = re.match(r"^/actions/toggle-broker/(\d+)$", path)
            if m:
                bid = int(m.group(1))
                cur = db.query_one("SELECT enabled FROM brokers WHERE id=?", (bid,))
                if cur:
                    db.execute("UPDATE brokers SET enabled=? WHERE id=?",
                               (0 if cur["enabled"] else 1, bid))
                return self._redirect("/brokers")

            return self._send("Not found", 404, "text/plain")
        except Exception as e:  # noqa: BLE001
            return self._send(f"<pre>Server error: {_html.escape(str(e))}</pre>", 500)


def main():
    db.init_db(seed_brokers=True)
    mailer.start_scheduler()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print("=" * 56)
    print("  PrivacyMirror — your personal data-removal service")
    print("=" * 56)
    print(f"  Open: {url}")
    print("  Mode: auto-send OFF, dry-run ON (safe defaults)")
    print("  Ctrl+C to stop.")
    print("=" * 56)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        mailer.stop_scheduler()
        httpd.shutdown()


if __name__ == "__main__":
    main()

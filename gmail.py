"""Gmail API sending over OAuth2 — pure standard library (urllib).

Why this instead of SMTP app passwords:
  - sends from your real Gmail account, so requests land in your "Sent" folder
    (a useful paper trail for data-subject requests),
  - uses OAuth2 instead of an app password.

One-time setup (done once in Google Cloud Console, then once in the app):
  1. Create an OAuth 2.0 Client ID of type "Desktop app".
  2. Paste its Client ID + Client Secret into Settings → Gmail.
  3. Click "Connect Gmail" and approve consent in your browser.
The app stores a refresh token locally and uses it to send.

Loopback redirect (http://127.0.0.1:PORT/...) is permitted for Desktop-app
clients, so no public redirect URI registration is needed.
"""

import base64
import json
import re
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
# send: deliver mail; compose: create/manage drafts; readonly: find & read broker
# replies so status can be tracked; userinfo.email: know which account consented.
READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = ("https://www.googleapis.com/auth/gmail.send "
          "https://www.googleapis.com/auth/gmail.compose "
          f"{READ_SCOPE} "
          "https://www.googleapis.com/auth/userinfo.email")
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

# in-memory access-token cache: {refresh_token: (access_token, expires_at)}
_TOKEN_CACHE = {}


def _post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Google OAuth error {e.code}: {body}") from e


def _post_json(url, payload, access_token):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Gmail API error {e.code}: {body}") from e


# ---------- OAuth flow ----------

def build_auth_url(client_id, redirect_uri, state):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",   # request a refresh token
        "prompt": "consent",        # force refresh_token even on re-auth
        "state": state,
    }
    return AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params)


def exchange_code(client_id, client_secret, code, redirect_uri):
    """Trade an authorization code for tokens. Returns the token dict."""
    return _post_form(TOKEN_ENDPOINT, {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })


def get_access_token(client_id, client_secret, refresh_token):
    """Return a valid access token, refreshing (and caching) as needed."""
    cached = _TOKEN_CACHE.get(refresh_token)
    if cached and cached[1] - 60 > time.time():
        return cached[0]
    tok = _post_form(TOKEN_ENDPOINT, {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    access = tok["access_token"]
    expires_at = time.time() + int(tok.get("expires_in", 3600))
    _TOKEN_CACHE[refresh_token] = (access, expires_at)
    return access


# ---------- message building + send ----------

def _raw_message(from_addr, to_addr, subject, body):
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def send_message(access_token, from_addr, to_addr, subject, body):
    raw = _raw_message(from_addr, to_addr, subject, body)
    return _post_json(f"{API_BASE}/messages/send", {"raw": raw}, access_token)


def create_draft(access_token, from_addr, to_addr, subject, body):
    raw = _raw_message(from_addr, to_addr, subject, body)
    return _post_json(f"{API_BASE}/drafts", {"message": {"raw": raw}}, access_token)


def get_user_email(access_token):
    """Return the email address of the consenting Google account."""
    return _get(USERINFO_ENDPOINT, access_token).get("email", "")


# ---------- reading replies ----------

def _get(url, access_token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Gmail API error {e.code}: {body}") from e


def search_message_ids(access_token, q, max_results=10):
    """Return a list of message ids matching a Gmail search query."""
    url = (f"{API_BASE}/messages?q={urllib.parse.quote(q)}"
           f"&maxResults={int(max_results)}")
    data = _get(url, access_token)
    return [m["id"] for m in data.get("messages", [])]


def _walk_text(payload):
    """Best-effort extraction of plain text from a Gmail message payload."""
    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    if mime == "text/plain" and data:
        return base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
    text = ""
    for part in payload.get("parts", []) or []:
        text += _walk_text(part)
    # fall back to any html if no plain text was found
    if not text and mime == "text/html" and data:
        raw = base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
        text = re.sub(r"<[^>]+>", " ", raw)
    return text


def get_message(access_token, msg_id):
    """Return {id, from, subject, date, snippet, text} for a message."""
    data = _get(f"{API_BASE}/messages/{msg_id}?format=full", access_token)
    headers = {h["name"].lower(): h["value"] for h in data.get("payload", {}).get("headers", [])}
    return {
        "id": data.get("id"),
        "thread_id": data.get("threadId"),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": data.get("snippet", ""),
        "text": _walk_text(data.get("payload", {})),
    }

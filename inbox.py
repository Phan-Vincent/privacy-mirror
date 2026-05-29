"""Reply ingestion: read broker replies from Gmail and advance request status.

Soundness model (see reply_classify_mode):
  - "ack"  (default): any reply -> Acknowledged; replies that ask you to verify/
            confirm -> Needs action; replies that look like a completion or
            rejection are only *suggested* (one-click confirm), never finalized.
  - "full": also auto-set Completed / Rejected on high-confidence phrases.
  - "off":  attach replies to the timeline but never change status.

We only ever read messages whose sender domain matches a broker we contacted,
and only after the request was sent. Each Gmail message is ingested once.
"""

import re
from datetime import datetime, timezone

import db
import gmail
import mailer

# Phrase banks for lightweight classification. Order of checks matters:
# a request to verify is actionable even if the mail also mentions completion.
VERIFY_PHRASES = [
    "verify your", "verification", "confirm your request", "confirm your identity",
    "confirm the request", "confirmation link", "click the link", "click below",
    "to complete your request", "complete your opt-out", "complete your opt out",
    "reply to confirm", "please confirm", "validate your", "to proceed",
]
COMPLETED_PHRASES = [
    "has been deleted", "have deleted", "have removed", "has been removed",
    "been suppressed", "successfully removed", "successfully opted", "opt-out is complete",
    "opt out is complete", "no longer appear", "request has been completed",
    "completed your request", "record has been removed", "information has been deleted",
    "removed your information", "has been processed", "we have processed",
    "no records were found", "no record was found", "do not have any information",
]
REJECTED_PHRASES = [
    "unable to verify", "could not verify", "cannot verify", "we are unable",
    "unable to process", "cannot process", "request is denied", "is denied",
    "we are not able", "not able to process",
]


def _contains(text, phrases):
    return any(p in text for p in phrases)


def classify(subject, body):
    """Return one of: needs_action | completed | rejected | acknowledged."""
    t = f"{subject}\n{body}".lower()
    if _contains(t, VERIFY_PHRASES):
        return "needs_action"
    if _contains(t, REJECTED_PHRASES):
        return "rejected"
    if _contains(t, COMPLETED_PHRASES):
        return "completed"
    return "acknowledged"


def _broker_domains(broker):
    doms = set()
    pe = (broker.get("privacy_email") or "")
    if "@" in pe:
        doms.add(pe.split("@", 1)[1].strip().lower())
    web = (broker.get("website") or "")
    host = web.split("//")[-1].split("/")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if host:
        doms.add(host)
    return {d for d in doms if "." in d}


def _after_clause(sent_at):
    try:
        dt = datetime.strptime(sent_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return ""
    return "after:" + dt.strftime("%Y/%m/%d")


def _seen(msg_id):
    return db.query_one("SELECT 1 FROM seen_messages WHERE message_id = ?", (msg_id,)) is not None


def _mark_seen(msg_id, req_id):
    db.execute(
        "INSERT OR IGNORE INTO seen_messages (message_id, request_id, ts) VALUES (?,?,?)",
        (msg_id, req_id, db.now_iso()),
    )


def _apply(req, suggested, msg, mode):
    rid = req["id"]
    cur = req["status"]
    db.log_event(rid, "reply",
                 f"Reply from {msg['from']}: {msg['subject']} — {msg['snippet'][:160]}")
    db.execute("UPDATE requests SET last_update=? WHERE id=?", (db.now_iso(), rid))

    if mode == "off":
        return "logged"

    if suggested == "needs_action":
        mailer.set_status(rid, "needs_action",
                          "Broker reply needs action (verify/confirm) — see timeline.")
        return "needs_action"

    if mode == "full" and suggested in ("completed", "rejected"):
        mailer.set_status(rid, suggested, f"Auto-classified from reply: {msg['subject'][:60]}")
        return suggested

    # ack mode (or a completed/rejected guess in ack mode): acknowledge + suggest
    if suggested in ("completed", "rejected"):
        if cur in ("sent", "overdue"):
            db.execute("UPDATE requests SET status='acknowledged', last_update=? WHERE id=?",
                       (db.now_iso(), rid))
        db.execute("UPDATE requests SET response_notes=? WHERE id=?",
                   (f"Suggested: {suggested.upper()} — confirm in Requests.", rid))
        db.log_event(rid, "suggestion",
                     f"Reply looks like {suggested.upper()} — confirm. ({msg['subject'][:60]})")
        return f"suggest:{suggested}"

    # plain acknowledgement
    if cur in ("sent", "overdue"):
        db.execute("UPDATE requests SET status='acknowledged', last_update=? WHERE id=?",
                   (db.now_iso(), rid))
    return "acknowledged"


def ingest_replies(max_requests=60, per_request_msgs=5):
    """Scan Gmail for broker replies to in-flight requests. Returns a summary dict."""
    if not mailer.gmail_can_read():
        return {"ok": False, "reason": "Gmail read access not granted — reconnect Gmail."}
    mode = db.get_setting("reply_classify_mode", "ack")
    s = db.all_settings()
    try:
        access = gmail.get_access_token(s["gmail_client_id"], s["gmail_client_secret"],
                                        s["gmail_refresh_token"])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"token error: {e}"}

    reqs = db.query(
        """SELECT r.*, b.privacy_email, b.website, b.name AS broker_name
           FROM requests r JOIN brokers b ON b.id = r.broker_id
           WHERE r.sent_at IS NOT NULL AND r.status IN ('sent','overdue','acknowledged')
           ORDER BY r.id LIMIT ?""",
        (max_requests,),
    )
    found = 0
    actions = {}
    for req in reqs:
        doms = _broker_domains(req)
        if not doms:
            continue
        q = "from:(" + " OR ".join(sorted(doms)) + ")"
        after = _after_clause(req.get("sent_at"))
        if after:
            q += " " + after
        try:
            ids = gmail.search_message_ids(access, q, max_results=per_request_msgs)
        except Exception as e:  # noqa: BLE001
            db.log_event(req["id"], "error", f"Reply search failed: {e}")
            continue
        for mid in ids:
            if _seen(mid):
                continue
            try:
                msg = gmail.get_message(access, mid)
            except Exception as e:  # noqa: BLE001
                db.log_event(req["id"], "error", f"Reply fetch failed: {e}")
                continue
            suggested = classify(msg["subject"], msg["text"])
            outcome = _apply(req, suggested, msg, mode)
            _mark_seen(mid, req["id"])
            found += 1
            actions[outcome] = actions.get(outcome, 0) + 1
    return {"ok": True, "found": found, "actions": actions, "mode": mode}

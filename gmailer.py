from __future__ import annotations
import base64
import email
from email.message import EmailMessage
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8")

def send_one(gmail_svc, to_addr: str, subject: str, body_text: str, lead_id: str) -> str:
    """
    Returns Gmail message id.
    Gmail API expects RFC 2822 MIME message base64url-encoded. :contentReference[oaicite:5]{index=5}
    """
    msg = EmailMessage()
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["X-Lead-ID"] = lead_id   # may or may not survive into DSNs; helpful if it does
    msg.set_content(body_text)

    raw = _b64url(msg.as_bytes())
    resp = gmail_svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    return resp["id"]

def search_bounces(gmail_svc, newer_than_days: int = 2, max_results: int = 500) -> List[str]:
    # Gmail API supports Gmail-style search in q. :contentReference[oaicite:6]{index=6}
    q = (
        f"newer_than:{newer_than_days}d "
        "(from:mailer-daemon OR from:postmaster OR subject:\"Delivery Status Notification\" "
        "OR subject:Undeliverable OR subject:\"Mail delivery failed\" OR subject:failure)"
    )
    resp = gmail_svc.users().messages().list(userId="me", q=q, maxResults=max_results).execute()
    msgs = resp.get("messages", [])
    return [m["id"] for m in msgs]

def _extract_text_parts(payload) -> List[Tuple[str, bytes]]:
    """
    Returns [(mimeType, decoded_bytes), ...]
    """
    out = []
    stack = [payload]
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data:
            out.append((mime, base64.urlsafe_b64decode(data.encode("utf-8"))))
        for p in part.get("parts", []) or []:
            stack.append(p)
    return out

def parse_dsn_recipients(message_full) -> List[Dict[str, str]]:
    """
    DSNs are standardized by RFC 3464; key fields include Final-Recipient, Status, Diagnostic-Code. :contentReference[oaicite:7]{index=7}
    We look for message/delivery-status blocks when present; otherwise we fall back to heuristics.
    Returns list of {email, status, diagnostic}.
    """
    payload = message_full.get("payload", {})
    parts = _extract_text_parts(payload)

    dsn_blocks: List[bytes] = []
    for mime, blob in parts:
        if mime == "message/delivery-status":
            dsn_blocks.append(blob)

    results: List[Dict[str, str]] = []
    for block in dsn_blocks:
        text = block.decode("utf-8", errors="replace")
        # DSN format: groups of header-like lines separated by blank line(s)
        chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
        for c in chunks:
            lines = [ln.strip() for ln in c.splitlines() if ln.strip()]
            final_rcpt = ""
            status = ""
            diag = ""
            for ln in lines:
                if ln.lower().startswith("final-recipient:"):
                    # e.g. "Final-Recipient: rfc822; user@example.com"
                    final_rcpt = ln.split(";", 1)[-1].strip()
                elif ln.lower().startswith("status:"):
                    status = ln.split(":", 1)[-1].strip()
                elif ln.lower().startswith("diagnostic-code:"):
                    diag = ln.split(":", 1)[-1].strip()
            if final_rcpt:
                results.append({"email": final_rcpt, "status": status, "diagnostic": diag})
    return results

def get_message_full(gmail_svc, msg_id: str) -> dict:
    return gmail_svc.users().messages().get(userId="me", id=msg_id, format="full").execute()

import re
import base64
from typing import Dict, List, Tuple

SMTP_LINE_RE = re.compile(r"(?m)^\s*(\d{3}\s+\d\.\d\.\d\s+.+)$")
STATUS_RE = re.compile(r"\b([245]\.\d\.\d)\b")
ENHANCED_SMTP_RE = re.compile(r"\b(\d{3})\s+([245]\.\d\.\d)\b")

def _extract_text_plain_parts(payload) -> List[str]:
    out: List[str] = []
    stack = [payload]
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data and mime.startswith("text/plain"):
            try:
                out.append(base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace"))
            except Exception:
                pass
        for p in part.get("parts", []) or []:
            stack.append(p)
    return out

def _extract_delivery_status_blocks(payload) -> List[str]:
    blocks: List[str] = []
    stack = [payload]
    while stack:
        part = stack.pop()
        if part.get("mimeType") == "message/delivery-status":
            data = (part.get("body", {}) or {}).get("data")
            if data:
                try:
                    blocks.append(base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace"))
                except Exception:
                    pass
        for p in part.get("parts", []) or []:
            stack.append(p)
    return blocks

def _best_reason_from_text(text: str) -> str:
    """
    Extract the most informative human-readable reason.
    Priority:
      1) lines after 'The response was:' (common in Gmail bounces)
      2) last SMTP status line in the text
      3) first ~300 chars of text
    """
    low = text.lower()
    marker = "the response was:"
    if marker in low:
        idx = low.find(marker) + len(marker)
        tail = text[idx:].strip()
        # take first 1-3 lines of the response block
        lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
        return " ".join(lines[:3])[:500]

    smtp_lines = SMTP_LINE_RE.findall(text)
    if smtp_lines:
        return smtp_lines[-1].strip()[:500]

    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]

def parse_bounces_from_gmail_message(message_full: dict) -> List[Dict[str, str]]:
    """
    Returns list of:
      {email, status, diagnostic, reason}
    """
    payload = message_full.get("payload", {}) or {}
    snippet = (message_full.get("snippet") or "").strip()

    dsn_blocks = _extract_delivery_status_blocks(payload)
    plain_texts = _extract_text_plain_parts(payload)
    combined_text = "\n\n".join(plain_texts).strip()

    results: List[Dict[str, str]] = []

    # 1) DSN parse (if present)
    for block in dsn_blocks:
        chunks = [c.strip() for c in block.split("\n\n") if c.strip()]
        for c in chunks:
            lines = [ln.strip() for ln in c.splitlines() if ln.strip()]
            final_rcpt = ""
            status = ""
            diag = ""
            for ln in lines:
                l = ln.lower()
                if l.startswith("final-recipient:"):
                    final_rcpt = ln.split(";", 1)[-1].strip()
                elif l.startswith("status:"):
                    status = ln.split(":", 1)[-1].strip()
                elif l.startswith("diagnostic-code:"):
                    diag = ln.split(":", 1)[-1].strip()

            if final_rcpt:
                reason = diag.strip() if diag else (_best_reason_from_text(combined_text) if combined_text else snippet)
                results.append({
                    "email": final_rcpt,
                    "status": status,
                    "diagnostic": diag,
                    "reason": reason,
                })

    # 2) Fallback if DSN missing: infer recipient + status from body/snippet
    if not results:
        # Try to find an email in text; Gmail bounces usually mention it.
        emails = set(re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", combined_text or snippet))
        reason = _best_reason_from_text(combined_text) if combined_text else snippet

        # Extract enhanced status if present (e.g. 5.2.2)
        m = STATUS_RE.search(combined_text or snippet)
        status = m.group(1) if m else ""
        for e in emails:
            results.append({"email": e, "status": status, "diagnostic": "", "reason": reason})

    return results

from __future__ import annotations
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from google_auth import build_creds, build_sheets_service, build_gmail_service
from sheets_store import read_leads, batch_update_cells
from gmailer import send_one, search_bounces, get_message_full, parse_dsn_recipients, parse_bounces_from_gmail_message

TZ = ZoneInfo("Asia/Kolkata")

SPREADSHEET_ID = "1V7_ck61GD0ltJ6pKDfQC-cYjtqYJzrwkbtGAJZ1hL80"
SHEET_NAME = "Sheet1"

ADMIN_EMAILS = ["admin1@yourco.com", "admin2@yourco.com"]  # optional

TURNOVER_SECONDS = 90

def render_email(first_name: str, company: str) -> str:
    return f"""Hi {first_name},

Quick question about {company}...

Regards,
Your Name
"""

def nightly_send_job():
    creds = build_creds()
    sheets = build_sheets_service(creds)
    gmail = build_gmail_service(creds)

    _, leads = read_leads(sheets, SPREADSHEET_ID, SHEET_NAME)

    start = datetime.now(TZ)
    # enforce finish by ~03:00; choose hard stop at 03:00 IST
    hard_stop = start.replace(hour=3, minute=0, second=0, microsecond=0)
    if hard_stop <= start:
        hard_stop = hard_stop + timedelta(days=1)

    pending = [l for l in leads if l.status == "PENDING"]
    updates = []

    for l in pending:
        now = datetime.now(TZ)
        if now + timedelta(seconds=TURNOVER_SECONDS) > hard_stop:
            break

        subject = f"{l.company} — quick question"
        body = render_email(l.first_name, l.company)

        try:
            msg_id = send_one(gmail, l.email, subject, body, l.lead_id)
            ts = datetime.now(TZ).isoformat(timespec="seconds")

            # Suppose columns: status=E, sent_at=F, gmail_msg_id=G (adjust to your sheet)
            updates.append((f"{SHEET_NAME}!E{l.row_idx}:G{l.row_idx}", [["SENT", ts, msg_id]]))
        except Exception as e:
            ts = datetime.now(TZ).isoformat(timespec="seconds")
            updates.append((f"{SHEET_NAME}!E{l.row_idx}:I{l.row_idx}", [["FAILED", ts, "", "", f"send_error: {e}"]]))
        finally:
            if updates:
                batch_update_cells(sheets, SPREADSHEET_ID, updates)
                updates.clear()

        time.sleep(TURNOVER_SECONDS)

def morning_verify_job():
    creds = build_creds()
    sheets = build_sheets_service(creds)
    gmail = build_gmail_service(creds)

    _, leads = read_leads(sheets, SPREADSHEET_ID, SHEET_NAME)
    sent = [l for l in leads if l.status == "SENT"]

    bounce_msg_ids = search_bounces(gmail, newer_than_days=2)
    failed_set = {}  # email -> (status_code, diagnostic)

    for mid in bounce_msg_ids:
        full = get_message_full(gmail, mid)
        for rec in parse_bounces_from_gmail_message(full):
            st = (rec.get("status") or "").strip()
            reason = (rec.get("reason") or "").strip()
            # Mark failures primarily on 5.x.x, but inbox-full is 5.2.2 (still 5.*)
            if st.startswith("5") or "inbox full" in reason.lower() or "overquota" in reason.lower():
                failed_set[rec["email"].lower()] = (st, reason)


    updates = []
    now_ts = datetime.now(TZ).isoformat(timespec="seconds")

    for l in sent:
        key = l.email.lower()
        if key in failed_set:
            code, diag = failed_set[key]
            # status=E, bounce_code=H, bounce_reason=I, verified_at=J (adjust)
            updates.append((f"{SHEET_NAME}!E{l.row_idx}:J{l.row_idx}", [["FAILED", l.sent_at, l.gmail_msg_id, code, diag, now_ts]]))
        else:
            # No bounce observed => mark VERIFIED
            updates.append((f"{SHEET_NAME}!E{l.row_idx}:J{l.row_idx}", [["VERIFIED", l.sent_at, l.gmail_msg_id, "", "", now_ts]]))

    if updates:
        batch_update_cells(sheets, SPREADSHEET_ID, updates)


def main():
    sched = BlockingScheduler(timezone=TZ)

    # Nightly between 23:00–00:00: pick 23:00 exactly
    sched.add_job(nightly_send_job, CronTrigger(hour=23, minute=0))

    # Morning verify
    sched.add_job(morning_verify_job, CronTrigger(hour=9, minute=30))

    # Report job at 10:15 would go here (generate sheet tab + email attachment)
    # sched.add_job(report_job, CronTrigger(hour=10, minute=15))

    sched.start()

if __name__ == "__main__":
    main()

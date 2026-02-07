import streamlit as st
from google_auth import build_creds, build_sheets_service
# from sheets_store import leads_to_df, read_leads
from worker import nightly_send_job, morning_verify_job
import pandas as pd
SPREADSHEET_ID = "1V7_ck61GD0ltJ6pKDfQC-cYjtqYJzrwkbtGAJZ1hL80"
SHEET_NAME = "Sheet1"  # or "Leads" if you renamed the tab

st.set_page_config(layout="wide")
st.title("Email Ops Dashboard")

import re

EXPECTED_COLS = [
    "lead_id", "email", "first_name", "company", "status",
    "sent_at", "gmail_msg_id", "bounce_code", "bounce_reason", "verified_at"
]

def _norm(s: str) -> str:
    # normalize: trim, lowercase, collapse whitespace, convert spaces/hyphens to underscores
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" ", "_").replace("-", "_")
    return s

def read_leads(sheets_svc, spreadsheet_id: str, sheet_name: str):
    # Fetch all used cells (prevents range-cutoff bugs)
    resp = sheets_svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=sheet_name
    ).execute()

    values = resp.get("values", [])
    if not values:
        return [], []

    raw_headers = values[0]
    headers = [_norm(h) for h in raw_headers]
    idx = {h: i for i, h in enumerate(headers) if h}

    leads = []
    for row in values[1:]:
        rec = {}
        for col in EXPECTED_COLS:
            j = idx.get(col)
            rec[col] = row[j] if (j is not None and j < len(row)) else None
        leads.append(rec)

    return headers, leads

def _to_row_dict(l):
    # dict input
    if isinstance(l, dict):
        return l
    # dataclass instance
    if is_dataclass(l):
        return asdict(l)
    # pydantic / attr objects
    if hasattr(l, "model_dump"):     # pydantic v2
        return l.model_dump()
    if hasattr(l, "dict"):           # pydantic v1
        return l.dict()
    # generic object with attributes
    if hasattr(l, "__dict__"):
        return vars(l)
    raise TypeError(f"Unsupported lead type: {type(l)}")

def leads_to_df(leads):
    rows = [_to_row_dict(l) for l in leads]
    df = pd.DataFrame(rows)

    # enforce expected schema + stable column order
    for c in EXPECTED_COLS:
        if c not in df.columns:
            df[c] = None
    df = df[EXPECTED_COLS + [c for c in df.columns if c not in EXPECTED_COLS]]
    return df

@st.cache_resource
def sheets_client():
    creds = build_creds()
    return build_sheets_service(creds)

sheets = sheets_client()

# Only read/display data on page load
headers, leads = read_leads(sheets, SPREADSHEET_ID, SHEET_NAME)
missing = [c for c in EXPECTED_COLS if c not in set(headers)]
print("HEADERS_FROM_SHEET:", headers)
print("MISSING_EXPECTED:", missing)
print("SAMPLE_ROW:", leads[0] if leads else None)
df = leads_to_df(leads)

st.dataframe(df, width="stretch")

with st.expander("Manual controls"):
    if st.button("Run nightly send now"):
        nightly_send_job()
        st.success("Send job executed. Refresh the page to see updates.")
    if st.button("Run morning verify now"):
        morning_verify_job()
        st.success("Verify job executed. Refresh the page to see updates.")

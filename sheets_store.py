from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import pandas as pd

@dataclass(frozen=True)
class Lead:
    row_idx: int          # 2-based (since row 1 is header)
    lead_id: str
    email: str
    first_name: str
    company: str
    status: str
    sent_at: str
    gmail_msg_id: str
    bounce_code: str
    bounce_reason: str
    verified_at: str

def read_leads(sheets_svc, spreadsheet_id: str, sheet_name: str = "Sheet1") -> Tuple[List[str], List[Lead]]:
    rng = f"{sheet_name}!A1:Z"
    resp = sheets_svc.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=rng).execute()
    values = resp.get("values", [])
    if not values:
        return [], []

    header = values[0]
    rows = values[1:]

    def get(row, col_name, default=""):
        try:
            j = header.index(col_name)
            return row[j] if j < len(row) else default
        except ValueError:
            return default

    leads: List[Lead] = []
    for i, row in enumerate(rows, start=2):
        leads.append(Lead(
            row_idx=i,
            lead_id=get(row, "lead_id"),
            email=get(row, "email"),
            first_name=get(row, "first_name"),
            company=get(row, "company"),
            status=get(row, "status", "PENDING") or "PENDING",
            sent_at=get(row, "sent_at"),
            gmail_msg_id=get(row, "gmail_msg_id"),
            bounce_code=get(row, "bounce_code"),
            bounce_reason=get(row, "bounce_reason"),
            verified_at=get(row, "verified_at"),
        ))
    return header, leads

def batch_update_cells(sheets_svc, spreadsheet_id: str, updates: List[Tuple[str, List[List[Any]]]]):
    """
    updates: list of (A1_range, [[...values...]]) items
    """
    body = {
        "valueInputOption": "RAW",
        "data": [{"range": rng, "values": vals} for rng, vals in updates],
    }
    sheets_svc.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

def leads_to_df(leads: List[Lead]) -> pd.DataFrame:
    return pd.DataFrame([l.__dict__ for l in leads])

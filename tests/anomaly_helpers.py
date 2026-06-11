"""Builders for synthetic detail/summary frames used by the anomaly tests."""

import pandas as pd

from anomaly.loader import _quarter_sort_key
from anomaly.vendors import add_canonical_vendor

DETAIL_DEFAULTS = {
    "data_source": "AP",
    "category": "OTHER SERVICES",
    "party": "D",
    "state": "MD",
    "vendor_id": None,
    "transaction_date": "2025-01-15",
    "description": "",
    "quarter_label": "2025Q1",
}


def make_detail(rows: list[dict]) -> pd.DataFrame:
    """Build a detail DataFrame the way the loader would finalize it."""
    full = []
    for row in rows:
        r = {**DETAIL_DEFAULTS, **row}
        full.append(r)
    df = pd.DataFrame(full)
    df["amount"] = df["amount"].astype(float)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["quarter_sort_key"] = df["quarter_label"].map(_quarter_sort_key)
    df = add_canonical_vendor(df)
    return df


SUMMARY_DEFAULTS = {
    "party": "D",
    "state": "MD",
    "congress": 119,
    "quarter_label": "2025Q1",
}


def make_summary(rows: list[dict]) -> pd.DataFrame:
    full = []
    for row in rows:
        r = {**SUMMARY_DEFAULTS, **row}
        full.append(r)
    df = pd.DataFrame(full)
    df["qtd_amount"] = df["qtd_amount"].astype(float)
    df["quarter_sort_key"] = df["quarter_label"].map(_quarter_sort_key)
    return df


def vanilla_offices(n: int = 15, quarter: str = "2025Q1") -> list[dict]:
    """Plain offices that share a common vendor — background population that
    should never be flagged."""
    rows = []
    for i in range(n):
        bid = f"V{i:06d}"
        name = f"Vanilla Member{i}"
        rows.append({
            "bioguide_id": bid, "member_name": name,
            "vendor_name": "COMMON PRINTING", "amount": 1200.0 + i,
            "quarter_label": quarter,
        })
        rows.append({
            "bioguide_id": bid, "member_name": name,
            "vendor_name": "GENERIC SUPPLY", "amount": 800.0 + i,
            "quarter_label": quarter,
        })
    return rows

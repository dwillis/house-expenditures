"""Load enriched output CSVs into typed DataFrames for anomaly analysis."""

from pathlib import Path

import pandas as pd

from anomaly.config import AnomalyConfig


def _quarter_sort_key(label: str) -> int:
    """Convert '2024Q3' to sortable integer 20243."""
    try:
        year, q = label.split("Q")
        return int(year) * 10 + int(q)
    except (ValueError, AttributeError):
        return 0


def _since_key(config: AnomalyConfig) -> int:
    if config.since_quarter:
        return _quarter_sort_key(config.since_quarter)
    return 0


DETAIL_DTYPES: dict[str, str] = {
    "bioguide_id": "string",
    "organization": "string",
    "fiscal_year": "string",
    "organization_code": "string",
    "program": "string",
    "program_code": "string",
    "category": "category",
    "budget_object_class": "string",
    "sort_sequence": "string",
    "transaction_date": "string",  # parsed separately after load
    "data_source": "category",
    "document": "string",
    "vendor_name": "string",
    "vendor_id": "string",
    "start_date": "string",
    "end_date": "string",
    "description": "string",
    "budget_object_code": "string",
    "amount": "float64",
    "member_name": "string",
    "party": "category",
    "state": "category",
    "district": "Int16",
    "congress": "Int16",
    "quarter_label": "string",
    "is_member": "string",  # "true"/"false" — cast to bool after load
}

SUMMARY_DTYPES: dict[str, str] = {
    "bioguide_id": "string",
    "organization": "string",
    "program": "string",
    "description": "string",
    "ytd_amount": "float64",
    "qtd_amount": "float64",
    "member_name": "string",
    "party": "category",
    "state": "category",
    "district": "Int16",
    "congress": "Int16",
    "quarter_label": "string",
    "is_member": "string",
}


def _load_csvs(
    files: list[Path],
    dtypes: dict[str, str],
    since_key: int,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for f in sorted(files):
        # Fast pre-filter by filename before reading
        stem = f.stem.split("-")[0]  # e.g. "2024Q3"
        if _quarter_sort_key(stem) < since_key:
            continue
        try:
            df = pd.read_csv(
                f,
                dtype=dtypes,
                low_memory=False,
                na_values=["", "NA", "N/A"],
                keep_default_na=False,
            )
            frames.append(df)
        except Exception as exc:
            print(f"  Warning: could not load {f.name}: {exc}")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _finalize_detail(df: pd.DataFrame, member_only: bool) -> pd.DataFrame:
    if df.empty:
        return df

    # Cast is_member string → bool
    df["is_member"] = df["is_member"].str.lower() == "true"

    # Drop non-member offices if requested
    if member_only:
        df = df[df["is_member"]].copy()

    # Drop AR (accounts receivable = equipment returns posted to CAO)
    if "data_source" in df.columns:
        df = df[df["data_source"] != "AR"].copy()

    # Parse transaction_date — only populated for AP records
    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"], format="%Y-%m-%d", errors="coerce"
    )

    # Derived sort key for ordering quarters
    df["quarter_sort_key"] = df["quarter_label"].map(_quarter_sort_key)

    # Normalise vendor_name: strip, uppercase for consistent matching
    df["vendor_name"] = df["vendor_name"].str.strip().str.upper()

    return df


def _finalize_summary(df: pd.DataFrame, member_only: bool) -> pd.DataFrame:
    if df.empty:
        return df

    df["is_member"] = df["is_member"].str.lower() == "true"

    if member_only:
        df = df[df["is_member"]].copy()

    df["quarter_sort_key"] = df["quarter_label"].map(_quarter_sort_key)

    return df


def load_data(config: AnomalyConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (detail_df, summary_df) loaded from output CSVs per config."""
    output_dir = config.output_dir
    since_key = _since_key(config)

    detail_files = sorted(output_dir.glob("*-detail.csv"))
    summary_files = sorted(output_dir.glob("*-summary.csv"))

    print(
        f"  Loading {len(detail_files)} detail files, "
        f"{len(summary_files)} summary files "
        f"(since key={since_key or 'all'}) ..."
    )

    detail_df = _load_csvs(detail_files, DETAIL_DTYPES, since_key)
    summary_df = _load_csvs(summary_files, SUMMARY_DTYPES, since_key)

    detail_df = _finalize_detail(detail_df, config.member_only)
    summary_df = _finalize_summary(summary_df, config.member_only)

    print(
        f"  Loaded {len(detail_df):,} detail rows, "
        f"{len(summary_df):,} summary rows."
    )
    return detail_df, summary_df

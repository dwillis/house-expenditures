"""Detectors for anomalous vendor patterns."""

import pandas as pd

from anomaly.config import (
    CARD_GATEWAY_PREFIXES,
    KNOWN_INSTITUTIONAL_VENDORS,
    PERSONNEL_CATEGORIES,
    AnomalyConfig,
)
from anomaly.report import Finding, severity_from_share


def _is_institutional(vendor_name: str, config: AnomalyConfig) -> bool:
    """Return True if the vendor should be excluded from rare-vendor analysis."""
    if not vendor_name:
        return True
    v = str(vendor_name).upper().strip()
    # Exact match against known set
    if v in KNOWN_INSTITUTIONAL_VENDORS:
        return True
    # Card-gateway sub-merchants (CITIBANK -...) are real specific vendors — keep them
    for prefix in CARD_GATEWAY_PREFIXES:
        if v.startswith(prefix):
            return False
    # Card-gateway aggregator exclusions also in config
    if v in config.neg_vendor_exclude:
        return True
    return False


def detect_rare_vendors(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """E — Flag significant payments to vendors used by very few offices."""
    findings: list[Finding] = []

    # Positive AP transactions only, non-personnel
    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"] > 0)
        & (~detail_df["category"].isin(PERSONNEL_CATEGORIES))
    ].copy()
    if ap.empty:
        return findings

    # Drop institutional vendors
    ap = ap[~ap["vendor_name"].apply(lambda v: _is_institutional(v, config))]

    # Count distinct offices per vendor
    vendor_stats = (
        ap.groupby("vendor_name")
        .agg(
            distinct_offices=("bioguide_id", "nunique"),
            total_spend=("amount", "sum"),
            transaction_count=("amount", "count"),
        )
        .reset_index()
    )

    rare = vendor_stats[
        (vendor_stats["distinct_offices"] <= config.vendor_rare_office_count)
        & (vendor_stats["total_spend"] > config.vendor_rare_min_amount)
    ].sort_values("total_spend", ascending=False)

    for _, vrow in rare.iterrows():
        vendor = vrow["vendor_name"]
        # Find which offices paid this vendor (one row per office, not per quarter)
        offices = (
            ap[ap["vendor_name"] == vendor][["bioguide_id", "member_name", "party", "state"]]
            .drop_duplicates(subset=["bioguide_id"])
        )

        for _, orow in offices.iterrows():
            office_txns = ap.loc[
                (ap["vendor_name"] == vendor) & (ap["bioguide_id"] == orow["bioguide_id"])
            ]
            office_spend = float(office_txns["amount"].sum())
            quarters = ", ".join(sorted(office_txns["quarter_label"].unique()))
            findings.append(Finding(
                detector_id="E",
                detector_name="Rare vendor",
                severity="HIGH" if int(vrow["distinct_offices"]) == 1 else "MEDIUM",
                bioguide_id=orow["bioguide_id"],
                member_name=orow["member_name"],
                party=orow["party"],
                state=orow["state"],
                description=(
                    f"Paid {vendor} ${office_spend:,.0f} — "
                    f"vendor used by only {int(vrow['distinct_offices'])} office(s) total"
                ),
                amount=office_spend,
                vendor_name=vendor,
                extra={
                    "vendor_total_across_all_offices": round(float(vrow["total_spend"]), 2),
                    "vendor_distinct_offices": int(vrow["distinct_offices"]),
                    "vendor_transaction_count": int(vrow["transaction_count"]),
                    "quarters": quarters,
                },
            ))
            if len(findings) >= config.max_findings_per_detector:
                return findings

    return findings


def detect_vendor_concentration(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """F — Flag offices where a single vendor dominates non-personnel spend."""
    findings: list[Finding] = []

    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"] > 0)
        & (~detail_df["category"].isin(PERSONNEL_CATEGORIES))
    ].copy()
    if ap.empty:
        return findings

    # Total non-personnel positive spend per (office, quarter)
    totals = (
        ap.groupby(["bioguide_id", "quarter_label"])["amount"]
        .sum()
        .rename("total_spend")
    )

    # Per-vendor spend per (office, quarter)
    vendor_q = (
        ap.groupby(["bioguide_id", "quarter_label", "vendor_name", "member_name", "party", "state"])
        ["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "vendor_spend"})
    )
    vendor_q = vendor_q.join(totals, on=["bioguide_id", "quarter_label"])
    vendor_q["vendor_share"] = vendor_q["vendor_spend"] / vendor_q["total_spend"].clip(lower=1)

    # Top vendor share per office×quarter
    top_vendor = (
        vendor_q.sort_values("vendor_share", ascending=False)
        .groupby(["bioguide_id", "quarter_label"])
        .first()
        .reset_index()
    )

    concentrated = top_vendor[
        (top_vendor["vendor_share"] > config.vendor_concentration_threshold)
        & (top_vendor["total_spend"] > config.vendor_concentration_min_total)
    ].sort_values("vendor_share", ascending=False)

    for _, row in concentrated.iterrows():
        share = float(row["vendor_share"])
        findings.append(Finding(
            detector_id="F",
            detector_name="Vendor concentration",
            severity=severity_from_share(share),
            bioguide_id=row["bioguide_id"],
            member_name=row["member_name"],
            party=row["party"],
            state=row["state"],
            quarter=str(row["quarter_label"]),
            description=(
                f"{row['vendor_name']} received {share:.1%} of non-personnel spend "
                f"(${row['vendor_spend']:,.0f} of ${row['total_spend']:,.0f})"
            ),
            amount=float(row["vendor_spend"]),
            vendor_name=row["vendor_name"],
            extra={
                "vendor_share": f"{share:.2%}",
                "office_non_personnel_total": round(float(row["total_spend"]), 2),
            },
        ))
        if len(findings) >= config.max_findings_per_detector:
            break

    return findings


def detect_new_expensive_vendors(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """G — Flag vendors that debuted recently and receive significant spend across many offices."""
    findings: list[Finding] = []

    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"] > 0)
        & (~detail_df["category"].isin(PERSONNEL_CATEGORIES))
    ].copy()
    if ap.empty:
        return findings

    # Determine debut year per vendor (earliest quarter_label)
    debut = (
        ap.groupby("vendor_name")["quarter_sort_key"]
        .min()
        .rename("first_quarter_key")
    )
    debut_year = (debut // 10).rename("debut_year")  # quarter_sort_key = year*10 + q

    ap = ap.join(debut_year, on="vendor_name")

    new_vendors = ap[ap["debut_year"] >= config.new_vendor_debut_year]
    if new_vendors.empty:
        return findings

    stats = (
        new_vendors.groupby("vendor_name")
        .agg(
            distinct_offices=("bioguide_id", "nunique"),
            total_spend=("amount", "sum"),
            debut_year=("debut_year", "min"),
        )
        .reset_index()
    )

    flagged = stats[
        (stats["distinct_offices"] >= config.new_vendor_min_offices)
        & (stats["total_spend"] >= config.new_vendor_min_amount)
    ].sort_values("total_spend", ascending=False)

    for _, row in flagged.iterrows():
        vendor = row["vendor_name"]
        # Sample of paying offices
        offices = (
            new_vendors[new_vendors["vendor_name"] == vendor]["member_name"]
            .dropna()
            .unique()[:5]
        )
        findings.append(Finding(
            detector_id="G",
            detector_name="New expensive vendor",
            severity="HIGH" if float(row["total_spend"]) > 500000 else "MEDIUM",
            vendor_name=vendor,
            description=(
                f"{vendor} debuted {int(row['debut_year'])}, "
                f"paid ${float(row['total_spend']):,.0f} by "
                f"{int(row['distinct_offices'])} offices"
            ),
            amount=float(row["total_spend"]),
            extra={
                "debut_year": int(row["debut_year"]),
                "distinct_offices": int(row["distinct_offices"]),
                "sample_offices": ", ".join(offices),
            },
        ))
        if len(findings) >= config.max_findings_per_detector:
            break

    return findings

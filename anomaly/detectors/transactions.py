"""Detectors for anomalous individual transaction patterns."""

import numpy as np
import pandas as pd

from anomaly.config import PERSONNEL_CATEGORIES, AnomalyConfig
from anomaly.report import Finding, severity_from_z

ROUND_NUMBER_CATEGORIES = frozenset({
    "OTHER SERVICES",
    "EQUIPMENT",
    "SUPPLIES AND MATERIALS",
})


def _mad_zscore(series: pd.Series) -> pd.Series:
    median = series.median()
    mad = (series - median).abs().median()
    if mad == 0:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return 0.6745 * (series - median) / mad


def detect_large_transactions(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """H — Flag unusually large single transactions per spending category."""
    findings: list[Finding] = []

    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"] > 0)
        & (~detail_df["category"].isin(PERSONNEL_CATEGORIES))
    ].copy()
    if ap.empty:
        return findings

    ap = ap[ap["amount"] >= config.large_tx_min_amount]

    for category, grp in ap.groupby("category"):
        if len(grp) < 20:
            continue
        z_scores = _mad_zscore(grp["amount"])
        flagged_idx = z_scores[z_scores > config.large_tx_zscore].index

        for idx in flagged_idx:
            row = ap.loc[idx]
            z = float(z_scores.loc[idx])
            findings.append(Finding(
                detector_id="H",
                detector_name="Large single transaction",
                severity=severity_from_z(z),
                bioguide_id=row["bioguide_id"],
                member_name=row["member_name"],
                party=row["party"],
                state=row["state"],
                quarter=str(row["quarter_label"]),
                description=(
                    f"${float(row['amount']):,.2f} in {category} "
                    f"(z={z:.1f}, category median ${grp['amount'].median():,.2f})"
                ),
                amount=float(row["amount"]),
                vendor_name=str(row["vendor_name"]) if pd.notna(row.get("vendor_name")) else None,
                extra={
                    "category": category,
                    "z_score": round(z, 2),
                    "category_median": round(float(grp["amount"].median()), 2),
                    "transaction_date": str(row.get("transaction_date", ""))[:10],
                    "description_field": str(row.get("description", "")),
                },
            ))

    findings.sort(key=lambda f: f.extra.get("z_score", 0), reverse=True)
    return findings[: config.max_findings_per_detector]


def detect_round_numbers(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """I — Flag clusters of suspiciously round-dollar transactions to the same vendor."""
    findings: list[Finding] = []

    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"] >= config.round_number_min)
        & (detail_df["category"].isin(ROUND_NUMBER_CATEGORIES))
    ].copy()
    if ap.empty:
        return findings

    # Flag round amounts (divisible by modulus)
    modulus = config.round_number_modulus
    ap["is_round"] = (ap["amount"].round(2) % modulus).abs() < 0.01

    round_txns = ap[ap["is_round"]].copy()
    if round_txns.empty:
        return findings

    # Group by office×vendor — find clusters of ≥N round payments
    clusters = (
        round_txns.groupby(["bioguide_id", "vendor_name", "member_name", "party", "state"])
        .agg(
            round_count=("amount", "count"),
            total_amount=("amount", "sum"),
            quarters=("quarter_label", lambda x: ", ".join(sorted(x.unique()))),
            amounts=("amount", lambda x: ", ".join(f"${v:,.0f}" for v in sorted(x)[:5])),
        )
        .reset_index()
    )

    clusters = clusters[
        clusters["round_count"] >= config.round_number_min_cluster
    ].sort_values("total_amount", ascending=False)

    for _, row in clusters.iterrows():
        n = int(row["round_count"])
        findings.append(Finding(
            detector_id="I",
            detector_name="Round number clustering",
            severity="MEDIUM" if n >= 4 else "LOW",
            bioguide_id=row["bioguide_id"],
            member_name=row["member_name"],
            party=row["party"],
            state=row["state"],
            description=(
                f"{n} round-dollar payments to {row['vendor_name']}, "
                f"total ${float(row['total_amount']):,.0f}"
            ),
            amount=float(row["total_amount"]),
            vendor_name=row["vendor_name"],
            extra={
                "round_payment_count": n,
                "quarters": row["quarters"],
                "amounts_sample": row["amounts"],
            },
        ))
        if len(findings) >= config.max_findings_per_detector:
            break

    return findings


def detect_wash_pairs(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """J — Flag near-equal positive/negative transaction pairs to the same vendor."""
    findings: list[Finding] = []

    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"].abs() >= config.wash_min_amount)
        & (detail_df["transaction_date"].notna())
    ].copy()
    if ap.empty:
        return findings

    # Exclude card-gateway aggregators
    ap = ap[~ap["vendor_name"].isin(config.neg_vendor_exclude)]

    for (bioguide, vendor), grp in ap.groupby(["bioguide_id", "vendor_name"]):
        pos = grp[grp["amount"] > 0].copy()
        neg = grp[grp["amount"] < 0].copy()
        if pos.empty or neg.empty:
            continue

        for _, pr in pos.iterrows():
            for _, nr in neg.iterrows():
                p, n = float(pr["amount"]), float(nr["amount"])
                pair_size = max(abs(p), abs(n))
                offset = abs(p + n)
                if pair_size == 0:
                    continue
                if (offset / pair_size) > config.wash_tolerance_pct:
                    continue
                # Check date proximity
                try:
                    days_apart = abs((pr["transaction_date"] - nr["transaction_date"]).days)
                except (TypeError, AttributeError):
                    continue
                if days_apart > config.wash_max_days_apart:
                    continue

                findings.append(Finding(
                    detector_id="J",
                    detector_name="Wash transaction pair",
                    severity="HIGH" if pair_size > 50000 else "MEDIUM",
                    bioguide_id=str(grp["bioguide_id"].iloc[0]),
                    member_name=str(grp["member_name"].iloc[0]),
                    party=str(grp["party"].iloc[0]),
                    state=str(grp["state"].iloc[0]),
                    description=(
                        f"Near-exact offset pair with {vendor}: "
                        f"+${p:,.2f} and -${abs(n):,.2f}, "
                        f"{days_apart} days apart"
                    ),
                    amount=p,
                    vendor_name=str(vendor),
                    extra={
                        "positive_amount": round(p, 2),
                        "negative_amount": round(n, 2),
                        "days_apart": days_apart,
                        "positive_date": str(pr["transaction_date"])[:10],
                        "negative_date": str(nr["transaction_date"])[:10],
                        "offset_pct": round(offset / pair_size * 100, 3),
                    },
                ))

                if len(findings) >= config.max_findings_per_detector:
                    return findings

    return findings


def detect_velocity_outliers(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """K — Flag offices with unusually high transaction counts in a quarter."""
    findings: list[Finding] = []

    ap = detail_df[detail_df["data_source"] == "AP"].copy()
    if ap.empty:
        return findings

    counts = (
        ap.groupby(["bioguide_id", "quarter_label", "member_name", "party", "state"])
        .size()
        .rename("tx_count")
        .reset_index()
    )

    for quarter, grp in counts.groupby("quarter_label"):
        if len(grp) < 10:
            continue
        series = grp["tx_count"].astype(float)
        z_scores = _mad_zscore(series)
        flagged = grp[z_scores > config.velocity_zscore]

        for _, row in flagged.iterrows():
            idx = row.name
            z = float(z_scores.loc[idx])
            findings.append(Finding(
                detector_id="K",
                detector_name="Transaction velocity outlier",
                severity=severity_from_z(z),
                bioguide_id=row["bioguide_id"],
                member_name=row["member_name"],
                party=row["party"],
                state=row["state"],
                quarter=str(quarter),
                description=(
                    f"{int(row['tx_count'])} AP transactions in {quarter} "
                    f"(z={z:.1f}, peer median {series.median():.0f})"
                ),
                extra={
                    "transaction_count": int(row["tx_count"]),
                    "peer_median": int(series.median()),
                    "z_score": round(z, 2),
                },
            ))

    findings.sort(key=lambda f: f.extra.get("z_score", 0), reverse=True)
    return findings[: config.max_findings_per_detector]

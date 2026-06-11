"""Detectors for anomalous individual transaction patterns."""

import numpy as np
import pandas as pd

from anomaly.config import PERSONNEL_CATEGORIES, AnomalyConfig
from anomaly.report import Finding, severity_from_z
from anomaly.vendors import clean_vendor_name

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


def _vendor_col(df: pd.DataFrame) -> str:
    return "canonical_vendor" if "canonical_vendor" in df.columns else "vendor_name"


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

    for category, grp in ap.groupby("category", observed=True):
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
                vendor_name=str(row[_vendor_col(ap)]) if pd.notna(row.get(_vendor_col(ap))) else None,
                extra={
                    "category": category,
                    "z_score": round(z, 2),
                    "category_median": round(float(grp["amount"].median()), 2),
                    "transaction_date": str(row.get("transaction_date", ""))[:10],
                    "description_field": str(row.get("description", "")),
                },
            ))

    findings.sort(key=lambda f: f.extra.get("z_score", 0), reverse=True)
    return findings


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

    vcol = _vendor_col(round_txns)

    # Group by office×vendor — find clusters of ≥N round payments
    clusters = (
        round_txns.groupby(["bioguide_id", vcol, "member_name", "party", "state"], observed=True)
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
            severity="MEDIUM" if n >= 6 else "LOW",
            bioguide_id=row["bioguide_id"],
            member_name=row["member_name"],
            party=row["party"],
            state=row["state"],
            description=(
                f"{n} round-dollar payments to {row[vcol]}, "
                f"total ${float(row['total_amount']):,.0f}"
            ),
            amount=float(row["total_amount"]),
            vendor_name=row[vcol],
            extra={
                "round_payment_count": n,
                "quarters": row["quarters"],
                "amounts_sample": row["amounts"],
            },
        ))

    return findings


def detect_wash_pairs(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """J — Flag near-equal positive/negative transaction pairs to the same vendor.

    Pairs are matched 1:1 greedily — each positive transaction can offset at
    most one negative and vice versa — so a recurring payment with a single
    refund yields one pair, not one per occurrence. Vendors where the same
    positive amount recurs (rent, retainers) are skipped entirely: a refund
    against a recurring charge is routine bookkeeping, not a wash.
    """
    findings: list[Finding] = []

    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"].abs() >= config.wash_min_amount)
        & (detail_df["transaction_date"].notna())
    ].copy()
    if ap.empty:
        return findings

    # Exclude card-gateway aggregators (match on cleaned form)
    excluded = {clean_vendor_name(v)[0] for v in config.neg_vendor_exclude}
    vcol = _vendor_col(ap)
    ap = ap[~ap[vcol].isin(excluded)]

    for (bioguide, vendor), grp in ap.groupby(["bioguide_id", vcol], observed=True):
        pos = grp[grp["amount"] > 0]
        neg = grp[grp["amount"] < 0]
        if pos.empty or neg.empty:
            continue

        # Amounts that recur among positives indicate scheduled payments;
        # offsets against them are routine corrections.
        pos_amount_counts = pos["amount"].round(2).value_counts()
        recurring = set(pos_amount_counts[pos_amount_counts >= config.wash_recurring_count].index)

        pos_records = [
            (float(r["amount"]), r["transaction_date"])
            for _, r in pos.iterrows()
            if round(float(r["amount"]), 2) not in recurring
        ]
        used = [False] * len(pos_records)

        for _, nr in neg.sort_values("transaction_date").iterrows():
            n = float(nr["amount"])
            best_i, best_offset, best_days = None, None, None
            for i, (p, p_date) in enumerate(pos_records):
                if used[i]:
                    continue
                pair_size = max(abs(p), abs(n))
                if pair_size == 0:
                    continue
                offset = abs(p + n)
                if (offset / pair_size) > config.wash_tolerance_pct:
                    continue
                try:
                    days_apart = abs((p_date - nr["transaction_date"]).days)
                except (TypeError, AttributeError):
                    continue
                if days_apart > config.wash_max_days_apart:
                    continue
                if best_i is None or (offset, days_apart) < (best_offset, best_days):
                    best_i, best_offset, best_days = i, offset, days_apart

            if best_i is None:
                continue
            used[best_i] = True
            p, p_date = pos_records[best_i]
            pair_size = max(abs(p), abs(n))

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
                    f"{best_days} days apart"
                ),
                amount=p,
                vendor_name=str(vendor),
                extra={
                    "positive_amount": round(p, 2),
                    "negative_amount": round(n, 2),
                    "days_apart": best_days,
                    "positive_date": str(p_date)[:10],
                    "negative_date": str(nr["transaction_date"])[:10],
                    "offset_pct": round(best_offset / pair_size * 100, 3),
                },
            ))

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
        ap.groupby(["bioguide_id", "quarter_label", "member_name", "party", "state"], observed=True)
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
    return findings

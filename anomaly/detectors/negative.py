"""Detectors for anomalous negative-amount patterns."""

import numpy as np
import pandas as pd

from anomaly.config import AnomalyConfig
from anomaly.report import Finding, severity_from_quarters, severity_from_z


def _mad_zscore(series: pd.Series) -> pd.Series:
    """Modified z-score using median absolute deviation (robust to outliers)."""
    median = series.median()
    mad = (series - median).abs().median()
    if mad == 0:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return 0.6745 * (series - median) / mad


def detect_office_negative_rate(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """A — Flag offices whose AP negative-transaction rate is a statistical outlier."""
    findings: list[Finding] = []

    ap = detail_df[detail_df["data_source"] == "AP"].copy()
    if ap.empty:
        return findings

    # Count total AP transactions and negative ones per (office, quarter)
    total = (
        ap.groupby(["bioguide_id", "quarter_label", "member_name", "party", "state"])
        .size()
        .rename("total_count")
    )
    neg = (
        ap[ap["amount"] < 0]
        .groupby(["bioguide_id", "quarter_label", "member_name", "party", "state"])
        .size()
        .rename("neg_count")
    )
    counts = pd.concat([total, neg], axis=1).fillna(0)
    counts["neg_rate"] = counts["neg_count"] / counts["total_count"].clip(lower=1)

    for quarter, grp in counts.groupby(level="quarter_label"):
        if len(grp) < 10:
            continue
        rates = grp["neg_rate"]
        z_scores = _mad_zscore(rates)

        flagged = z_scores[z_scores > config.neg_office_zscore]
        for idx in flagged.index:
            row = grp.loc[idx]
            z = float(z_scores.loc[idx])
            bioguide = idx[0]
            member = idx[2]
            party = idx[3]
            state = idx[4]

            # Compute total negative dollar value for context
            mask = (
                (ap["bioguide_id"] == bioguide)
                & (ap["quarter_label"] == quarter)
                & (ap["amount"] < 0)
            )
            neg_total = float(ap.loc[mask, "amount"].sum())

            findings.append(Finding(
                detector_id="A",
                detector_name="Office negative AP rate",
                severity=severity_from_z(z),
                bioguide_id=bioguide,
                member_name=member,
                party=party,
                state=state,
                quarter=str(quarter),
                description=(
                    f"Negative AP rate {row['neg_rate']:.1%} "
                    f"(z={z:.1f}, peer median {rates.median():.1%})"
                ),
                amount=neg_total,
                extra={
                    "neg_count": int(row["neg_count"]),
                    "total_ap_count": int(row["total_count"]),
                    "peer_median_neg_rate": f"{rates.median():.3%}",
                },
            ))

    findings.sort(key=lambda f: abs(f.amount or 0), reverse=True)
    return findings[: config.max_findings_per_detector]


def detect_cross_quarter_patterns(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """B — Flag office×vendor pairs with negative transactions across many quarters."""
    findings: list[Finding] = []

    ap_neg = detail_df[
        (detail_df["data_source"] == "AP") & (detail_df["amount"] < 0)
    ].copy()
    if ap_neg.empty:
        return findings

    # Exclude known card-gateway aggregators
    mask = ~ap_neg["vendor_name"].isin(config.neg_vendor_exclude)
    ap_neg = ap_neg[mask]

    # Count distinct quarters with negatives per (office, vendor)
    pattern = (
        ap_neg.groupby(["bioguide_id", "vendor_name", "member_name", "party", "state"])
        .agg(
            quarters_with_negatives=("quarter_label", "nunique"),
            quarter_list=("quarter_label", lambda x: ", ".join(sorted(x.unique()))),
            total_negative_amount=("amount", "sum"),
            transaction_count=("amount", "count"),
        )
        .reset_index()
    )

    pattern = pattern[
        pattern["quarters_with_negatives"] >= config.neg_cross_quarter_min
    ].sort_values("quarters_with_negatives", ascending=False)

    for _, row in pattern.iterrows():
        n_quarters = int(row["quarters_with_negatives"])
        findings.append(Finding(
            detector_id="B",
            detector_name="Cross-quarter negative vendor pattern",
            severity=severity_from_quarters(n_quarters),
            bioguide_id=row["bioguide_id"],
            member_name=row["member_name"],
            party=row["party"],
            state=row["state"],
            description=(
                f"Negative transactions to {row['vendor_name']} "
                f"in {n_quarters} separate quarters"
            ),
            amount=float(row["total_negative_amount"]),
            vendor_name=row["vendor_name"],
            extra={
                "quarters_with_negatives": n_quarters,
                "transaction_count": int(row["transaction_count"]),
                "quarters": row["quarter_list"],
            },
        ))
        if len(findings) >= config.max_findings_per_detector:
            break

    return findings

"""Detectors for anomalous category-level spending distributions."""

import numpy as np
import pandas as pd

from anomaly.config import ELECTION_YEARS, PERSONNEL_CATEGORIES, RARE_CATEGORIES, AnomalyConfig
from anomaly.report import Finding, severity_from_z


def _mad_zscore(series: pd.Series) -> pd.Series:
    median = series.median()
    mad = (series - median).abs().median()
    if mad == 0:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return 0.6745 * (series - median) / mad


def detect_category_outliers(
    summary_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """C — Flag offices whose category share of non-personnel spend is a peer outlier."""
    findings: list[Finding] = []

    if summary_df.empty:
        return findings

    # summary 'description' field maps to category names
    non_pers = summary_df[~summary_df["description"].isin(PERSONNEL_CATEGORIES)].copy()
    if non_pers.empty:
        return findings

    # Total non-personnel QTD spend per office×quarter
    totals = (
        non_pers.groupby(["bioguide_id", "quarter_label"])["qtd_amount"]
        .sum()
        .rename("office_total")
    )

    # Per category share per office×quarter
    cat_totals = (
        non_pers.groupby(["bioguide_id", "quarter_label", "description", "member_name", "party", "state"])
        ["qtd_amount"]
        .sum()
        .reset_index()
    )
    cat_totals = cat_totals.join(
        totals, on=["bioguide_id", "quarter_label"]
    )
    cat_totals["category_share"] = (
        cat_totals["qtd_amount"] / cat_totals["office_total"].clip(lower=1)
    )

    # Z-score per category per quarter
    for (category, quarter), grp in cat_totals.groupby(["description", "quarter_label"]):
        if len(grp) < 10:
            continue
        shares = grp["category_share"]
        z_scores = _mad_zscore(shares)

        flagged = z_scores[
            (z_scores > config.category_zscore)
            & (grp["qtd_amount"].abs() > config.category_min_amount)
        ]
        for idx in flagged.index:
            row = grp.loc[idx]
            z = float(z_scores.loc[idx])
            findings.append(Finding(
                detector_id="C",
                detector_name="Category spend outlier",
                severity=severity_from_z(z),
                bioguide_id=row["bioguide_id"],
                member_name=row["member_name"],
                party=row["party"],
                state=row["state"],
                quarter=str(quarter),
                description=(
                    f"{category} is {row['category_share']:.1%} of non-personnel spend "
                    f"(z={z:.1f}, peer median {shares.median():.1%})"
                ),
                amount=float(row["qtd_amount"]),
                extra={
                    "category": category,
                    "category_share": f"{row['category_share']:.2%}",
                    "peer_median_share": f"{shares.median():.2%}",
                    "z_score": round(z, 2),
                },
            ))

    findings.sort(key=lambda f: f.extra.get("z_score", 0), reverse=True)
    return findings[: config.max_findings_per_detector]


def detect_rare_category_dominance(
    summary_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """D — Flag offices where a rare/unusual category dominates non-personnel spend."""
    findings: list[Finding] = []

    if summary_df.empty:
        return findings

    non_pers = summary_df[~summary_df["description"].isin(PERSONNEL_CATEGORIES)].copy()

    totals = (
        non_pers.groupby(["bioguide_id", "quarter_label"])["qtd_amount"]
        .sum()
        .rename("office_total")
    )

    rare = non_pers[non_pers["description"].isin(RARE_CATEGORIES)].copy()
    rare = rare.join(totals, on=["bioguide_id", "quarter_label"])
    rare["share"] = rare["qtd_amount"] / rare["office_total"].clip(lower=1)

    # Dominance flag
    dominated = rare[
        (rare["share"] > config.category_rare_dominance)
        & (rare["qtd_amount"].abs() > config.category_min_amount)
    ]

    for _, row in dominated.iterrows():
        category = row["description"]
        quarter = row["quarter_label"]

        # Extra check: FRANKED MAIL in Q3/Q4 of election year
        is_franked_mail = category == "FRANKED MAIL"
        try:
            yr = int(str(quarter)[:4])
            q_num = int(str(quarter)[-1])
            election_concern = is_franked_mail and yr in ELECTION_YEARS and q_num in (3, 4)
        except (ValueError, IndexError):
            election_concern = False

        severity = "HIGH" if (election_concern or float(row["share"]) > 0.80) else "MEDIUM"

        note = " [ELECTION YEAR — franked mail prohibited near election day]" if election_concern else ""
        findings.append(Finding(
            detector_id="D",
            detector_name="Rare category dominance",
            severity=severity,
            bioguide_id=row["bioguide_id"],
            member_name=row["member_name"],
            party=row["party"],
            state=row["state"],
            quarter=str(quarter),
            description=(
                f"{category} is {row['share']:.1%} of non-personnel QTD spend{note}"
            ),
            amount=float(row["qtd_amount"]),
            extra={
                "category": category,
                "category_share": f"{row['share']:.2%}",
                "office_non_personnel_total": round(float(row["office_total"]), 2),
            },
        ))
        if len(findings) >= config.max_findings_per_detector:
            break

    return findings

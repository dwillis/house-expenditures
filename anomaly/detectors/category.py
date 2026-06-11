"""Detectors for anomalous category-level spending distributions."""

import numpy as np
import pandas as pd
from scipy.stats import norm

from anomaly.config import (
    PERSONNEL_CATEGORIES,
    RARE_CATEGORIES,
    AnomalyConfig,
    is_election_year,
)
from anomaly.report import Finding, severity_from_z


def _mad_zscore(series: pd.Series) -> pd.Series:
    median = series.median()
    mad = (series - median).abs().median()
    if mad == 0:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return 0.6745 * (series - median) / mad


def _bh_reject(pvals: np.ndarray, q: float) -> np.ndarray:
    """Benjamini–Hochberg: boolean mask of rejected (significant) hypotheses."""
    n = len(pvals)
    if n == 0:
        return np.array([], dtype=bool)
    order = np.argsort(pvals)
    ranked = pvals[order]
    thresholds = q * (np.arange(1, n + 1) / n)
    below = ranked <= thresholds
    if not below.any():
        return np.zeros(n, dtype=bool)
    cutoff = ranked[np.nonzero(below)[0].max()]
    return pvals <= cutoff


def detect_category_outliers(
    summary_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """C — Flag offices whose category share of non-personnel spend is a peer outlier.

    Peers are restricted to offices with nonzero spend in the category — a
    zero-inflated share distribution makes any spend look extreme. Z-scores are
    computed on log shares (spending shares are right-skewed), converted to
    one-sided p-values, and Benjamini–Hochberg-corrected across all
    category×quarter tests to control the false discovery rate.
    """
    findings: list[Finding] = []

    if summary_df.empty:
        return findings

    # summary 'description' field maps to category names
    non_pers = summary_df[~summary_df["description"].isin(PERSONNEL_CATEGORIES)].copy()
    if non_pers.empty:
        return findings

    # Total non-personnel QTD spend per office×quarter. Negative category
    # totals (refund-heavy quarters) are clipped so a share can't exceed 100%.
    totals = (
        non_pers.assign(qtd_amount=non_pers["qtd_amount"].clip(lower=0))
        .groupby(["bioguide_id", "quarter_label"])["qtd_amount"]
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

    candidates: list[dict] = []
    for (category, quarter), grp in cat_totals.groupby(["description", "quarter_label"]):
        # Peer group: offices actually spending in this category
        nonzero = grp[grp["category_share"] > 0]
        if len(nonzero) < 10:
            continue
        shares = nonzero["category_share"]
        z_scores = _mad_zscore(np.log10(shares))
        pvals = pd.Series(norm.sf(z_scores), index=z_scores.index)

        for idx in nonzero.index:
            candidates.append({
                "idx": idx,
                "category": category,
                "quarter": quarter,
                "z": float(z_scores.loc[idx]),
                "p": float(pvals.loc[idx]),
                "peer_median_share": float(shares.median()),
            })

    if not candidates:
        return findings

    rejected = _bh_reject(np.array([c["p"] for c in candidates]), config.category_fdr_q)

    for cand, significant in zip(candidates, rejected):
        if not significant:
            continue
        row = cat_totals.loc[cand["idx"]]
        share = float(row["category_share"])
        # Floors: must be a meaningful slice of office spend and real dollars
        if share < config.category_min_share:
            continue
        if abs(float(row["qtd_amount"])) < config.category_min_amount:
            continue
        z = cand["z"]
        findings.append(Finding(
            detector_id="C",
            detector_name="Category spend outlier",
            severity=severity_from_z(z),
            bioguide_id=row["bioguide_id"],
            member_name=row["member_name"],
            party=row["party"],
            state=row["state"],
            quarter=str(cand["quarter"]),
            description=(
                f"{cand['category']} is {share:.1%} of non-personnel spend "
                f"(z={z:.1f}, peer median {cand['peer_median_share']:.1%})"
            ),
            amount=float(row["qtd_amount"]),
            extra={
                "category": cand["category"],
                "category_share": f"{share:.2%}",
                "peer_median_share": f"{cand['peer_median_share']:.2%}",
                "z_score": round(z, 2),
                "bh_p_value": round(cand["p"], 6),
            },
        ))

    findings.sort(key=lambda f: f.extra.get("z_score", 0), reverse=True)
    return findings


def detect_rare_category_dominance(
    summary_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """D — Flag offices where a rare/unusual category dominates non-personnel spend."""
    findings: list[Finding] = []

    if summary_df.empty:
        return findings

    non_pers = summary_df[~summary_df["description"].isin(PERSONNEL_CATEGORIES)].copy()

    totals = (
        non_pers.assign(qtd_amount=non_pers["qtd_amount"].clip(lower=0))
        .groupby(["bioguide_id", "quarter_label"])["qtd_amount"]
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

        # Extra check: FRANKED MAIL in Q3/Q4 of an election year
        is_franked_mail = category == "FRANKED MAIL"
        try:
            yr = int(str(quarter)[:4])
            q_num = int(str(quarter)[-1])
            election_concern = is_franked_mail and is_election_year(yr) and q_num in (3, 4)
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

    return findings

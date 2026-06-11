"""Detectors keyed to the political calendar: pre-election communications
surges, departing-member spend-downs, and year-end budget exhaustion."""

import pandas as pd

from anomaly.config import (
    COMMS_CATEGORIES,
    PERSONNEL_CATEGORIES,
    YEAR_END_CATEGORIES,
    AnomalyConfig,
    is_election_year,
)
from anomaly.report import Finding


def _year_quarter(label: str) -> tuple[int, int] | None:
    try:
        year, q = str(label).split("Q")
        return int(year), int(q)
    except (ValueError, AttributeError):
        return None


def _office_meta(summary_df: pd.DataFrame) -> pd.DataFrame:
    return (
        summary_df[["bioguide_id", "member_name", "party", "state"]]
        .drop_duplicates("bioguide_id")
        .set_index("bioguide_id")
    )


def detect_election_comms_surge(
    summary_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """N — Flag election-year Q2/Q3 communications spend far above the office's
    own off-year baseline.

    Franked mail is prohibited in the window before a general election, which
    makes a mail/printing surge in the quarters leading up to it pursuable.
    Baseline is the same office's Q2+Q3 communications spend in odd years; the
    same-quarter comparison controls for seasonality. Offices with no off-year
    history fall back to the peer median surge-year value.
    """
    findings: list[Finding] = []
    if summary_df.empty:
        return findings

    comms = summary_df[summary_df["description"].isin(COMMS_CATEGORIES)].copy()
    if comms.empty:
        return findings

    yq = comms["quarter_label"].map(_year_quarter)
    comms["year"] = yq.map(lambda t: t[0] if t else None)
    comms["q_num"] = yq.map(lambda t: t[1] if t else None)
    comms = comms[comms["q_num"].isin([2, 3])]
    if comms.empty:
        return findings

    per_office_year = (
        comms.groupby(["bioguide_id", "year"])["qtd_amount"].sum().reset_index()
    )
    meta = _office_meta(summary_df)

    election = per_office_year[per_office_year["year"].map(lambda y: is_election_year(int(y)))]
    off_year = per_office_year[~per_office_year["year"].map(lambda y: is_election_year(int(y)))]
    baselines = off_year.groupby("bioguide_id")["qtd_amount"].mean()

    for ey, ey_grp in election.groupby("year"):
        peer_median = float(ey_grp["qtd_amount"].median())
        for _, row in ey_grp.iterrows():
            bioguide = row["bioguide_id"]
            amount = float(row["qtd_amount"])
            own_baseline = baselines.get(bioguide)
            baseline = float(own_baseline) if pd.notna(own_baseline) else peer_median
            baseline_src = "own off-year Q2+Q3 mean" if pd.notna(own_baseline) else "peer median"
            if baseline <= 0:
                continue
            ratio = amount / baseline
            delta = amount - baseline
            if ratio < config.election_surge_ratio or delta < config.election_surge_min_delta:
                continue
            if bioguide not in meta.index:
                continue
            m = meta.loc[bioguide]
            findings.append(Finding(
                detector_id="N",
                detector_name="Pre-election communications surge",
                severity="HIGH" if ratio >= 2 * config.election_surge_ratio else "MEDIUM",
                bioguide_id=bioguide,
                member_name=m["member_name"],
                party=m["party"],
                state=m["state"],
                quarter=f"{int(ey)}Q2–Q3",
                description=(
                    f"Election-year mail/printing spend ${amount:,.0f} in {int(ey)} Q2–Q3, "
                    f"{ratio:.1f}× {baseline_src} of ${baseline:,.0f}"
                ),
                amount=amount,
                extra={
                    "election_year": int(ey),
                    "baseline": round(baseline, 2),
                    "baseline_source": baseline_src,
                    "ratio": round(ratio, 2),
                    "categories": ", ".join(sorted(COMMS_CATEGORIES)),
                },
            ))

    findings.sort(key=lambda f: f.extra.get("ratio", 0), reverse=True)
    return findings


def detect_departing_spend_down(
    summary_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """O — Flag departing members whose final two quarters of non-personnel
    spend run well above their own trailing average.

    Departure is inferred from the data: a bioguide present in congress N but
    absent from congress N+1 (when N+1 appears in the data). Lame-duck
    equipment and furniture buys are a perennial accountability story.
    """
    findings: list[Finding] = []
    if summary_df.empty or "congress" not in summary_df.columns:
        return findings

    non_pers = summary_df[~summary_df["description"].isin(PERSONNEL_CATEGORIES)].copy()
    non_pers = non_pers[non_pers["congress"].notna()]
    if non_pers.empty:
        return findings

    congresses = sorted(int(c) for c in non_pers["congress"].unique())
    members_by_congress = {
        c: set(non_pers.loc[non_pers["congress"] == c, "bioguide_id"]) for c in congresses
    }
    departed: set[str] = set()
    for c in congresses:
        if c + 1 in members_by_congress:
            departed |= members_by_congress[c] - members_by_congress[c + 1]

    if not departed:
        return findings

    per_quarter = (
        non_pers.groupby(["bioguide_id", "quarter_label", "quarter_sort_key"])["qtd_amount"]
        .sum()
        .reset_index()
        .sort_values("quarter_sort_key")
    )
    meta = _office_meta(summary_df)

    for bioguide in sorted(departed):
        history = per_quarter[per_quarter["bioguide_id"] == bioguide]
        if len(history) < 4:  # need a baseline before the final two quarters
            continue
        final_two = history.tail(2)
        baseline_rows = history.iloc[:-2].tail(4)
        baseline = float(baseline_rows["qtd_amount"].mean())
        if baseline <= 0:
            continue
        final_avg = float(final_two["qtd_amount"].mean())
        ratio = final_avg / baseline
        delta = float(final_two["qtd_amount"].sum()) - 2 * baseline
        if ratio < config.spend_down_ratio or delta < config.spend_down_min_delta:
            continue
        if bioguide not in meta.index:
            continue
        m = meta.loc[bioguide]
        quarters = ", ".join(final_two["quarter_label"])
        findings.append(Finding(
            detector_id="O",
            detector_name="Departing-member spend-down",
            severity="HIGH" if ratio >= 2.0 else "MEDIUM",
            bioguide_id=bioguide,
            member_name=m["member_name"],
            party=m["party"],
            state=m["state"],
            quarter=quarters,
            description=(
                f"Final-quarter non-personnel spend ${final_avg:,.0f}/qtr is "
                f"{ratio:.1f}× own trailing average ${baseline:,.0f}/qtr "
                f"(member left after this congress)"
            ),
            amount=float(final_two["qtd_amount"].sum()),
            extra={
                "final_quarters": quarters,
                "trailing_avg_per_quarter": round(baseline, 2),
                "ratio": round(ratio, 2),
                "excess_spend": round(delta, 2),
            },
        ))

    findings.sort(key=lambda f: f.extra.get("excess_spend", 0), reverse=True)
    return findings


def detect_year_end_exhaustion(
    summary_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """P — Flag Q4 equipment/supplies spend far above the office's own Q1–Q3
    average. The MRA is use-it-or-lose-it, so December buying sprees are a
    recurring waste pattern."""
    findings: list[Finding] = []
    if summary_df.empty:
        return findings

    ye = summary_df[summary_df["description"].isin(YEAR_END_CATEGORIES)].copy()
    if ye.empty:
        return findings

    yq = ye["quarter_label"].map(_year_quarter)
    ye["year"] = yq.map(lambda t: t[0] if t else None)
    ye["q_num"] = yq.map(lambda t: t[1] if t else None)
    ye = ye[ye["year"].notna()]

    per_oyq = (
        ye.groupby(["bioguide_id", "year", "q_num"])["qtd_amount"].sum().reset_index()
    )
    meta = _office_meta(summary_df)

    for (bioguide, year), grp in per_oyq.groupby(["bioguide_id", "year"]):
        q4 = grp[grp["q_num"] == 4]
        early = grp[grp["q_num"].isin([1, 2, 3])]
        if q4.empty or len(early) < 2:
            continue
        q4_amount = float(q4["qtd_amount"].sum())
        baseline = float(early["qtd_amount"].mean())
        if baseline <= 0:
            continue
        ratio = q4_amount / baseline
        delta = q4_amount - baseline
        if ratio < config.year_end_ratio or delta < config.year_end_min_delta:
            continue
        if bioguide not in meta.index:
            continue
        m = meta.loc[bioguide]
        findings.append(Finding(
            detector_id="P",
            detector_name="Year-end budget exhaustion",
            severity="HIGH" if ratio >= 2 * config.year_end_ratio else "MEDIUM",
            bioguide_id=bioguide,
            member_name=m["member_name"],
            party=m["party"],
            state=m["state"],
            quarter=f"{int(year)}Q4",
            description=(
                f"Q4 equipment/supplies spend ${q4_amount:,.0f} is {ratio:.1f}× "
                f"own Q1–Q3 average ${baseline:,.0f}"
            ),
            amount=q4_amount,
            extra={
                "q1_q3_avg": round(baseline, 2),
                "ratio": round(ratio, 2),
                "excess_spend": round(delta, 2),
                "categories": ", ".join(sorted(YEAR_END_CATEGORIES)),
            },
        ))

    findings.sort(key=lambda f: f.extra.get("excess_spend", 0), reverse=True)
    return findings

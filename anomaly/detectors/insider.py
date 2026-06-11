"""Detectors for potential self-dealing: payments to vendors connected to the
member by name, and payments to individuals rather than firms."""

import re

import pandas as pd

from anomaly.config import PERSONNEL_CATEGORIES, AnomalyConfig
from anomaly.report import Finding
from anomaly.vendors import ENTITY_SUFFIXES, is_member_reimbursement

# Name suffixes that aren't surnames.
_NAME_SUFFIXES = frozenset({"JR", "SR", "II", "III", "IV", "V", "MD", "DDS"})

PERSON_VENDOR_CATEGORIES = frozenset({"OTHER SERVICES", "EQUIPMENT"})

# Vendor tokens that mark a business even without a legal-form suffix.
_BUSINESS_TOKENS = frozenset({
    "GROUP", "ASSOCIATES", "SERVICES", "CONSULTING", "PARTNERS", "SOLUTIONS",
    "REALTY", "PROPERTIES", "ENTERPRISES", "COMMUNICATIONS", "MANAGEMENT",
    "OFFICE", "CENTER", "CENTRE", "STUDIO", "STUDIOS", "MEDIA", "PRESS",
    "PRINTING", "RENTALS", "LEASING", "HOLDINGS", "VENTURES", "AGENCY",
    "TECHNOLOGIES", "SYSTEMS", "DESIGN", "DESIGNS",
})


def member_surname(member_name: str | None) -> str | None:
    """Extract the surname token from a member's display name."""
    if member_name is None or pd.isna(member_name) or not str(member_name).strip():
        return None
    cleaned = re.sub(r"[^A-Za-z\- ]", " ", str(member_name)).upper()
    tokens = [t for t in cleaned.split() if t and t not in _NAME_SUFFIXES]
    if not tokens:
        return None
    return tokens[-1]


def _vendor_col(df: pd.DataFrame) -> str:
    return "canonical_vendor" if "canonical_vendor" in df.columns else "vendor_name"


def _surname_counts(detail_df: pd.DataFrame) -> dict[str, int]:
    """How many distinct members share each surname (incl. hyphen parts)."""
    counts: dict[str, int] = {}
    roster = detail_df[["bioguide_id", "member_name"]].drop_duplicates("bioguide_id")
    for _, row in roster.iterrows():
        surname = member_surname(row["member_name"])
        if not surname:
            continue
        for part in {surname, *surname.split("-")}:
            if part:
                counts[part] = counts.get(part, 0) + 1
    return counts


def detect_member_name_vendors(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """L — Flag non-personnel payments to vendors containing the member's surname.

    The classic self-dealing shape: rent paid to the member's own LLC, services
    bought from a relative. Surnames shared by multiple members get a higher
    dollar floor to suppress coincidental matches on common names.
    """
    findings: list[Finding] = []

    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"] > 0)
        & (~detail_df["category"].isin(PERSONNEL_CATEGORIES))
        & (detail_df["member_name"].notna())
    ].copy()
    if ap.empty:
        return findings

    vcol = _vendor_col(ap)
    surname_freq = _surname_counts(detail_df)

    per_office_vendor = (
        ap.groupby(["bioguide_id", vcol, "member_name", "party", "state"], observed=True)
        .agg(
            total_amount=("amount", "sum"),
            transaction_count=("amount", "count"),
            quarters=("quarter_label", lambda x: ", ".join(sorted(x.unique()))),
            categories=("category", lambda x: ", ".join(sorted(set(str(c) for c in x)))),
        )
        .reset_index()
    )

    for _, row in per_office_vendor.iterrows():
        surname = member_surname(row["member_name"])
        if not surname or len(surname) < 4:
            continue
        vendor = str(row[vcol])
        if is_member_reimbursement(vendor):
            continue  # reimbursement to the member, not a third-party vendor
        vendor_tokens = set(vendor.split())
        name_parts = {surname, *surname.split("-")}
        matched = {p for p in name_parts if len(p) >= 4 and p in vendor_tokens}
        if not matched:
            continue

        shared = max(surname_freq.get(p, 1) for p in matched) > 1
        floor = config.insider_shared_surname_min if shared else config.insider_min_amount
        total = float(row["total_amount"])
        if total < floor:
            continue

        findings.append(Finding(
            detector_id="L",
            detector_name="Member-name vendor match",
            severity="HIGH",
            bioguide_id=row["bioguide_id"],
            member_name=row["member_name"],
            party=row["party"],
            state=row["state"],
            description=(
                f"Paid ${total:,.0f} to {vendor} — vendor name contains "
                f"member surname '{'/'.join(sorted(matched))}'"
            ),
            amount=total,
            vendor_name=vendor,
            extra={
                "matched_surname": ", ".join(sorted(matched)),
                "surname_shared_by_members": shared,
                "transaction_count": int(row["transaction_count"]),
                "quarters": row["quarters"],
                "categories": row["categories"],
            },
        ))

    findings.sort(key=lambda f: f.amount or 0, reverse=True)
    return findings


def _looks_like_person(vendor: str) -> bool:
    """Heuristic: 2–3 alphabetic tokens, no business/legal-form markers."""
    tokens = vendor.split()
    if len(tokens) < 2 or len(tokens) > 3:
        return False
    token_set = set(tokens)
    if token_set & (ENTITY_SUFFIXES | _BUSINESS_TOKENS):
        return False
    # Allow a middle initial; all other tokens must be purely alphabetic names
    for i, t in enumerate(tokens):
        if i == 1 and len(tokens) == 3 and len(t) == 1:
            continue
        if not t.isalpha() or len(t) < 2:
            return False
    return True


def detect_person_payees(
    detail_df: pd.DataFrame, config: AnomalyConfig
) -> list[Finding]:
    """M — Flag significant non-payroll payments to person-shaped payees.

    Individuals paid through OTHER SERVICES or EQUIPMENT (rather than payroll)
    are consultants, landlords, or contractors worth a look once cumulative
    spend is substantial.
    """
    findings: list[Finding] = []

    ap = detail_df[
        (detail_df["data_source"] == "AP")
        & (detail_df["amount"] > 0)
        & (detail_df["category"].isin(PERSON_VENDOR_CATEGORIES))
    ].copy()
    if ap.empty:
        return findings

    vcol = _vendor_col(ap)
    ap = ap[ap[vcol].notna() & (ap[vcol] != "")]
    ap = ap[~ap[vcol].map(is_member_reimbursement)]
    ap = ap[ap[vcol].map(lambda v: _looks_like_person(str(v)))]
    if ap.empty:
        return findings

    per_office_vendor = (
        ap.groupby(["bioguide_id", vcol, "member_name", "party", "state"], observed=True)
        .agg(
            total_amount=("amount", "sum"),
            transaction_count=("amount", "count"),
            quarters=("quarter_label", lambda x: ", ".join(sorted(x.unique()))),
            categories=("category", lambda x: ", ".join(sorted(set(str(c) for c in x)))),
        )
        .reset_index()
    )

    flagged = per_office_vendor[
        per_office_vendor["total_amount"] >= config.person_vendor_min_amount
    ].sort_values("total_amount", ascending=False)

    for _, row in flagged.iterrows():
        total = float(row["total_amount"])
        findings.append(Finding(
            detector_id="M",
            detector_name="Person-shaped payee",
            severity="HIGH" if total >= 25000 else "MEDIUM",
            bioguide_id=row["bioguide_id"],
            member_name=row["member_name"],
            party=row["party"],
            state=row["state"],
            description=(
                f"Paid ${total:,.0f} to {row[vcol]} ({row['categories']}) — "
                f"payee appears to be an individual, not a firm"
            ),
            amount=total,
            vendor_name=row[vcol],
            extra={
                "transaction_count": int(row["transaction_count"]),
                "quarters": row["quarters"],
                "categories": row["categories"],
            },
        ))

    return findings

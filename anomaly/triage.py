"""Triage detector findings into ranked story leads.

A story lead bundles every finding about one member-vendor relationship (or
one office, for findings with no vendor) and scores it for newsworthiness:
dollars at stake, how many independent detectors corroborate it, how long the
pattern persists, and how inherently pursuable each detector's signal is.
Bookkeeping-style detectors (negative rates, washes, round numbers, velocity)
only ever corroborate — they never form a lead on their own.
"""

import math
from dataclasses import dataclass, field

import pandas as pd

from anomaly.config import CORROBORATION_ONLY_DETECTORS, AnomalyConfig
from anomaly.report import Finding


def _clean(value) -> str | None:
    """Normalize pandas NA / empty values from detector findings to None."""
    if value is None or (pd.api.types.is_scalar(value) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s or None

# One-line phrase per detector, used to compose the lead's narrative hook.
DETECTOR_PHRASES: dict[str, str] = {
    "A": "unusually high refund/reversal rate",
    "B": "negative transactions recurring across quarters",
    "C": "category share far above peers",
    "D": "rare spending category dominates",
    "E": "vendor used by almost no other offices",
    "F": "vendor dominates the office's spending",
    "G": "recently debuted vendor with coordinated spending",
    "H": "outsized single transaction",
    "I": "cluster of round-dollar payments",
    "J": "near-exact offsetting transaction pair",
    "K": "unusually high transaction volume",
    "L": "vendor name matches the member's surname",
    "M": "payee appears to be an individual, not a firm",
    "N": "pre-election communications surge",
    "O": "spending ramp-up before leaving office",
    "P": "year-end budget-exhaustion spree",
}


@dataclass
class StoryLead:
    bioguide_id: str | None
    member_name: str | None
    party: str | None
    state: str | None
    vendor_name: str | None
    findings: list[Finding] = field(default_factory=list)
    score: float = 0.0
    hook: str = ""

    @property
    def detectors(self) -> set[str]:
        return {f.detector_id for f in self.findings}

    @property
    def quarters(self) -> list[str]:
        qs: set[str] = set()
        for f in self.findings:
            if f.quarter:
                qs.add(str(f.quarter))
            extra_q = f.extra.get("quarters")
            if extra_q:
                qs.update(q.strip() for q in str(extra_q).split(",") if q.strip())
        return sorted(qs)

    @property
    def amount(self) -> float:
        """Largest single finding amount — findings about the same money
        overlap (e.g. rare vendor + concentration), so summing double-counts."""
        return max((abs(f.amount) for f in self.findings if f.amount is not None), default=0.0)


def _lead_key(f: Finding) -> tuple[str, str]:
    return (_clean(f.bioguide_id) or "", _clean(f.vendor_name) or "")


def _score(lead: StoryLead, config: AnomalyConfig) -> float:
    weights = config.detector_weights
    detectors = lead.detectors

    weight_sum = sum(weights.get(d, 1.0) for d in detectors)
    corroboration = 2.0 * (len(detectors) - 1)
    magnitude = math.log10(max(lead.amount, 1.0))
    persistence = min(0.5 * max(len(lead.quarters) - 1, 0), 2.0)

    score = weight_sum + corroboration + magnitude + persistence
    if lead.amount < config.lead_min_amount:
        score -= 2.0
    # Relative magnitude: spending that is a large slice of the office budget
    # matters more than the same dollars in a big-budget office.
    for f in lead.findings:
        office_total = f.extra.get("office_non_personnel_total")
        if office_total and f.amount and float(office_total) > 0:
            share = abs(float(f.amount)) / float(office_total)
            score += min(1.0, share)
            break
    return round(score, 2)


def _hook(lead: StoryLead) -> str:
    who = lead.member_name or lead.bioguide_id or "Multiple offices"
    phrases = [DETECTOR_PHRASES.get(d, d) for d in sorted(lead.detectors)]
    parts = [f"{who}: ${lead.amount:,.0f}"]
    if lead.vendor_name:
        parts.append(f"to {lead.vendor_name}")
    qs = lead.quarters
    span = f"{qs[0]}–{qs[-1]}" if len(qs) > 1 else (qs[0] if qs else "")
    if span:
        parts.append(f"({span})")
    return " ".join(parts) + " — " + "; ".join(phrases)


def build_leads(findings: list[Finding], config: AnomalyConfig) -> list[StoryLead]:
    """Group findings into leads, score them, and return the top max_leads."""
    grouped: dict[tuple[str, str], StoryLead] = {}
    for f in findings:
        key = _lead_key(f)
        lead = grouped.get(key)
        if lead is None:
            lead = StoryLead(
                bioguide_id=_clean(f.bioguide_id),
                member_name=_clean(f.member_name),
                party=_clean(f.party),
                state=_clean(f.state),
                vendor_name=_clean(f.vendor_name),
            )
            grouped[key] = lead
        lead.findings.append(f)
        if lead.member_name is None:
            lead.member_name = _clean(f.member_name)

    leads = []
    for lead in grouped.values():
        # Bookkeeping signals never carry a lead by themselves
        if lead.detectors <= CORROBORATION_ONLY_DETECTORS:
            continue
        lead.score = _score(lead, config)
        lead.hook = _hook(lead)
        leads.append(lead)

    leads.sort(key=lambda l: l.score, reverse=True)
    return leads[: config.max_leads]

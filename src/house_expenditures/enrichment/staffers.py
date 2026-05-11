"""Extract staffers from PERSONNEL COMPENSATION records with partisan classification."""

import logging

from house_expenditures.enrichment.congress import classify_office_party
from house_expenditures.models import DetailRecord, StafferRecord
from house_expenditures.parsers.normalize import clean_title, is_member_org, strip_year_prefix

logger = logging.getLogger(__name__)


def extract_staffers(
    records: list[DetailRecord], congress: int, quarter_label: str
) -> list[StafferRecord]:
    """Extract staffer records from enriched detail records.

    Filters for PERSONNEL COMPENSATION category and classifies
    each staffer's party based on their office.
    """
    staffers: list[StafferRecord] = []

    for record in records:
        if record.category.upper() != "PERSONNEL COMPENSATION":
            continue

        name = (record.vendor_name or "").strip()
        if not name:
            continue

        title = clean_title(record.description or "")
        _, office_cleaned = strip_year_prefix(record.organization)

        # Determine party
        if record.is_member and record.party:
            party = record.party
        elif record.is_member and not record.party:
            party = None
        else:
            party = classify_office_party(office_cleaned, congress)

        staffer = StafferRecord(
            name=name,
            title=title,
            office=office_cleaned,
            bioguide_id=record.bioguide_id,
            party=party,
            state=record.state,
            district=record.district,
            quarter=quarter_label,
            start_date=record.start_date,
            end_date=record.end_date,
            amount=record.amount,
        )
        staffers.append(staffer)

    logger.info("Extracted %d staffer records for %s", len(staffers), quarter_label)
    return staffers


def unique_staffers(records: list[StafferRecord]) -> list[str]:
    """Return unique staffer names."""
    seen: set[str] = set()
    result: list[str] = []
    for r in records:
        if r.name not in seen:
            seen.add(r.name)
            result.append(r.name)
    return sorted(result)


def unique_offices(records: list[StafferRecord]) -> list[str]:
    """Return unique non-member offices."""
    seen: set[str] = set()
    result: list[str] = []
    for r in records:
        if r.bioguide_id:
            continue
        if r.office not in seen:
            seen.add(r.office)
            result.append(r.office)
    return sorted(result)


def unique_titles(records: list[StafferRecord]) -> list[str]:
    """Return unique standardized titles."""
    seen: set[str] = set()
    result: list[str] = []
    for r in records:
        if r.title and r.title not in seen:
            seen.add(r.title)
            result.append(r.title)
    return sorted(result)

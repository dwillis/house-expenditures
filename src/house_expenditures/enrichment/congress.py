"""Quarter-to-Congress mapping and party utilities."""

from house_expenditures.config import (
    LEADERSHIP_OFFICES_MAJORITY,
    LEADERSHIP_OFFICES_MINORITY,
    MAJORITY_PARTY,
    PARTY_ORGANIZATIONS,
)


def quarter_to_congress(year: int, quarter: int = 1) -> int:
    """Map a year/quarter to the Congress number.

    Congress terms start Jan 3 of odd years. Since expenditure quarters
    always use the calendar year, the formula is straightforward.
    """
    return ((year - 1789) // 2) + 1


def get_majority_party(congress: int) -> str | None:
    """Get the majority party for a given Congress."""
    return MAJORITY_PARTY.get(congress)


def get_minority_party(congress: int) -> str | None:
    majority = get_majority_party(congress)
    if majority == "R":
        return "D"
    elif majority == "D":
        return "R"
    return None


def classify_office_party(org_name: str, congress: int) -> str | None:
    """Determine party affiliation from a non-member office name.

    Returns "R", "D", or None (non-partisan / unknown).
    """
    upper = org_name.upper().strip()

    for pattern, party in PARTY_ORGANIZATIONS.items():
        if pattern in upper:
            return party

    for pattern in LEADERSHIP_OFFICES_MAJORITY:
        if pattern in upper:
            return get_majority_party(congress)

    for pattern in LEADERSHIP_OFFICES_MINORITY:
        if pattern in upper:
            return get_minority_party(congress)

    return None

from pathlib import Path

from house_expenditures.enrichment.legislators import (
    LegislatorIndex,
    filter_for_congress,
    load_legislators,
)
from house_expenditures.enrichment.matcher import match_legislator

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _build_index() -> LegislatorIndex:
    path = FIXTURES_DIR / "legislators_sample.yaml"
    legislators = load_legislators(path, path)
    # Use congress 118 (2023-2025) — filters to legislators serving then
    congress_legs = filter_for_congress(legislators, 118)
    return LegislatorIndex(congress_legs)


def test_exact_match():
    index = _build_index()
    leg = match_legislator("2024 HON. ALMA S. ADAMS", index)
    assert leg is not None
    assert leg.bioguide_id == "A000370"
    assert leg.state == "NC"


def test_match_with_state_disambiguation():
    index = _build_index()
    leg = match_legislator("2024 HON. MIKE ROGERS (AL)", index)
    assert leg is not None
    assert leg.bioguide_id == "R000575"
    assert leg.state == "AL"


def test_non_member_returns_none():
    index = _build_index()
    leg = match_legislator("2024 OFFICE OF THE SPEAKER", index)
    assert leg is None


def test_match_with_overrides():
    index = _build_index()
    overrides = {"ALMA S. ADAMS": "A000370"}
    leg = match_legislator("2024 HON. ALMA S. ADAMS", index, overrides)
    assert leg is not None
    assert leg.bioguide_id == "A000370"


def test_unmatched_returns_none():
    index = _build_index()
    leg = match_legislator("2024 HON. NONEXISTENT PERSON", index)
    assert leg is None


def test_nickname_match():
    """Earl L. 'Buddy' Carter should match via first+last or nickname."""
    index = _build_index()
    leg = match_legislator("2024 HON. EARL L. CARTER", index)
    assert leg is not None
    assert leg.bioguide_id == "C001103"


def test_org_code_state_disambiguation():
    """MIKE ROGERS with org_code should disambiguate by state."""
    index = _build_index()

    # With org_code for Alabama
    leg = match_legislator("2024 HON. MIKE ROGERS", index, org_code="AL03ROM")
    assert leg is not None
    assert leg.bioguide_id == "R000575"
    assert leg.state == "AL"

    # With org_code for Michigan
    leg = match_legislator("2024 HON. MIKE ROGERS", index, org_code="MI07ROM")
    assert leg is not None
    assert leg.bioguide_id == "R000395"
    assert leg.state == "MI"


def test_filter_for_congress():
    path = FIXTURES_DIR / "legislators_sample.yaml"
    legislators = load_legislators(path, path)

    # Congress 118 (2023-2025)
    c118 = filter_for_congress(legislators, 118)
    bioguides = {leg.bioguide_id for leg in c118}
    assert "A000370" in bioguides  # Adams serving in 118th
    assert "R000575" in bioguides  # Rogers (AL) serving in 118th
    assert "B001313" in bioguides  # Kamlager-Dove serving in 118th

    # Rogers (MI) also serving in 118th (added back for disambiguation tests)
    mi_rogers = [l for l in c118 if l.bioguide_id == "R000395"]
    assert len(mi_rogers) >= 1

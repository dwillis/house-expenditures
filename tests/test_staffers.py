from decimal import Decimal
from pathlib import Path

from house_expenditures.enrichment.legislators import (
    LegislatorIndex,
    filter_for_congress,
    load_legislators,
)
from house_expenditures.enrichment.matcher import enrich_detail_records
from house_expenditures.enrichment.staffers import (
    extract_staffers,
    unique_offices,
    unique_staffers,
    unique_titles,
)
from house_expenditures.parsers.detail import parse_detail

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _get_enriched_records():
    detail_path = FIXTURES_DIR / "detail_12col_sample.csv"
    records = parse_detail(detail_path)

    leg_path = FIXTURES_DIR / "legislators_sample.yaml"
    legislators = load_legislators(leg_path, leg_path)
    congress_legs = filter_for_congress(legislators, 117)
    index = LegislatorIndex(congress_legs)

    return enrich_detail_records(records, index, 117, "2022Q1")


def test_extract_staffers():
    records = _get_enriched_records()
    staffers = extract_staffers(records, 117, "2022Q1")
    # Should extract PERSONNEL COMPENSATION records only
    assert len(staffers) == 2  # JANE DOE and JOHN SMITH

    names = [s.name for s in staffers]
    assert "JANE DOE" in names
    assert "JOHN SMITH" in names


def test_staffer_party_from_member():
    records = _get_enriched_records()
    staffers = extract_staffers(records, 117, "2022Q1")

    jane = [s for s in staffers if s.name == "JANE DOE"][0]
    # Adams is a Democrat
    assert jane.party == "D"


def test_staffer_title_cleaning():
    records = _get_enriched_records()
    staffers = extract_staffers(records, 117, "2022Q1")

    john = [s for s in staffers if s.name == "JOHN SMITH"][0]
    # "(OTHER COMPENSATION)" should be stripped
    assert "OTHER COMPENSATION" not in john.title
    assert john.title == "LEGISLATIVE DIRECTOR"


def test_unique_staffers():
    records = _get_enriched_records()
    staffers = extract_staffers(records, 117, "2022Q1")
    names = unique_staffers(staffers)
    assert len(names) == 2


def test_unique_titles():
    records = _get_enriched_records()
    staffers = extract_staffers(records, 117, "2022Q1")
    titles = unique_titles(staffers)
    assert "STAFF ASSISTANT" in titles
    assert "LEGISLATIVE DIRECTOR" in titles

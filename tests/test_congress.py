from house_expenditures.enrichment.congress import (
    classify_office_party,
    get_majority_party,
    get_minority_party,
    quarter_to_congress,
)


def test_quarter_to_congress_basic():
    assert quarter_to_congress(2016, 1) == 114
    assert quarter_to_congress(2016, 4) == 114
    assert quarter_to_congress(2017, 1) == 115
    assert quarter_to_congress(2019, 1) == 116
    assert quarter_to_congress(2023, 1) == 118
    assert quarter_to_congress(2025, 1) == 119


def test_majority_party():
    assert get_majority_party(114) == "R"
    assert get_majority_party(116) == "D"
    assert get_majority_party(118) == "R"


def test_minority_party():
    assert get_minority_party(114) == "D"
    assert get_minority_party(116) == "R"


def test_classify_office_party_leadership():
    assert classify_office_party("OFFICE OF THE SPEAKER", 118) == "R"
    assert classify_office_party("OFFICE OF THE SPEAKER", 116) == "D"
    assert classify_office_party("OFFICE OF THE MINORITY LEADER", 118) == "D"


def test_classify_office_party_organizations():
    assert classify_office_party("REPUBLICAN CONFERENCE", 118) == "R"
    assert classify_office_party("DEMOCRATIC CAUCUS", 118) == "D"


def test_classify_office_party_nonpartisan():
    assert classify_office_party("OFFICE OF THE CLERK", 118) is None
    assert classify_office_party("COMMITTEE ON APPROPRIATIONS", 118) is None

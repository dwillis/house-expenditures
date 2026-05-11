from house_expenditures.parsers.normalize import (
    clean_title,
    is_member_org,
    normalize_text,
    parse_member_name,
    strip_year_prefix,
)


def test_normalize_text_en_dash():
    assert normalize_text("Jan–Feb") == "Jan-Feb"


def test_normalize_text_smart_quotes():
    assert normalize_text("“Hello”") == '"Hello"'
    assert normalize_text("‘world’") == "'world'"


def test_normalize_text_whitespace():
    assert normalize_text("  foo   bar  ") == "foo bar"


def test_strip_year_prefix():
    year, name = strip_year_prefix("2024 HON. JOHN SMITH")
    assert year == "2024"
    assert name == "HON. JOHN SMITH"


def test_strip_year_prefix_no_year():
    year, name = strip_year_prefix("OFFICE OF THE CLERK")
    assert year is None
    assert name == "OFFICE OF THE CLERK"


def test_parse_member_name_simple():
    result = parse_member_name("2024 HON. ALMA S. ADAMS")
    assert result["is_member"] is True
    assert result["first"] == "ALMA"
    assert result["last"] == "ADAMS"
    assert result["middle"] == "S."
    assert result["state_hint"] is None


def test_parse_member_name_with_state():
    result = parse_member_name("2022 HON. MIKE ROGERS (AL)")
    assert result["is_member"] is True
    assert result["first"] == "MIKE"
    assert result["last"] == "ROGERS"
    assert result["state_hint"] == "AL"


def test_parse_member_name_with_suffix():
    result = parse_member_name("HON. HENRY C. JOHNSON JR.")
    assert result["is_member"] is True
    assert result["last"] == "JOHNSON"
    assert result["suffix"] == "JR."


def test_parse_member_name_non_member():
    result = parse_member_name("OFFICE OF THE SPEAKER")
    assert result["is_member"] is False


def test_clean_title_removes_other_compensation():
    assert clean_title("STAFF ASSISTANT (OTHER COMPENSATION)") == "STAFF ASSISTANT"


def test_clean_title_removes_overtime():
    assert clean_title("LEGISLATIVE DIRECTOR (OVERTIME)") == "LEGISLATIVE DIRECTOR"


def test_clean_title_normal():
    assert clean_title("CHIEF OF STAFF") == "CHIEF OF STAFF"


def test_is_member_org():
    assert is_member_org("2024 HON. JOHN SMITH") is True
    assert is_member_org("OFFICE OF THE CLERK") is False
    assert is_member_org("HON. JANE DOE") is True

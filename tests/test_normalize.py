from house_expenditures.parsers.normalize import (
    clean_title,
    is_member_org,
    normalize_date,
    normalize_for_matching,
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


# --- normalize_date: exercised on every non-empty date in 4.7M real rows ---


def test_normalize_date_formats():
    # The only format seen in real data is dd-Mon-yy
    assert normalize_date("15-Feb-22") == "2022-02-15"
    assert normalize_date("1-Nov-24") == "2024-11-01"  # unpadded day
    # The remaining formats are accepted for robustness
    assert normalize_date("18-Mar-2016") == "2016-03-18"
    assert normalize_date("03/07/2025") == "2025-03-07"
    assert normalize_date("12/31/24") == "2024-12-31"


def test_normalize_date_two_digit_year_cutoff():
    # Expenditure data spans 2009-2026; Python's %y maps 00-68 -> 2000s
    assert normalize_date("15-Feb-09") == "2009-02-15"
    assert normalize_date("15-Feb-26") == "2026-02-15"


def test_normalize_date_unrecognized_returns_raw():
    # Formats outside the list pass through unchanged (NOT None) — callers
    # like the loader then coerce them to NaT downstream
    assert normalize_date("2024-02-15") == "2024-02-15"
    assert normalize_date("31-Jun-22") == "31-Jun-22"  # impossible date


def test_normalize_date_empty_is_none():
    assert normalize_date("") is None
    assert normalize_date("   ") is None


# --- organization-name variants present in real data ---


def test_strip_year_prefix_fiscal_year_org():
    # Institutional orgs use "FISCAL YEAR 2023 ..." — no leading year prefix
    year, name = strip_year_prefix("FISCAL YEAR 2023 SERGEANT AT ARMS")
    assert year is None
    assert name == "FISCAL YEAR 2023 SERGEANT AT ARMS"


def test_is_member_org_institutional():
    assert is_member_org("FISCAL YEAR 2023 CHIEF ADMIN OFCR OF THE HOUSE") is False
    assert is_member_org("FISCAL YEAR 2022 STATIONERY") is False


def test_parse_member_name_quoted_nickname():
    result = parse_member_name('2024 HON. EARL L. "BUDDY" CARTER')
    assert result["is_member"] is True
    assert result["first"] == "EARL"
    assert result["middle"] == "L."
    assert result["last"] == "CARTER"
    assert result["quoted_nickname"] == "BUDDY"
    assert result["state_hint"] is None


def test_parse_member_name_double_quote_as_apostrophe():
    # Real data renders O'ROURKE with a double quote
    result = parse_member_name('HON. BETO O"ROURKE')
    assert result["is_member"] is True
    assert result["first"] == "BETO"
    assert result["last"] == "O'ROURKE"


def test_normalize_for_matching():
    assert normalize_for_matching("GONZÁLEZ") == "GONZALEZ"
    assert normalize_for_matching("O’BRIEN") == "O'BRIEN"

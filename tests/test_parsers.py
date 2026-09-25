from decimal import Decimal

from house_expenditures.parsers.detail import (
    COLUMN_MAP_12,
    COLUMN_MAP_18,
    _detect_encoding,
    _detect_format,
    parse_detail,
)
from house_expenditures.parsers.summary import parse_summary


def test_parse_detail_12col(detail_12col_path):
    records = parse_detail(detail_12col_path)
    # Should have 4 records (SUBTOTAL row filtered out)
    assert len(records) == 4

    # Check first record
    r = records[0]
    assert "ALMA S. ADAMS" in r.organization
    assert r.category == "PERSONNEL COMPENSATION"
    assert r.vendor_name == "JANE DOE"
    assert r.amount == Decimal("2500")
    assert r.transaction_date == "2022-02-15"

    # 18-col fields should be None
    assert r.fiscal_year is None
    assert r.organization_code is None
    assert r.vendor_id is None


def test_parse_detail_12col_filters_subtotal(detail_12col_path):
    records = parse_detail(detail_12col_path)
    for r in records:
        assert r.sort_sequence.upper() != "SUBTOTAL"


def test_parse_detail_18col(detail_18col_path):
    records = parse_detail(detail_18col_path)
    assert len(records) == 3

    r = records[0]
    assert "ALMA S. ADAMS" in r.organization
    assert r.fiscal_year == "LY2024"
    assert r.organization_code == "21NC120"
    assert r.vendor_id == "0000012345"
    assert r.budget_object_code == "1105"
    assert r.amount == Decimal("2750")


def test_parse_detail_amount_parsing(detail_12col_path):
    records = parse_detail(detail_12col_path)
    amounts = [r.amount for r in records]
    assert Decimal("150.75") in amounts
    assert all(isinstance(a, Decimal) for a in amounts if a is not None)


def test_parse_summary(summary_path):
    records = parse_summary(summary_path)
    # TOTALS row should be filtered out
    assert len(records) == 2

    r = records[0]
    assert "ALMA S. ADAMS" in r.organization
    assert r.description == "PERSONNEL COMPENSATION"
    assert r.ytd_amount == Decimal("125000")
    assert r.qtd_amount == Decimal("42000")


def test_parse_detail_skips_row_with_multiple_extra_values(tmp_path):
    """Two unquoted commas produce two extra fields — no unique repair exists,
    so the row is skipped rather than guessed at."""
    p = tmp_path / "detail_multi_extra.csv"
    p.write_text(
        "ORGANIZATION,PROGRAM,SORT SUBTOTAL DESCRIPTION,SORT SEQUENCE,"
        "TRANSACTION DATE,DATA SOURCE,DOCUMENT,VENDOR NAME,PERFORM START DT,"
        "PERFORM END DT,DESCRIPTION,AMOUNT\n"
        "2020 HON. A,OFFICIAL,SUPPLIES,DETAIL,15-Jul-20,AP,123,VEN A,VEN B,"
        "EXTRA C,1-Feb-22,1-Feb-22,DESC,-50\n"
    )
    assert parse_detail(p) == []


def test_parse_detail_skips_ambiguous_repair(tmp_path):
    """When two different merge points are equally plausible the row is
    skipped instead of repaired — never guess between valid readings."""
    p = tmp_path / "detail_ambiguous.csv"
    # Re-merging at VENDOR NAME or at DESCRIPTION both validate
    p.write_text(
        "ORGANIZATION,PROGRAM,SORT SUBTOTAL DESCRIPTION,SORT SEQUENCE,"
        "TRANSACTION DATE,DATA SOURCE,DOCUMENT,VENDOR NAME,PERFORM START DT,"
        "PERFORM END DT,DESCRIPTION,AMOUNT\n"
        "2020 HON. A,OFFICIAL,SUPPLIES,DETAIL,15-Jul-20,AP,123,VEN,"
        "1-Feb-22,1-Feb-22,1-Feb-22,DESC,-50\n"
    )
    assert parse_detail(p) == []


def test_parse_summary_skips_misaligned_row(tmp_path):
    """A row with an extra field (unquoted comma) must not yield a record with
    shifted values. Summary files have only two typed columns (the amounts),
    too few to disambiguate a merge point, so the row is skipped — the detail
    parser repairs such rows because its typed columns pin the merge uniquely."""
    p = tmp_path / "summary_misaligned.csv"
    p.write_text(
        "ORGANIZATION,PROGRAM,DESCRIPTION,YTD AMOUNT,QTD AMOUNT\n"
        "2024 HON. ALMA S. ADAMS,MEMBERS REPRESENTATIONAL ALLOWANCE,"
        "PERSONNEL COMPENSATION,125000,42000\n"
        '2024 HON. "JANE, A. DOE",MEMBERS REPRESENTATIONAL ALLOWANCE,'
        "PERSONNEL COMPENSATION,1,2,3\n"
    )
    records = parse_summary(p)
    assert len(records) == 1
    assert records[0].organization == "2024 HON. ALMA S. ADAMS"
    assert records[0].qtd_amount == Decimal("42000")


# --- Real-data structure quirks (mirrored from the house.gov cache) ---


def test_parse_detail_padded_header_positional(detail_12col_padded_path):
    """Headers in 2020Q3-2022Q3 files end with trailing spaces and a trailing
    comma; rows must still land in the right columns."""
    records = parse_detail(detail_12col_padded_path)
    # 3 DETAIL rows survive; SUBTOTAL + GRAND TOTAL filtered
    assert len(records) == 3

    r = records[0]
    assert r.organization == "2020 HON. PAUL TONKO"
    assert r.category == "SUPPLIES AND MATERIALS"
    assert r.transaction_date == "2020-06-11"
    assert r.vendor_name == "CITI PCARD-AMZN Mktp US MS6GB0ZA0"
    assert r.start_date == "2020-06-11"
    assert r.end_date == "2020-06-11"
    assert r.description == "OFFICE SUPPLIES (OUTSIDE)"
    assert r.amount == Decimal("84.3")


def test_parse_detail_repairs_misaligned_row_12col(detail_12col_padded_path):
    """A vendor name containing an unquoted comma (real rows in 2020Q3-2022Q3
    cache files) splits into two CSV fields and shifts every later column.
    The parser re-merges the split field and restores the true values."""
    records = parse_detail(detail_12col_padded_path)
    assert len(records) == 3

    r = [r for r in records if "CNDTL" in (r.vendor_name or "")][0]
    assert r.vendor_name == "CITI PCARD-CNDTL CR,AMZN MKTP US M79"
    assert r.transaction_date == "2020-07-15"
    assert r.start_date == "2020-05-25"
    assert r.end_date == "2020-05-25"
    assert r.description == "OFFICE SUPPLIES (OUTSIDE)"
    assert r.amount == Decimal("-102.86")


def test_parse_detail_grand_total_filtered(detail_12col_padded_path):
    """GRAND TOTAL FOR ORGANIZATION rows are subtotal rows in disguise; they
    must never leak into transaction records (they would double-count)."""
    records = parse_detail(detail_12col_padded_path)
    assert all(r.sort_sequence != "GRAND TOTAL FOR ORGANIZATION" for r in records)
    assert all(not (r.description or "").endswith("TOTALS:") for r in records)


def test_parse_detail_18col_padded_header_positional(detail_18col_padded_path):
    """18-col headers with trailing spaces + trailing comma (2023Q3, 2025Q3)."""
    records = parse_detail(detail_18col_padded_path)
    assert len(records) == 2

    r = records[0]
    assert r.fiscal_year == "FY2023"
    assert r.organization_code == "50SG000"
    assert r.program == "NON - PERSONNEL"
    assert r.program_code == "NONPS"
    assert r.budget_object_class == "26"
    assert r.transaction_date == "2023-08-25"
    assert r.vendor_name == "CITI PCARD-STAPLES INC"
    assert r.vendor_id == "33707"
    assert r.start_date == "2023-05-11"
    assert r.end_date == "2023-05-11"
    assert r.budget_object_code == "2620"
    assert r.amount == Decimal("-45.5")


def test_parse_detail_repairs_misaligned_row_18col(detail_18col_padded_path):
    """Same unquoted-comma defect in an 18-col file (real rows in 2023Q3 and
    2025Q3). Without repair the amount column picks up the budget object
    code (2620) — a fabricated $2,620 transaction — and the true amount
    (-129.99) is lost."""
    records = parse_detail(detail_18col_padded_path)
    assert len(records) == 2

    r = [r for r in records if "CNDTL" in (r.vendor_name or "")][0]
    assert r.vendor_name == "CITI PCARD-CNDTL CR,AMZN MKTP US HD8"
    assert r.vendor_id == "33707"  # not the merchant name
    assert r.start_date == "2023-05-11"  # not '33707'
    assert r.end_date == "2023-05-11"
    assert r.description == "OFFICE SUPPLIES (OUTSIDE)"  # not a date
    assert r.budget_object_code == "2620"
    assert r.amount == Decimal("-129.99")  # not the fabricated 2620


def test_parse_detail_negative_amount(detail_18col_padded_path):
    """Refund/adjustment rows are negative; ~157k rows in the real data."""
    records = parse_detail(detail_18col_padded_path)
    assert records[0].amount == Decimal("-45.5")


def test_parse_detail_cp1252_encoding(detail_cp1252_path):
    """2016-2019 downloads are cp1252, not UTF-8; accents must survive."""
    records = parse_detail(detail_cp1252_path)
    assert len(records) == 2
    assert records[0].vendor_name == "CITI PCARD-MILOS DELI & CAFÉ"
    assert records[1].vendor_name == "WEBER GONZÁLEZ GROUP"


def test_parse_detail_quoted_comma_fields(detail_edge_cases_path):
    """Quoted commas are one field — unlike the unquoted case above."""
    records = parse_detail(detail_edge_cases_path)
    quoted = [r for r in records if r.vendor_name == "SMITH, JONES & ASSOCIATES LLC"]
    assert len(quoted) == 1
    assert quoted[0].amount == Decimal("1234.56")  # "1,234.56" quoted, commas stripped


def test_parse_detail_strips_field_whitespace(detail_edge_cases_path):
    """~878k real rows carry padded vendor names."""
    records = parse_detail(detail_edge_cases_path)
    assert any(r.vendor_name == "OFFICE DEPOT" for r in records)


def test_parse_detail_empty_fields_are_none(detail_edge_cases_path):
    """Empty dates and amounts become None, and the row is kept."""
    records = parse_detail(detail_edge_cases_path)
    postal = [r for r in records if r.vendor_name == "POSTAL SERVICE"][0]
    assert postal.transaction_date is None
    assert postal.start_date is None
    assert postal.end_date is None
    assert postal.description == "POSTAGE"


def test_parse_detail_invalid_amount_is_none(detail_edge_cases_path):
    """Non-numeric amounts currently degrade to None rather than raising."""
    records = parse_detail(detail_edge_cases_path)
    postal = [r for r in records if r.vendor_name == "POSTAL SERVICE"][0]
    assert postal.amount is None


def test_parse_detail_empty_amount_kept(detail_edge_cases_path):
    """A DETAIL row with an empty amount still parses (amount=None)."""
    records = parse_detail(detail_edge_cases_path)
    delta = [r for r in records if r.vendor_name == "DELTA AIR LINES"][0]
    assert delta.amount is None
    assert delta.transaction_date == "2022-04-09"


def test_detect_format_boundaries():
    assert _detect_format(["A", "", "B", " "]) is COLUMN_MAP_12
    # 17+ non-empty header columns -> 18-col schema
    assert _detect_format([f"C{i}" for i in range(17)]) is COLUMN_MAP_18
    assert _detect_format([f"C{i}" for i in range(12)]) is COLUMN_MAP_12


def test_detect_encoding(tmp_path):
    # Plain ASCII decodes with the first (BOM-tolerant) candidate
    plain = tmp_path / "plain.csv"
    plain.write_text("ORGANIZATION,AMOUNT\n")
    assert _detect_encoding(plain) == "utf-8-sig"

    # cp1252 accented byte (0xC9 = É) is invalid UTF-8
    cp = tmp_path / "cp.csv"
    cp.write_bytes("VENDOR,CAF\xc9\n".encode("latin-1"))
    assert _detect_encoding(cp) == "cp1252"

    # A UTF-8 BOM is stripped
    bom = tmp_path / "bom.csv"
    bom.write_bytes("\xef\xbb\xbfORGANIZATION\n".encode())
    assert _detect_encoding(bom) == "utf-8-sig"

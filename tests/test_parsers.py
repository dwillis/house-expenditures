from decimal import Decimal

from house_expenditures.parsers.detail import parse_detail
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

"""Unit tests for the generic misaligned-row repair helper."""

import re

from house_expenditures.parsers.repair import repair_row

# A free-text column, then typed columns — mirrors the detail schema shape
COLUMNS = ["ORGANIZATION", "DOCUMENT", "VENDOR NAME", "START", "AMOUNT"]


def _digits(value: str) -> bool:
    v = value.strip()
    return not v or v.isdigit()


def _date(value: str) -> bool:
    v = value.strip()
    return not v or re.fullmatch(r"\d{1,2}-Feb-22", v) is not None


def _amount(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return not value.strip()


VALIDATORS = {"DOCUMENT": _digits, "START": _date, "AMOUNT": _amount}


def test_repair_row_exact_merge():
    raw = ["2020 HON. A", "123", "CITI PCARD-CNDTL CR", "AMZN MKTP", "1-Feb-22", "-50"]
    assert repair_row(raw, COLUMNS, VALIDATORS) == {
        "ORGANIZATION": "2020 HON. A",
        "DOCUMENT": "123",
        "VENDOR NAME": "CITI PCARD-CNDTL CR,AMZN MKTP",
        "START": "1-Feb-22",
        "AMOUNT": "-50",
    }


def test_repair_row_ambiguous_returns_none():
    # The comma could be in ORGANIZATION or in VENDOR NAME and either way
    # every typed column validates — refuse to choose
    raw = ["ORG NAME", "123", "456", "VEN", "1-Feb-22", "-50"]
    assert repair_row(raw, COLUMNS, VALIDATORS) is None


def test_repair_row_no_valid_merge_returns_none():
    raw = ["A", "123", "VEN", "X", "NOT A DATE", "not-numeric"]
    assert repair_row(raw, COLUMNS, VALIDATORS) is None


def test_repair_row_wrong_arity_returns_none():
    # Two extra values: out of scope for a single-comma repair
    assert repair_row(
        ["A", "123", "VEN", "X", "1-Feb-22", "1-Feb-22", "-50"],
        COLUMNS, VALIDATORS,
    ) is None
    # A well-formed row has nothing to repair
    assert repair_row(
        ["A", "123", "VEN", "1-Feb-22", "-50"], COLUMNS, VALIDATORS,
    ) is None
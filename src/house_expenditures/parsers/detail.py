"""Parse House expenditure detail CSV files."""

import csv
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from house_expenditures.models import DetailRecord
from house_expenditures.parsers.normalize import normalize_date, normalize_text
from house_expenditures.parsers.repair import repair_row

DATE_FIELDS = {"transaction_date", "start_date", "end_date"}

logger = logging.getLogger(__name__)

# Column mapping from 12-column format to our standardized field names
COLUMN_MAP_12 = {
    "ORGANIZATION": "organization",
    "PROGRAM": "program",
    "SORT SUBTOTAL DESCRIPTION": "category",
    "SORT SEQUENCE": "sort_sequence",
    "TRANSACTION DATE": "transaction_date",
    "DATA SOURCE": "data_source",
    "DOCUMENT": "document",
    "VENDOR NAME": "vendor_name",
    "PERFORM START DT": "start_date",
    "PERFORM END DT": "end_date",
    "DESCRIPTION": "description",
    "AMOUNT": "amount",
}

# Column mapping from 18-column format
COLUMN_MAP_18 = {
    **COLUMN_MAP_12,
    "FISCAL YEAR OR LEGISLATIVE YEAR": "fiscal_year",
    "ORGANIZATION CODE": "organization_code",
    "PROGRAM CODE": "program_code",
    "BUDGET OBJECT CLASS": "budget_object_class",
    "VENDOR ID": "vendor_id",
    "BUDGET OBJECT CODE": "budget_object_code",
}


def _detect_format(header_fields: list[str]) -> dict[str, str]:
    """Detect CSV format based on the number of non-empty header columns."""
    cleaned = [h.strip() for h in header_fields if h.strip()]
    if len(cleaned) >= 17:
        return COLUMN_MAP_18
    return COLUMN_MAP_12


def _parse_amount(raw: str) -> Decimal | None:
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _detect_encoding(path: Path) -> str:
    """Detect file encoding by attempting to read the entire file."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "iso-8859-1"):
        try:
            raw.decode(encoding)
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "iso-8859-1"


# --- Repair validators: value shapes observed across all cached files ---
# A wrong merge point always places a comma-containing value in the merged
# column, so these typed-column checks are what pin the merge uniquely.
# Free-text columns (organization, program, category, vendor name,
# description) are intentionally unvalidated.

_UPPER_ALNUM = re.compile(r"[A-Z0-9]+\Z")
_UPPER_ALNUM_HYPHEN = re.compile(r"[A-Z0-9-]+\Z")
_DIGITS = re.compile(r"\d+\Z")
_SORT_SEQUENCES = {"DETAIL", "SUBTOTAL", "GRAND TOTAL FOR ORGANIZATION"}


def _empty_or(pattern: re.Pattern, value: str) -> bool:
    v = value.strip().upper()
    return not v or pattern.fullmatch(v) is not None


def _date_like(value: str) -> bool:
    v = value.strip()
    return not v or normalize_date(v) != v


def _amount_like(value: str) -> bool:
    v = value.strip()
    return not v or _parse_amount(v) is not None


REPAIR_VALIDATORS = {
    "TRANSACTION DATE": _date_like,
    "PERFORM START DT": _date_like,
    "PERFORM END DT": _date_like,
    "AMOUNT": _amount_like,
    "SORT SEQUENCE": lambda v: not v.strip() or v.strip().upper() in _SORT_SEQUENCES,
    "DATA SOURCE": lambda v: _empty_or(_UPPER_ALNUM, v),
    "DOCUMENT": lambda v: _empty_or(_UPPER_ALNUM_HYPHEN, v),
    "VENDOR ID": lambda v: _empty_or(_UPPER_ALNUM, v),
    "ORGANIZATION CODE": lambda v: _empty_or(_UPPER_ALNUM, v),
    "PROGRAM CODE": lambda v: _empty_or(_UPPER_ALNUM, v),
    "FISCAL YEAR OR LEGISLATIVE YEAR": lambda v: _empty_or(_UPPER_ALNUM, v),
    "BUDGET OBJECT CLASS": lambda v: _empty_or(_DIGITS, v),
    "BUDGET OBJECT CODE": lambda v: _empty_or(_DIGITS, v),
}


def parse_detail(path: Path) -> list[DetailRecord]:
    """Parse a detail CSV file into a list of DetailRecord objects."""
    records: list[DetailRecord] = []

    encoding = _detect_encoding(path)
    logger.debug("Reading %s with encoding %s", path.name, encoding)

    with open(path, "r", encoding=encoding, newline="") as f:
        first_line = f.readline()
        f.seek(0)

        header_fields = first_line.split(",")
        column_map = _detect_format(header_fields)

        reader = csv.DictReader(f, restkey="__extra__")
        if reader.fieldnames is None:
            return records

        # Clean up fieldnames (trailing commas produce empty fields)
        reader.fieldnames = [fn.strip() for fn in reader.fieldnames if fn.strip()]

        for row in reader:
            # A row with more values than the header means a field contained
            # an unquoted comma (real examples: CITI PCARD vendor names in the
            # 2020Q3-2022Q3 and 2023Q3/2025Q3 files), shifting every later
            # column. Try to repair it; skip only when no unique repair exists.
            # Files with padded headers carry one extra *empty* trailing value
            # on every row; those pass the check below untouched.
            extra = row.pop("__extra__", None)
            if extra and any(v.strip() for v in extra):
                raw = [row.get(col) or "" for col in reader.fieldnames] + list(extra)
                repaired = repair_row(raw, reader.fieldnames, REPAIR_VALIDATORS)
                if repaired is None:
                    logger.warning(
                        "Skipping misaligned row in %s line %d (organization=%r)",
                        path.name,
                        reader.line_num,
                        (row.get("ORGANIZATION") or "").strip(),
                    )
                    continue
                logger.info(
                    "Repaired misaligned row in %s line %d (organization=%r)",
                    path.name,
                    reader.line_num,
                    (repaired.get("ORGANIZATION") or "").strip(),
                )
                row = repaired

            sort_seq = (row.get("SORT SEQUENCE") or "").strip()
            if sort_seq.upper() == "SUBTOTAL":
                continue

            desc = (row.get("DESCRIPTION") or "").strip()
            if desc.endswith("TOTALS:"):
                continue

            record = DetailRecord()
            for csv_col, field_name in column_map.items():
                raw_val = row.get(csv_col)
                if raw_val is None:
                    continue

                raw_val = raw_val.strip()

                if field_name == "amount":
                    setattr(record, field_name, _parse_amount(raw_val))
                elif field_name in DATE_FIELDS:
                    setattr(record, field_name, normalize_date(raw_val))
                else:
                    setattr(record, field_name, normalize_text(raw_val) if raw_val else None)

            if not record.organization:
                continue

            records.append(record)

    logger.info("Parsed %d detail records from %s", len(records), path.name)
    return records

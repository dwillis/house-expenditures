"""Parse House expenditure detail CSV files."""

import csv
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from house_expenditures.models import DetailRecord
from house_expenditures.parsers.normalize import normalize_date, normalize_text

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

        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return records

        # Clean up fieldnames (trailing commas produce empty fields)
        reader.fieldnames = [fn.strip() for fn in reader.fieldnames if fn.strip()]

        for row_num, row in enumerate(reader, start=2):
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

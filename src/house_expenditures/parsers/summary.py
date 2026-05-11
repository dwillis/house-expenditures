"""Parse House expenditure summary CSV files."""

import csv
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from house_expenditures.models import SummaryRecord
from house_expenditures.parsers.normalize import normalize_text

logger = logging.getLogger(__name__)


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


def parse_summary(path: Path) -> list[SummaryRecord]:
    """Parse a summary CSV file into a list of SummaryRecord objects."""
    records: list[SummaryRecord] = []

    encoding = _detect_encoding(path)
    logger.debug("Reading %s with encoding %s", path.name, encoding)

    with open(path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return records
        reader.fieldnames = [fn.strip() for fn in reader.fieldnames if fn.strip()]

        for row in reader:
            desc = (row.get("DESCRIPTION") or "").strip()
            if desc.endswith("TOTALS:"):
                continue

            record = SummaryRecord(
                organization=normalize_text(row.get("ORGANIZATION", "")),
                program=normalize_text(row.get("PROGRAM", "")),
                description=normalize_text(desc),
                ytd_amount=_parse_amount(row.get("YTD AMOUNT", "")),
                qtd_amount=_parse_amount(row.get("QTD AMOUNT", "")),
            )

            if not record.organization:
                continue

            records.append(record)

    logger.info("Parsed %d summary records from %s", len(records), path.name)
    return records

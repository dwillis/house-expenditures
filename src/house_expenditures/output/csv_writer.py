"""Write standardized CSV output files."""

import csv
import logging
from dataclasses import fields
from pathlib import Path

from house_expenditures.models import DetailRecord, StafferRecord, SummaryRecord

logger = logging.getLogger(__name__)

DETAIL_OUTPUT_COLUMNS = [
    "bioguide_id", "organization", "fiscal_year", "organization_code",
    "program", "program_code", "category", "budget_object_class",
    "sort_sequence", "transaction_date", "data_source", "document",
    "vendor_name", "vendor_id", "start_date", "end_date", "description",
    "budget_object_code", "amount", "member_name", "party", "state",
    "district", "congress", "quarter_label", "is_member",
]

SUMMARY_OUTPUT_COLUMNS = [
    "bioguide_id", "organization", "program", "description",
    "ytd_amount", "qtd_amount", "member_name", "party", "state",
    "district", "congress", "quarter_label", "is_member",
]

STAFFER_OUTPUT_COLUMNS = [
    "name", "title", "office", "bioguide_id", "party", "state",
    "district", "quarter", "start_date", "end_date", "amount",
]


def _write_records(path: Path, records: list, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {}
            for col in columns:
                val = getattr(record, col, None)
                if val is None:
                    row[col] = ""
                elif isinstance(val, bool):
                    row[col] = str(val).lower()
                else:
                    row[col] = str(val)
            writer.writerow(row)
    logger.info("Wrote %d records to %s", len(records), path)


def write_detail_csv(records: list[DetailRecord], path: Path) -> None:
    _write_records(path, records, DETAIL_OUTPUT_COLUMNS)


def write_summary_csv(records: list[SummaryRecord], path: Path) -> None:
    _write_records(path, records, SUMMARY_OUTPUT_COLUMNS)


def write_staffers_csv(records: list[StafferRecord], path: Path) -> None:
    _write_records(path, records, STAFFER_OUTPUT_COLUMNS)

"""Write standardized JSON output files."""

import json
import logging
from decimal import Decimal
from pathlib import Path

from house_expenditures.models import DetailRecord, StafferRecord, SummaryRecord
from house_expenditures.output.csv_writer import (
    DETAIL_OUTPUT_COLUMNS,
    STAFFER_OUTPUT_COLUMNS,
    SUMMARY_OUTPUT_COLUMNS,
)

logger = logging.getLogger(__name__)


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _records_to_dicts(records: list, columns: list[str]) -> list[dict]:
    result = []
    for record in records:
        row = {}
        for col in columns:
            val = getattr(record, col, None)
            if isinstance(val, Decimal):
                row[col] = float(val) if val is not None else None
            elif isinstance(val, bool):
                row[col] = val
            else:
                row[col] = val
        result.append(row)
    return result


def _write_json(path: Path, records: list, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _records_to_dicts(records, columns)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, cls=_DecimalEncoder, indent=2)
    logger.info("Wrote %d records to %s", len(records), path)


def write_detail_json(records: list[DetailRecord], path: Path) -> None:
    _write_json(path, records, DETAIL_OUTPUT_COLUMNS)


def write_summary_json(records: list[SummaryRecord], path: Path) -> None:
    _write_json(path, records, SUMMARY_OUTPUT_COLUMNS)


def write_staffers_json(records: list[StafferRecord], path: Path) -> None:
    _write_json(path, records, STAFFER_OUTPUT_COLUMNS)

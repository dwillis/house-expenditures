"""End-to-end pipeline for processing House expenditure data."""

import logging
from pathlib import Path

from house_expenditures.downloader import download_legislators, download_quarter
from house_expenditures.enrichment.congress import quarter_to_congress
from house_expenditures.enrichment.legislators import (
    LegislatorIndex,
    filter_for_congress,
    load_legislators,
)
from house_expenditures.enrichment.matcher import (
    build_org_code_map,
    enrich_detail_records,
    enrich_summary_records,
)
from house_expenditures.enrichment.staffers import extract_staffers
from house_expenditures.models import DetailRecord, Quarter, SummaryRecord
from house_expenditures.output.csv_writer import (
    write_detail_csv,
    write_staffers_csv,
    write_summary_csv,
)
from house_expenditures.output.json_writer import (
    write_detail_json,
    write_staffers_json,
    write_summary_json,
)
from house_expenditures.parsers.detail import parse_detail
from house_expenditures.parsers.normalize import strip_year_prefix
from house_expenditures.parsers.summary import parse_summary

logger = logging.getLogger(__name__)


def _congresses_from_records(
    records: list[DetailRecord] | list[SummaryRecord],
) -> set[int]:
    """Extract additional Congress numbers from year-prefixed organization names.

    Records sometimes carry a year prefix (e.g., "2022 HON. A. DONALD MCEACHIN"
    in a 2025 report) indicating they originated in an earlier Congress.
    """
    extra: set[int] = set()
    for r in records:
        if r.organization:
            year_str, _ = strip_year_prefix(r.organization)
            if year_str:
                extra.add(quarter_to_congress(int(year_str)))
    return extra


def _build_index(
    cache_dir: Path,
    congress: int,
    force: bool,
    extra_congresses: set[int] | None = None,
) -> LegislatorIndex:
    """Download legislators and build an index covering the target Congress
    plus the two adjacent ones, so leftover records from prior terms still match.

    If extra_congresses is provided (e.g. from year-prefixed org names),
    those are included too so that older records still match their legislators.
    """
    current_path, historical_path = download_legislators(cache_dir, force=force)
    all_legislators = load_legislators(current_path, historical_path)

    target_congresses = {congress, congress - 1, congress + 1}
    if extra_congresses:
        target_congresses.update(extra_congresses)

    seen_bioguides: set[str] = set()
    combined: list = []
    for c in sorted(target_congresses):
        for leg in filter_for_congress(all_legislators, c):
            if leg.bioguide_id not in seen_bioguides:
                seen_bioguides.add(leg.bioguide_id)
                combined.append(leg)

    extra_label = ""
    if extra_congresses and extra_congresses - {congress, congress - 1, congress + 1}:
        extras = sorted(extra_congresses - {congress, congress - 1, congress + 1})
        extra_label = f" + Congresses {extras}"

    logger.info(
        "Loaded %d unique House members for Congress %d (±1%s)",
        len(combined), congress, extra_label,
    )
    return LegislatorIndex(combined)


def run_pipeline(
    year: int,
    quarter: int,
    cache_dir: Path,
    output_dir: Path,
    output_format: str = "csv",
    force: bool = False,
    overrides_path: Path | None = None,
) -> None:
    """Run the full download -> parse -> enrich -> output pipeline."""
    q = Quarter(year, quarter)
    congress = quarter_to_congress(year, quarter)
    logger.info("Processing %s (Congress %d)", q.label, congress)

    # Download
    detail_path, summary_path = download_quarter(year, quarter, cache_dir, force)

    # Parse
    detail_records = parse_detail(detail_path)
    summary_records = parse_summary(summary_path)

    # Scan for year-prefixed records that need older Congresses
    extra = _congresses_from_records(detail_records) | _congresses_from_records(summary_records)

    # Enrich
    index = _build_index(cache_dir, congress, force, extra)
    detail_records = enrich_detail_records(
        detail_records, index, congress, q.label, overrides_path
    )
    org_codes = build_org_code_map(detail_records)
    summary_records = enrich_summary_records(
        summary_records, index, congress, q.label, overrides_path,
        org_code_map=org_codes,
    )

    # Output
    if output_format in ("csv", "both"):
        write_detail_csv(detail_records, output_dir / f"{q.label}-detail.csv")
        write_summary_csv(summary_records, output_dir / f"{q.label}-summary.csv")

    if output_format in ("json", "both"):
        write_detail_json(detail_records, output_dir / f"{q.label}-detail.json")
        write_summary_json(summary_records, output_dir / f"{q.label}-summary.json")

    logger.info("Finished %s", q.label)


def run_staffers_pipeline(
    year: int,
    quarter: int,
    cache_dir: Path,
    output_dir: Path,
    force: bool = False,
    overrides_path: Path | None = None,
) -> None:
    """Run pipeline focused on staffer extraction."""
    q = Quarter(year, quarter)
    congress = quarter_to_congress(year, quarter)
    logger.info("Extracting staffers for %s (Congress %d)", q.label, congress)

    # Download + parse detail
    detail_path, _ = download_quarter(year, quarter, cache_dir, force)
    detail_records = parse_detail(detail_path)

    # Scan for year-prefixed records that need older Congresses
    extra = _congresses_from_records(detail_records)

    # Enrich (need legislator matching for party assignment)
    index = _build_index(cache_dir, congress, force, extra)
    detail_records = enrich_detail_records(
        detail_records, index, congress, q.label, overrides_path
    )

    # Extract staffers
    staffer_records = extract_staffers(detail_records, congress, q.label)

    # Output
    write_staffers_csv(staffer_records, output_dir / f"{q.label}-staffers.csv")
    write_staffers_json(staffer_records, output_dir / f"{q.label}-staffers.json")

    logger.info("Finished staffers for %s", q.label)

#!/usr/bin/env python3
"""
Detect anomalous spending in House expenditure data.

Usage:
    uv run python anomaly/run_anomaly.py
    uv run python anomaly/run_anomaly.py --since 2022Q1
    uv run python anomaly/run_anomaly.py --output-dir output/ --report report.txt
"""

import argparse
import sys
import time
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from anomaly import triage, vendors
from anomaly.config import AnomalyConfig
from anomaly.detectors import category, insider, negative, timing, transactions, vendor
from anomaly.loader import load_data
from anomaly.report import build_report


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Detect anomalous spending in House expenditure output CSVs."
    )
    p.add_argument(
        "--output-dir", default="output", help="Directory containing *-detail.csv files"
    )
    p.add_argument(
        "--since", default=None, metavar="QUARTER",
        help="Only analyse quarters at or after this label, e.g. 2022Q1"
    )
    p.add_argument(
        "--report", default="anomaly_report.txt", help="Path for text report output"
    )
    p.add_argument(
        "--flagged-csv", default="anomaly_flagged.csv", help="Path for flagged findings CSV"
    )
    p.add_argument(
        "--all-offices", action="store_true",
        help="Include non-member (committee/admin) offices (default: member offices only)"
    )
    # Threshold overrides
    p.add_argument("--neg-zscore", type=float, default=3.0)
    p.add_argument("--category-zscore", type=float, default=3.0)
    p.add_argument("--large-tx-zscore", type=float, default=4.0)
    p.add_argument("--velocity-zscore", type=float, default=3.5)
    p.add_argument("--vendor-rare-count", type=int, default=2)
    p.add_argument("--vendor-concentration", type=float, default=0.70)
    p.add_argument(
        "--max-leads", type=int, default=50,
        help="Number of ranked story leads to include in the report"
    )
    p.add_argument(
        "--leads-csv", default="anomaly_leads.csv", help="Path for ranked story leads CSV"
    )
    return p.parse_args()


def _step(label: str) -> None:
    print(f"\n[{label}]")


def main() -> None:
    args = parse_args()

    config = AnomalyConfig(
        output_dir=Path(args.output_dir),
        since_quarter=args.since,
        member_only=not args.all_offices,
        report_path=Path(args.report),
        flagged_csv_path=Path(args.flagged_csv),
        neg_office_zscore=args.neg_zscore,
        category_zscore=args.category_zscore,
        large_tx_zscore=args.large_tx_zscore,
        velocity_zscore=args.velocity_zscore,
        vendor_rare_office_count=args.vendor_rare_count,
        vendor_concentration_threshold=args.vendor_concentration,
        max_leads=args.max_leads,
        leads_csv_path=Path(args.leads_csv),
    )

    t0 = time.time()

    _step("Loading data")
    detail_df, summary_df = load_data(config)

    if detail_df.empty:
        print("No detail data found — check --output-dir and --since.")
        sys.exit(1)

    # Data-driven institutional vendor set (ubiquitous vendors are not stories)
    config.institutional_vendors = vendors.institutional_vendors(detail_df)

    all_findings = []

    _step("A — Office negative AP rate (per quarter)")
    found = negative.detect_office_negative_rate(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("B — Cross-quarter negative vendor patterns")
    found = negative.detect_cross_quarter_patterns(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("C — Category spend outlier vs peers")
    found = category.detect_category_outliers(summary_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("D — Rare category dominance")
    found = category.detect_rare_category_dominance(summary_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("E — Rare vendor with significant spend")
    found = vendor.detect_rare_vendors(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("F — Vendor concentration")
    found = vendor.detect_vendor_concentration(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("G — New expensive vendor (coordinated)")
    found = vendor.detect_new_expensive_vendors(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("H — Large single transaction per category")
    found = transactions.detect_large_transactions(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("I — Round number clustering")
    found = transactions.detect_round_numbers(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("J — Wash transaction pairs")
    found = transactions.detect_wash_pairs(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("K — Transaction velocity outliers")
    found = transactions.detect_velocity_outliers(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("L — Member-name vendor matches")
    found = insider.detect_member_name_vendors(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("M — Person-shaped payees")
    found = insider.detect_person_payees(detail_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("N — Pre-election communications surge")
    found = timing.detect_election_comms_surge(summary_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("O — Departing-member spend-down")
    found = timing.detect_departing_spend_down(summary_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("P — Year-end budget exhaustion")
    found = timing.detect_year_end_exhaustion(summary_df, config)
    print(f"  {len(found)} findings")
    all_findings.extend(found)

    _step("Triaging findings into story leads")
    leads = triage.build_leads(all_findings, config)
    print(f"  {len(leads)} leads")

    _step("Writing outputs")
    build_report(all_findings, config, leads)

    elapsed = time.time() - t0
    print(f"\nDone — {len(all_findings)} findings, {len(leads)} story leads in {elapsed:.1f}s")


if __name__ == "__main__":
    main()

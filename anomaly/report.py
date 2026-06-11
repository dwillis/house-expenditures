"""Aggregate detector findings into a text report and flagged CSV."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from anomaly.config import AnomalyConfig


@dataclass
class Finding:
    detector_id: str          # e.g. "A", "E"
    detector_name: str
    severity: str             # "HIGH" | "MEDIUM" | "LOW"
    bioguide_id: str | None = None
    member_name: str | None = None
    party: str | None = None
    state: str | None = None
    district: str | None = None
    quarter: str | None = None
    description: str = ""
    amount: float | None = None
    vendor_name: str | None = None
    extra: dict = field(default_factory=dict)


def _severity(z: float | None = None, quarters: int | None = None, share: float | None = None) -> str:
    if share is not None and share > 0.90:
        return "HIGH"
    if quarters is not None:
        if quarters >= 6:
            return "HIGH"
        if quarters >= 3:
            return "MEDIUM"
        return "LOW"
    if z is not None:
        if z > 5.0:
            return "HIGH"
        if z > 3.0:
            return "MEDIUM"
    return "LOW"


def severity_from_z(z: float) -> str:
    return _severity(z=z)


def severity_from_quarters(n: int) -> str:
    return _severity(quarters=n)


def severity_from_share(share: float) -> str:
    return _severity(share=share)


def _member_label(f: Finding) -> str:
    parts = [f.member_name or f.bioguide_id or "Unknown"]
    if f.party or f.state:
        tag = "-".join(filter(None, [f.party, f.state, str(f.district) if f.district else None]))
        parts.append(f"({tag})")
    return " ".join(parts)


def build_report(findings: list[Finding], config: AnomalyConfig, leads: list | None = None) -> None:
    """Write text report, flagged CSV, and (when triaged) the leads CSV."""
    _write_text_report(findings, config, leads)
    _write_flagged_csv(findings, config)
    if leads is not None:
        _write_leads_csv(leads, config)


def _lead_lines(leads: list) -> list[str]:
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 72)
    lines.append(f"STORY LEADS — top {len(leads)} by newsworthiness score")
    lines.append("=" * 72)
    for rank, lead in enumerate(leads, 1):
        lines.append("")
        lines.append(f"#{rank} [score {lead.score:.1f}] {lead.hook}")
        for f in lead.findings:
            lines.append(f"    [{f.severity}] {f.detector_id}. {f.detector_name}"
                         + (f" — {f.quarter}" if f.quarter else ""))
            lines.append(f"      {f.description}")
    lines.append("")
    return lines


def _write_text_report(
    findings: list[Finding], config: AnomalyConfig, leads: list | None = None
) -> None:
    high = [f for f in findings if f.severity == "HIGH"]
    medium = [f for f in findings if f.severity == "MEDIUM"]
    low = [f for f in findings if f.severity == "LOW"]

    # Count by detector
    detector_counts: dict[str, dict[str, int]] = {}
    for f in findings:
        key = f"{f.detector_id}. {f.detector_name}"
        if key not in detector_counts:
            detector_counts[key] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "TOTAL": 0}
        detector_counts[key][f.severity] += 1
        detector_counts[key]["TOTAL"] += 1

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("HOUSE EXPENDITURE ANOMALY REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if config.since_quarter:
        lines.append(f"Data range: {config.since_quarter} – present")
    else:
        lines.append("Data range: all available quarters")
    lines.append("=" * 72)
    lines.append("")
    lines.append("SUMMARY")
    lines.append("-" * 72)
    lines.append(f"{'Detector':<50} {'HIGH':>5} {'MED':>5} {'LOW':>5} {'TOTAL':>7}")
    lines.append("-" * 72)
    for det, counts in sorted(detector_counts.items()):
        lines.append(
            f"{det:<50} {counts['HIGH']:>5} {counts['MEDIUM']:>5} "
            f"{counts['LOW']:>5} {counts['TOTAL']:>7}"
        )
    lines.append("-" * 72)
    lines.append(
        f"{'TOTAL':<50} {len(high):>5} {len(medium):>5} {len(low):>5} {len(findings):>7}"
    )
    lines.append("")

    if leads:
        lines.extend(_lead_lines(leads))

    # The flagged CSV holds every finding; the text listing is capped per
    # severity so the report stays scannable.
    max_listed = 200
    for severity_label, bucket in [("HIGH", high), ("MEDIUM", medium), ("LOW", low)]:
        if not bucket:
            continue
        lines.append("")
        lines.append(f"{'=' * 72}")
        listed = bucket[:max_listed]
        suffix = f", first {len(listed)} shown — full list in CSV" if len(bucket) > max_listed else ""
        lines.append(f"{severity_label} FINDINGS ({len(bucket)}{suffix})")
        lines.append("=" * 72)
        for i, f in enumerate(listed, 1):
            member = _member_label(f)
            lines.append(f"\n[{severity_label}] {f.detector_id}. {f.detector_name}"
                         + (f" — {f.quarter}" if f.quarter else ""))
            lines.append(f"  {member}" + (f", bioguide: {f.bioguide_id}" if f.bioguide_id else ""))
            lines.append(f"  {f.description}")
            if f.amount is not None:
                lines.append(f"  Amount: ${f.amount:,.2f}")
            if f.vendor_name:
                lines.append(f"  Vendor: {f.vendor_name}")
            for k, v in f.extra.items():
                lines.append(f"  {k}: {v}")

    lines.append("")
    text = "\n".join(lines)
    config.report_path.write_text(text, encoding="utf-8")
    print(f"  Text report written to {config.report_path}")


def _write_flagged_csv(findings: list[Finding], config: AnomalyConfig) -> None:
    rows = []
    for f in findings:
        row = {
            "detector_id": f.detector_id,
            "detector_name": f.detector_name,
            "severity": f.severity,
            "bioguide_id": f.bioguide_id,
            "member_name": f.member_name,
            "party": f.party,
            "state": f.state,
            "district": f.district,
            "quarter": f.quarter,
            "description": f.description,
            "amount": f.amount,
            "vendor_name": f.vendor_name,
            "extra_json": json.dumps(f.extra) if f.extra else "",
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(config.flagged_csv_path, index=False)
    print(f"  Flagged CSV written to {config.flagged_csv_path} ({len(df):,} rows)")


def _write_leads_csv(leads: list, config: AnomalyConfig) -> None:
    rows = []
    for rank, lead in enumerate(leads, 1):
        rows.append({
            "rank": rank,
            "score": lead.score,
            "bioguide_id": lead.bioguide_id,
            "member_name": lead.member_name,
            "party": lead.party,
            "state": lead.state,
            "vendor_name": lead.vendor_name,
            "amount": lead.amount,
            "quarters": ", ".join(lead.quarters),
            "detectors": ", ".join(sorted(lead.detectors)),
            "n_findings": len(lead.findings),
            "hook": lead.hook,
        })
    df = pd.DataFrame(rows)
    df.to_csv(config.leads_csv_path, index=False)
    print(f"  Leads CSV written to {config.leads_csv_path} ({len(df):,} rows)")

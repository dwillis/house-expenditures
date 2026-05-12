#!/usr/bin/env python3
"""Generate output/files.json manifest for the GitHub Pages site."""

import json
import re
from pathlib import Path

OUTPUT_DIR = Path("output")
MANIFEST_PATH = OUTPUT_DIR / "files.json"

# Quarter label -> Congress number
def _quarter_to_congress(year: int) -> int:
    return ((year - 1789) // 2) + 1


def build_manifest() -> None:
    if not OUTPUT_DIR.exists():
        print("No output/ directory found. Run the pipeline first.")
        return

    csv_files = sorted(OUTPUT_DIR.glob("*.csv"))
    if not csv_files:
        print("No CSV files found in output/.")
        return

    # Group by quarter label (e.g., "2024Q3")
    quarters: dict[str, dict] = {}

    for path in csv_files:
        match = re.match(r"^(\d{4})Q(\d)-(detail|summary)\.csv$", path.name)
        if not match:
            continue

        year, qtr, file_type = int(match.group(1)), int(match.group(2)), match.group(3)
        label = f"{year}Q{qtr}"
        size_bytes = path.stat().st_size

        if label not in quarters:
            quarters[label] = {
                "year": year,
                "quarter": qtr,
                "congress": _quarter_to_congress(year),
            }

        quarters[label][file_type] = {
            "filename": path.name,
            "size_bytes": size_bytes,
        }

    # Sort by year descending, then quarter descending (newest first)
    manifest = sorted(
        quarters.values(),
        key=lambda q: (q["year"], q["quarter"]),
        reverse=True,
    )

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(manifest)} quarters to {MANIFEST_PATH}")


if __name__ == "__main__":
    build_manifest()

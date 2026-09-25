import json
import re
from pathlib import Path

import build_site

REPO_DIR = Path(__file__).parent.parent
OUTPUT_DIR = REPO_DIR / "output"
QUARTER_RE = re.compile(r"^(\d{4})Q(\d)-(detail|summary)\.csv$")


def _quarters_on_disk(output_dir: Path) -> set[tuple[int, int]]:
    quarters = set()
    for path in output_dir.glob("*.csv"):
        match = QUARTER_RE.match(path.name)
        if match:
            quarters.add((int(match.group(1)), int(match.group(2))))
    return quarters


def test_manifest_includes_all_quarters_on_disk():
    """CSVs added to output/ must appear in files.json or the site won't list them.

    Guards against adding a quarter's CSVs without rerunning build_site.py.
    """
    manifest = json.loads((OUTPUT_DIR / "files.json").read_text())
    in_manifest = {(q["year"], q["quarter"]) for q in manifest}
    missing = _quarters_on_disk(OUTPUT_DIR) - in_manifest
    assert not missing, (
        f"output/ contains CSVs missing from files.json (rerun build_site.py): {sorted(missing)}"
    )


def test_build_manifest_generates_newest_first(tmp_path, monkeypatch):
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    (out_dir / "2026Q1-detail.csv").write_text("x")
    (out_dir / "2026Q1-summary.csv").write_text("x")
    (out_dir / "2026Q2-detail.csv").write_text("x")
    (out_dir / "2026Q2-summary.csv").write_text("x")
    manifest_path = out_dir / "files.json"
    monkeypatch.setattr(build_site, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(build_site, "MANIFEST_PATH", manifest_path)

    build_site.build_manifest()

    manifest = json.loads(manifest_path.read_text())
    assert [(q["year"], q["quarter"]) for q in manifest] == [(2026, 2), (2026, 1)]
    newest = manifest[0]
    assert newest["congress"] == 119
    assert newest["detail"]["filename"] == "2026Q2-detail.csv"
    assert newest["summary"]["filename"] == "2026Q2-summary.csv"
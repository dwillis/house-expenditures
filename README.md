# house-expenditures

A Python CLI tool that downloads, parses, enriches, and standardizes [U.S. House of Representatives Statement of Disbursements](https://www.house.gov/the-house-explained/open-government/statement-of-disbursements) data, producing clean CSV and JSON files.

Inspired by the [ProPublica disbursements](https://github.com/propublica/disbursements) Ruby pipeline, rebuilt in Python with modern data sources and improved legislator matching.

## What it does

- Downloads quarterly detail and summary CSV files from house.gov (Q1 2016 onward)
- Parses both the 12-column (2016-2022) and 18-column (2023+) detail formats
- Matches member offices to legislators using [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators), adding bioguide IDs, party, state, and district
- Extracts staffers from personnel compensation records with partisan classification (R/D/None)
- Outputs standardized, enriched CSV and JSON files

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/your-org/house-expenditures.git
cd house-expenditures
uv sync
```

## Usage

### Process a single quarter

```bash
uv run house-expenditures process --year 2024 --quarter 4 --format csv
```

This downloads the source data, parses it, matches legislators, and writes enriched output to `output/`.

### Process all available quarters

```bash
uv run house-expenditures process --all --format both
```

### Download without processing

```bash
uv run house-expenditures download --year 2024 --quarter 4
```

### Extract staffers

```bash
uv run house-expenditures staffers --year 2024 --quarter 4
```

### List available quarters

```bash
uv run house-expenditures list-quarters
```

### Options

| Option | Description |
|---|---|
| `--year` / `--quarter` | Specify a single quarter |
| `--all` | Process all available quarters (Q1 2016 - present) |
| `--format csv\|json\|both` | Output format (default: csv) |
| `--force` | Re-download even if cached |
| `--overrides PATH` | JSON file mapping member names to bioguide IDs |
| `--output-dir PATH` | Output directory (default: `output/`) |
| `--cache-dir PATH` | Cache directory (default: `~/.house-expenditures/cache/`) |
| `-v` / `--verbose` | Enable debug logging |

## Output files

### Enriched detail CSV

One file per quarter (e.g., `2024Q4-detail.csv`) with columns:

`bioguide_id`, `organization`, `fiscal_year`, `organization_code`, `program`, `program_code`, `category`, `budget_object_class`, `sort_sequence`, `transaction_date`, `data_source`, `document`, `vendor_name`, `vendor_id`, `start_date`, `end_date`, `description`, `budget_object_code`, `amount`, `member_name`, `party`, `state`, `district`, `congress`, `quarter_label`, `is_member`

### Enriched summary CSV

One file per quarter (e.g., `2024Q4-summary.csv`) with columns:

`bioguide_id`, `organization`, `program`, `description`, `ytd_amount`, `qtd_amount`, `member_name`, `party`, `state`, `district`, `congress`, `quarter_label`, `is_member`

### Staffers CSV

One file per quarter (e.g., `2024Q4-staffers.csv`) with columns:

`name`, `title`, `office`, `bioguide_id`, `party`, `state`, `district`, `quarter`, `start_date`, `end_date`, `amount`

## Legislator matching

Member offices (those starting with "HON.") are matched to legislators from the [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators) YAML files using a multi-step approach:

1. Exact match on official full name
2. First + last name match within the relevant Congress
3. Nickname matching (e.g., "Buddy" Carter)
4. Last name with state disambiguation (e.g., Mike Rogers AL vs MI)
5. Compound/hyphenated last name handling (e.g., Wasserman Schultz, González-Colón)
6. Quoted nickname extraction (e.g., Jesús G. "Chuy" García)
7. Accent and apostrophe normalization (e.g., Barragán, O'Halleran)

For edge cases not handled by the algorithmic matcher, supply a JSON overrides file:

```json
{
  "SOME UNUSUAL NAME": "B000123"
}
```

```bash
uv run house-expenditures process --year 2024 --quarter 4 --overrides overrides.json
```

## Partisan classification

Staffers are assigned a party based on their office:

| Office type | Classification |
|---|---|
| Member office (HON.) | Member's party from congress-legislators |
| Speaker / Majority Leader / Majority Whip | Majority party for that Congress |
| Minority Leader / Minority Whip | Minority party for that Congress |
| Republican Conference | R |
| Democratic Caucus | D |
| Committees, Clerk, CAO, etc. | None |

## Data source

The House publishes quarterly CSV files at [house.gov](https://www.house.gov/the-house-explained/open-government/statement-of-disbursements). CSV data is available from Q1 2016 onward. The tool includes a hardcoded registry of all known download URLs (which are inconsistently formatted) with a scraper fallback for new quarters.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src/ tests/
```

## License

Public domain (CC0).

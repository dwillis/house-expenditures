import logging
from pathlib import Path

import click

from house_expenditures.config import DEFAULT_CACHE_DIR, DEFAULT_OUTPUT_DIR


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_CACHE_DIR,
    show_default=True,
    help="Directory for cached downloads.",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUTPUT_DIR,
    show_default=True,
    help="Directory for output files.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, cache_dir: Path, output_dir: Path) -> None:
    """Parse, enrich, and standardize U.S. House Office Expenditure data.

    Downloads quarterly Statement of Disbursements CSV files from house.gov,
    matches member offices to legislators using congress-legislators data,
    and produces enriched CSV/JSON output with bioguide IDs, party, state,
    and district. Also extracts staffers with partisan classification.

    Data is available from Q1 2016 through the most recent published quarter.

    \b
    Examples:
      house-expenditures process --year 2024 --quarter 4
      house-expenditures process --all --format both
      house-expenditures staffers --year 2024 --quarter 4
      house-expenditures list-quarters
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["cache_dir"] = cache_dir
    ctx.obj["output_dir"] = output_dir


@cli.command()
@click.option("--year", type=int, required=False, help="Year to download (e.g. 2024).")
@click.option("--quarter", type=int, required=False, help="Quarter to download (1-4).")
@click.option("--all", "all_quarters", is_flag=True, help="Download all available quarters.")
@click.option("--force", is_flag=True, help="Re-download even if files are cached.")
@click.pass_context
def download(ctx: click.Context, year: int | None, quarter: int | None, all_quarters: bool, force: bool) -> None:
    """Download raw expenditure CSV files from house.gov.

    Downloads both the detail and summary CSV files for the specified
    quarter(s) and caches them locally. Use --force to re-download
    files that are already cached.

    \b
    Examples:
      house-expenditures download --year 2024 --quarter 4
      house-expenditures download --all
      house-expenditures download --all --force
    """
    from house_expenditures.downloader import download_quarter, download_all_quarters

    cache_dir = ctx.obj["cache_dir"]
    if all_quarters:
        download_all_quarters(cache_dir, force=force)
    elif year and quarter:
        download_quarter(year, quarter, cache_dir, force=force)
    else:
        raise click.UsageError("Provide --year and --quarter, or use --all.")


@cli.command()
@click.option("--year", type=int, required=False, help="Year to process (e.g. 2024).")
@click.option("--quarter", type=int, required=False, help="Quarter to process (1-4).")
@click.option("--all", "all_quarters", is_flag=True, help="Process all available quarters.")
@click.option("--force", is_flag=True, help="Re-download source files even if cached.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "json", "both"]),
    default="csv",
    show_default=True,
    help="Output format for enriched data.",
)
@click.option(
    "--overrides",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file mapping member names to bioguide IDs for manual overrides.",
)
@click.pass_context
def process(
    ctx: click.Context,
    year: int | None,
    quarter: int | None,
    all_quarters: bool,
    force: bool,
    output_format: str,
    overrides: Path | None,
) -> None:
    """Run the full pipeline: download, parse, enrich, and output.

    Downloads detail and summary CSVs from house.gov, parses them,
    matches member offices to legislators (adding bioguide ID, party,
    state, district), and writes enriched CSV/JSON files to the
    output directory.

    Outputs per quarter: detail CSV/JSON and summary CSV/JSON.

    \b
    Examples:
      house-expenditures process --year 2024 --quarter 4
      house-expenditures process --year 2024 --quarter 4 --format both
      house-expenditures process --all --format json
      house-expenditures process --year 2024 --quarter 4 --overrides fixes.json
    """
    from house_expenditures.pipeline import run_pipeline

    cache_dir = ctx.obj["cache_dir"]
    output_dir = ctx.obj["output_dir"]

    if all_quarters:
        from house_expenditures.url_index import get_available_quarters

        for q_year, q_num in get_available_quarters():
            run_pipeline(q_year, q_num, cache_dir, output_dir, output_format, force, overrides)
    elif year and quarter:
        run_pipeline(year, quarter, cache_dir, output_dir, output_format, force, overrides)
    else:
        raise click.UsageError("Provide --year and --quarter, or use --all.")


@cli.command()
@click.option("--year", type=int, required=False, help="Year to extract (e.g. 2024).")
@click.option("--quarter", type=int, required=False, help="Quarter to extract (1-4).")
@click.option("--all", "all_quarters", is_flag=True, help="Extract staffers for all available quarters.")
@click.option("--force", is_flag=True, help="Re-download source files even if cached.")
@click.option(
    "--overrides",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file mapping member names to bioguide IDs for manual overrides.",
)
@click.pass_context
def staffers(
    ctx: click.Context,
    year: int | None,
    quarter: int | None,
    all_quarters: bool,
    force: bool,
    overrides: Path | None,
) -> None:
    """Extract House staffers with partisan classification.

    Filters detail records for personnel compensation, identifies each
    staffer's name and title, and classifies their party affiliation
    based on the office they work for:

    \b
      - Member offices: inherit the member's party (R or D)
      - Leadership offices: majority or minority party for that Congress
      - Party organizations: R or D directly
      - Committees and administrative offices: None

    Outputs both CSV and JSON staffer files per quarter.

    \b
    Examples:
      house-expenditures staffers --year 2024 --quarter 4
      house-expenditures staffers --all
    """
    from house_expenditures.pipeline import run_staffers_pipeline

    cache_dir = ctx.obj["cache_dir"]
    output_dir = ctx.obj["output_dir"]

    if all_quarters:
        from house_expenditures.url_index import get_available_quarters

        for q_year, q_num in get_available_quarters():
            run_staffers_pipeline(q_year, q_num, cache_dir, output_dir, force, overrides)
    elif year and quarter:
        run_staffers_pipeline(year, quarter, cache_dir, output_dir, force, overrides)
    else:
        raise click.UsageError("Provide --year and --quarter, or use --all.")


@cli.command("list-quarters")
def list_quarters() -> None:
    """List all quarters with available data.

    Shows every quarter from Q1 2016 through the most recent published
    quarter. These are the valid values for --year and --quarter in
    other commands.
    """
    from house_expenditures.url_index import get_available_quarters

    quarters = get_available_quarters()
    for q_year, q_num in quarters:
        click.echo(f"{q_year} Q{q_num}")

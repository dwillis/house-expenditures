"""Download House expenditure CSVs and congress-legislators YAML."""

import logging
import time
from pathlib import Path

import requests

from house_expenditures.config import (
    DEFAULT_CACHE_DIR,
    LEGISLATORS_BASE_URL,
    LEGISLATORS_CACHE_TTL_DAYS,
    USER_AGENT,
)
from house_expenditures.url_index import get_available_quarters, get_url

logger = logging.getLogger(__name__)


def _download_file(
    url: str, dest: Path, force: bool = False, max_retries: int = 3
) -> Path:
    """Download a file with retries and caching."""
    if dest.exists() and not force:
        logger.debug("Using cached %s", dest)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=120, stream=True)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info("Downloaded %s", dest.name)
            return dest
        except requests.RequestException as e:
            if attempt == max_retries:
                raise RuntimeError(f"Failed to download {url} after {max_retries} attempts: {e}") from e
            wait = 2 ** attempt
            logger.warning("Download attempt %d failed (%s), retrying in %ds...", attempt, e, wait)
            time.sleep(wait)

    return dest  # unreachable, but satisfies type checker


def download_quarter(
    year: int, quarter: int, cache_dir: Path = DEFAULT_CACHE_DIR, force: bool = False
) -> tuple[Path, Path]:
    """Download detail and summary CSVs for a quarter. Returns (detail_path, summary_path)."""
    detail_url = get_url(year, quarter, "detail")
    summary_url = get_url(year, quarter, "summary")

    detail_path = cache_dir / f"{year}-Q{quarter}-detail.csv"
    summary_path = cache_dir / f"{year}-Q{quarter}-summary.csv"

    _download_file(detail_url, detail_path, force=force)
    _download_file(summary_url, summary_path, force=force)

    return detail_path, summary_path


def download_all_quarters(
    cache_dir: Path = DEFAULT_CACHE_DIR, force: bool = False
) -> list[tuple[int, int, Path, Path]]:
    """Download all available quarters. Returns list of (year, quarter, detail, summary)."""
    results = []
    for year, quarter in get_available_quarters():
        try:
            detail, summary = download_quarter(year, quarter, cache_dir, force)
            results.append((year, quarter, detail, summary))
        except Exception as e:
            logger.error("Failed to download %d Q%d: %s", year, quarter, e)
    return results


def download_legislators(
    cache_dir: Path = DEFAULT_CACHE_DIR, force: bool = False
) -> tuple[Path, Path]:
    """Download legislators-current.yaml and legislators-historical.yaml."""
    current_path = cache_dir / "legislators-current.yaml"
    historical_path = cache_dir / "legislators-historical.yaml"

    for name, path in [
        ("legislators-current.yaml", current_path),
        ("legislators-historical.yaml", historical_path),
    ]:
        if not force and path.exists():
            age_days = (time.time() - path.stat().st_mtime) / 86400
            if age_days < LEGISLATORS_CACHE_TTL_DAYS:
                logger.debug("Using cached %s (%.1f days old)", name, age_days)
                continue

        url = f"{LEGISLATORS_BASE_URL}/{name}"
        _download_file(url, path, force=True)

    return current_path, historical_path

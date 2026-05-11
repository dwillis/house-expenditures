"""Registry of known House expenditure CSV URLs and scraper fallback."""

import logging
import re
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from house_expenditures.config import (
    ARCHIVE_PAGE_URL,
    HOUSE_GOV_BASE,
    MAIN_PAGE_URL,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

# Mapping of (year, quarter, file_type) -> relative URL path
# file_type is "detail" or "summary"
# Scraped from house.gov main + archive pages (verified May 2025)
KNOWN_URLS: dict[tuple[int, int, str], str] = {
    # 2016
    (2016, 1, "detail"): "/sites/default/files/uploads/documents/JAN-MAR-2016-SOD-DETAIL-GRID_REVISED_9_26_16.csv",
    (2016, 1, "summary"): "/sites/default/files/uploads/documents/JAN-MAR-2016-SOD-SUMM-GRID.csv",
    (2016, 2, "detail"): "/sites/default/files/uploads/documents/APR-JUNE-2016-SOD-DETAIL-GRID-REVISE-9_26_16.csv",
    (2016, 2, "summary"): "/sites/default/files/uploads/documents/APR-JUNE-2016-SOD-SUMM-GRID.CSV",
    (2016, 3, "detail"): "/sites/default/files/uploads/documents/JULY-SEPT-2016-SOD-DETAIL-GRID.csv",
    (2016, 3, "summary"): "/sites/default/files/uploads/documents/JULY-SEPT-2016-SOD-SUMM-GRID.csv",
    (2016, 4, "detail"): "/sites/default/files/uploads/documents/OCT-DEC%202016%20DETAIL%20GRID.csv",
    (2016, 4, "summary"): "/sites/default/files/uploads/documents/OCT-DEC%202016%20SUMM%20GRID.csv",
    # 2017
    (2017, 1, "detail"): "/sites/default/files/uploads/documents/SODs/JAN-MAR%202017%20DETAIL%20GRID.csv",
    (2017, 1, "summary"): "/sites/default/files/uploads/documents/SODs/JAN-MAR%202017%20SUMM%20GRID.csv",
    (2017, 2, "detail"): "/sites/default/files/uploads/documents/APR-JUN%202017%20DETAIL%20GRID.csv",
    (2017, 2, "summary"): "/sites/default/files/uploads/documents/APR-JUN%202017%20SUMMARY%20GRID.csv",
    (2017, 3, "detail"): "/sites/default/files/uploads/documents/SODs/JUL-SEPT%202017%20SOD%20DETAIL%20GRID.csv",
    (2017, 3, "summary"): "/sites/default/files/uploads/documents/SODs/JUL-SEPT%202017%20SOD%20SUMMARY%20GRID.csv",
    (2017, 4, "detail"): "/sites/default/files/uploads/documents/SODs/OCT-DEC%202017%20SOD%20DETAIL%20GRID.csv",
    (2017, 4, "summary"): "/sites/default/files/uploads/documents/SODs/OCT-DEC%202017%20SOD%20SUMMARY%20GRID.csv",
    # 2018
    (2018, 1, "detail"): "/sites/default/files/uploads/documents/JAN-MAR%202018%20SOD%20DETAIL%20GRID.csv",
    (2018, 1, "summary"): "/sites/default/files/uploads/documents/JAN-MAR%202018%20SOD%20SUMMARY%20GRID.csv",
    (2018, 2, "detail"): "/sites/default/files/uploads/documents/SODs/APR-JUNE-2018-SOD-DETAIL-GRID.csv",
    (2018, 2, "summary"): "/sites/default/files/uploads/documents/SODs/APR-JUNE-2018-SOD-SUMMARY-GRID.csv",
    (2018, 3, "detail"): "/sites/default/files/uploads/documents/SODs/JULY-SEPTEMBER%202018%20SOD%20DETAIL%20GRID.csv",
    (2018, 3, "summary"): "/sites/default/files/uploads/documents/SODs/JULY-SEPTEMBER%202018%20SOD%20SUMMARY%20GRID.csv",
    (2018, 4, "detail"): "/sites/default/files/uploads/documents/SODs/OCT-DEC%202018%20SOD%20DETAIL%20GRID.csv",
    (2018, 4, "summary"): "/sites/default/files/uploads/documents/SODs/OCT-DEC%202018%20SOD%20SUMMARY%20GRID.csv",
    # 2019
    (2019, 1, "detail"): "/sites/default/files/uploads/documents/SODs/JAN-MAR%202019%20SOD%20DETAIL%20GRID.CSV",
    (2019, 1, "summary"): "/sites/default/files/uploads/documents/SODs/JAN-MAR%202019%20SOD%20SUMMARY%20GRID.CSV",
    (2019, 2, "detail"): "/sites/default/files/uploads/documents/SODs/APR-JUN%202019%20SOD%20DETAIL%20GRID.csv",
    (2019, 2, "summary"): "/sites/default/files/uploads/documents/SODs/APR-JUN%202019%20SOD%20SUMMARY%20GRID.csv",
    (2019, 3, "detail"): "/sites/default/files/uploads/documents/SODs/JUL-SEPT%202019%20SOD%20DETAIL%20GRID.csv",
    (2019, 3, "summary"): "/sites/default/files/uploads/documents/SODs/JUL-SEPT%202019%20SOD%20SUMMARY%20GRID.csv",
    (2019, 4, "detail"): "/sites/default/files/uploads/documents/SODs/OCT-DEC-2019-SOD-DETAIL-GRID.csv",
    (2019, 4, "summary"): "/sites/default/files/uploads/documents/SODs/OCT-DEC-2019-SOD-SUMMARY-GRID.csv",
    # 2020
    (2020, 1, "detail"): "/sites/default/files/uploads/documents/SODs/JAN-MAR-2020-SOD-DETAIL-GRID_FINAL.csv",
    (2020, 1, "summary"): "/sites/default/files/uploads/documents/SODs/JAN-MAR-2020-SOD-SUMMARY-GRID_FINAL.csv",
    (2020, 2, "detail"): "/sites/default/files/uploads/documents/SODs/APR-JUN-2020-SOD-DETAIL-GRID_FINAL.csv",
    (2020, 2, "summary"): "/sites/default/files/uploads/documents/SODs/APR-JUN-2020-SOD-SUMMARY-GRID_FINAL.csv",
    (2020, 3, "detail"): "/sites/default/files/uploads/documents/SODs/2020q3/JULY-SEPT-2020-SOD-DETAIL-GRID-FINAL.csv",
    (2020, 3, "summary"): "/sites/default/files/uploads/documents/SODs/2020q3/JULY-SEPT-2020-SOD-SUMM-GRID-FINAL.csv",
    (2020, 4, "detail"): "/sites/default/files/uploads/documents/SODs/2020q4/OCT-DEC%202020%20SOD%20DETAIL%20GRID_FINAL.csv",
    (2020, 4, "summary"): "/sites/default/files/uploads/documents/SODs/2020q4/OCT-DEC%202020%20SOD%20SUMM%20GRID_FINAL.csv",
    # 2021
    (2021, 1, "detail"): "/sites/default/files/uploads/documents/SODs/2021q1/JAN_MAR_2021_SOD_DETAIL_GRID_FINAL.csv",
    (2021, 1, "summary"): "/sites/default/files/uploads/documents/SODs/2021q1/JAN_MAR_2021_SOD_SUMM_GRID_FINAL.csv",
    (2021, 2, "detail"): "/sites/default/files/uploads/documents/SODs/2021q2/APR-JUN%202021%20SOD%20DETAIL%20GRID_FINAL.csv",
    (2021, 2, "summary"): "/sites/default/files/uploads/documents/SODs/2021q2/APR-JUN%202021%20SOD%20SUMM%20GRID_FINAL.csv",
    (2021, 3, "detail"): "/sites/default/files/uploads/documents/SODs/2021q3/JULY-2021-SOD-DETAIL-GRID-FINAL.csv",
    (2021, 3, "summary"): "/sites/default/files/uploads/documents/SODs/2021q3/JULY-SEPT-2021-SOD-SUMM-GRID-FINAL.csv",
    (2021, 4, "detail"): "/sites/default/files/uploads/documents/SODs/2021q4/OCT-DEC-2021-SOD-DETAIL-GRID-FINAL.csv",
    (2021, 4, "summary"): "/sites/default/files/uploads/documents/SODs/2021q4/OCT-DEC-2021-SOD-SUMM-GRID-FINAL.csv",
    # 2022
    (2022, 1, "detail"): "/sites/default/files/2022-05/JAN-MAR-2022-SOD-DETAIL-GRID-FINAL.csv",
    (2022, 1, "summary"): "/sites/default/files/2022-05/JAN-MAR-2022-SOD-SUMM-GRID-FINAL.csv",
    (2022, 2, "detail"): "/sites/default/files/2022-08/APR-JUNE-2022-SOD-DETAIL-GRID-FINAL.csv",
    (2022, 2, "summary"): "/sites/default/files/2022-08/APR-JUNE-2022-SOD-SUMMARY-GRID-FINAL.csv",
    (2022, 3, "detail"): "/sites/default/files/2022-11/JULY-SEPT-2022-SOD-DETAIL-GRID-FINAL.csv",
    (2022, 3, "summary"): "/sites/default/files/2022-11/JULY-SEPT-2022-SOD-SUMMARY-GRID-FINAL.csv",
    (2022, 4, "detail"): "/sites/default/files/2023-02/OCT-DEC-2022-SOD-DETAIL-GRID-FINAL.csv",
    (2022, 4, "summary"): "/sites/default/files/2023-02/OCT-DEC-2022-SOD-SUMMARY-GRID-FINAL.csv",
    # 2023
    (2023, 1, "detail"): "/sites/default/files/2023-05/JAN-MAR-2023-SOD-DETAIL-GRID-FINAL.csv",
    (2023, 1, "summary"): "/sites/default/files/2023-05/JAN-MAR-2023-SOD-SUMMARY-GRID-FINAL.csv",
    (2023, 2, "detail"): "/sites/default/files/2023-08/APRIL-JUNE%202023%20SOD%20DETAIL%20GRID-FINAL.csv",
    (2023, 2, "summary"): "/sites/default/files/2023-08/APRIL-JUNE-2023-SOD-SUMMARY-GRID-FINAL.csv",
    (2023, 3, "detail"): "/sites/default/files/2023-11/JULY-SEPTEMBER-2023-SOD-DETAIL-GRID-FINAL.csv",
    (2023, 3, "summary"): "/sites/default/files/2023-11/JULY-SEPTEMBER-SOD-SUMMARY-GRID-FINAL.csv",
    (2023, 4, "detail"): "/sites/default/files/2024-02/OCT-DEC-2023-SOD-DETAIL-GRID-FINAL.csv",
    (2023, 4, "summary"): "/sites/default/files/2024-02/OCT-DEC-2023-SOD-SUMMARY-GRID-FINAL.csv",
    # 2024
    (2024, 1, "detail"): "/sites/default/files/2024-05/JAN-MAR-2024-SOD-DETAIL-GRID-FINAL.csv",
    (2024, 1, "summary"): "/sites/default/files/2024-05/JAN-MAR-2024-SOD-SUMMARY-GRID-FINAL.csv",
    (2024, 2, "detail"): "/sites/default/files/2024-08/APRIL-JUNE-2024-SOD-DETAIL-GRID-FINAL.csv",
    (2024, 2, "summary"): "/sites/default/files/2024-08/APRIL-JUNE-2024-SOD-SUMMARY-GRID-FINAL.csv",
    (2024, 3, "detail"): "/sites/default/files/2024-11/JULY-SEPTEMBER_2024_SOD_DETAIL_GRID-FINAL.csv",
    (2024, 3, "summary"): "/sites/default/files/2024-11/JULY-SEPTEMBER_2024_SOD_SUMMARY_GRID-FINAL.csv",
    (2024, 4, "detail"): "/sites/default/files/2025-02/OCTOBER-DECEMBER-2024-SOD-DETAIL-GRID-FINAL.csv",
    (2024, 4, "summary"): "/sites/default/files/2025-02/OCTOBER-DECEMBER-2024-SOD-SUMMARY-GRID-FINAL.csv",
    # 2025
    (2025, 1, "detail"): "/sites/default/files/2025-05/JANUARY-MARCH-2025-SOD-DETAIL-GRID-FINAL.csv",
    (2025, 1, "summary"): "/sites/default/files/2025-05/JANUARY-MARCH-2025-SOD-SUMMARY-GRID-FINAL.csv",
    (2025, 2, "detail"): "/sites/default/files/2025-08/APRIL-JUNE%202025%20SOD%20DETAIL%20GRID-FINAL.csv",
    (2025, 2, "summary"): "/sites/default/files/2025-08/APRIL-JUNE%202025%20SOD%20SUMMARY%20GRID-FINAL.csv",
    (2025, 3, "detail"): "/sites/default/files/2025-11/grids/JULY-SEPTEMBER%202025%20SOD%20DETAIL%20GRID-FINAL.csv",
    (2025, 3, "summary"): "/sites/default/files/2025-11/grids/JULY-SEPTEMBER%202025%20SOD%20SUMMARY%20GRID-FINAL.csv",
    (2025, 4, "detail"): "/sites/default/files/2026-02/OCT-DEC-2025-SOD-DETAIL-GRID-FINAL.csv",
    (2025, 4, "summary"): "/sites/default/files/2026-02/OCT-DEC-2025-SOD-SUMMARY-GRID-FINAL.csv",
}


def _classify_url(href: str) -> tuple[int, int, str] | None:
    """Extract (year, quarter, file_type) from a CSV URL path."""
    decoded = unquote(href).upper()
    filename = decoded.split("/")[-1]

    year_match = re.search(r"(\d{4})", filename)
    if not year_match:
        return None
    year = int(year_match.group(1))

    if "DETAIL" in filename:
        file_type = "detail"
    elif "SUMM" in filename or "SUMMARY" in filename:
        file_type = "summary"
    else:
        return None

    if any(m in filename for m in ["JAN", "JANUARY"]):
        quarter = 1
    elif any(m in filename for m in ["APR", "APRIL"]):
        quarter = 2
    elif any(m in filename for m in ["JUL", "JULY"]):
        quarter = 3
    elif any(m in filename for m in ["OCT", "OCTOBER"]):
        quarter = 4
    else:
        return None

    return (year, quarter, file_type)


def scrape_urls() -> dict[tuple[int, int, str], str]:
    """Scrape CSV URLs from house.gov main and archive pages."""
    urls: dict[tuple[int, int, str], str] = {}
    for page_url in [MAIN_PAGE_URL, ARCHIVE_PAGE_URL]:
        try:
            resp = requests.get(
                page_url, headers={"User-Agent": USER_AGENT}, timeout=30
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Failed to scrape %s: %s", page_url, e)
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not re.search(r"\.[cC][sS][vV]$", href):
                continue
            key = _classify_url(href)
            if key:
                urls[key] = href

    return urls


def get_url(year: int, quarter: int, file_type: str) -> str:
    """Get the full URL for a given quarter's CSV file."""
    key = (year, quarter, file_type)
    if key in KNOWN_URLS:
        return HOUSE_GOV_BASE + KNOWN_URLS[key]

    logger.info("URL not in registry for %s, scraping house.gov...", key)
    scraped = scrape_urls()
    if key in scraped:
        return HOUSE_GOV_BASE + scraped[key]

    raise ValueError(
        f"No URL found for {year} Q{quarter} {file_type}. "
        "The file may not be published yet."
    )


def get_available_quarters() -> list[tuple[int, int]]:
    """Return sorted list of (year, quarter) tuples with known data."""
    seen: set[tuple[int, int]] = set()
    for year, quarter, _ in KNOWN_URLS:
        seen.add((year, quarter))
    return sorted(seen)

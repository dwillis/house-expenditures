"""Load and index congress-legislators data."""

import logging
from datetime import date
from pathlib import Path

import yaml

from house_expenditures.models import Legislator
from house_expenditures.parsers.normalize import normalize_for_matching

logger = logging.getLogger(__name__)


def _parse_date(d: str) -> date:
    return date.fromisoformat(d)


def load_legislators(current_path: Path, historical_path: Path) -> list[Legislator]:
    """Load all legislators from YAML files, extracting House terms."""
    all_legislators: list[Legislator] = []
    seen: set[tuple[str, str, str]] = set()  # (bioguide, term_start, term_end)

    paths = [historical_path, current_path]
    if current_path == historical_path:
        paths = [current_path]

    for path in paths:
        if not path.exists():
            logger.warning("Legislators file not found: %s", path)
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            continue

        for entry in data:
            ids = entry.get("id", {})
            bioguide = ids.get("bioguide", "")
            if not bioguide:
                continue

            name = entry.get("name", {})
            first = name.get("first", "")
            last = name.get("last", "")
            official_full = name.get("official_full")
            nickname = name.get("nickname")
            suffix = name.get("suffix")
            middle = name.get("middle")

            for term in entry.get("terms", []):
                if term.get("type") != "rep":
                    continue

                key = (bioguide, term.get("start", ""), term.get("end", ""))
                if key in seen:
                    continue
                seen.add(key)

                leg = Legislator(
                    bioguide_id=bioguide,
                    first_name=first,
                    last_name=last,
                    official_full=official_full,
                    nickname=nickname,
                    suffix=suffix,
                    middle=middle,
                    party=term.get("party", ""),
                    state=term.get("state", ""),
                    district=term.get("district"),
                    chamber="rep",
                    term_start=term.get("start", ""),
                    term_end=term.get("end", ""),
                )
                all_legislators.append(leg)

    logger.info("Loaded %d House term records", len(all_legislators))
    return all_legislators


def _congress_dates(congress: int) -> tuple[date, date]:
    """Return the (start, end) dates for a Congress."""
    start_year = 1789 + (congress - 1) * 2
    start = date(start_year, 1, 3)
    end = date(start_year + 2, 1, 3)
    return start, end


def filter_for_congress(
    legislators: list[Legislator], congress: int
) -> list[Legislator]:
    """Filter legislators to those serving during a given Congress."""
    congress_start, congress_end = _congress_dates(congress)
    result = []
    for leg in legislators:
        try:
            term_start = _parse_date(leg.term_start)
            term_end = _parse_date(leg.term_end)
        except (ValueError, TypeError):
            continue
        if term_start < congress_end and term_end > congress_start:
            result.append(leg)
    return result


class LegislatorIndex:
    """Pre-built lookup indices for fast legislator matching."""

    def __init__(self, legislators: list[Legislator]) -> None:
        self.by_bioguide: dict[str, Legislator] = {}
        self.by_full_name: dict[str, list[Legislator]] = {}
        self.by_last_name: dict[str, list[Legislator]] = {}
        self.by_first_last: dict[tuple[str, str], list[Legislator]] = {}
        self.by_state_last: dict[tuple[str, str], list[Legislator]] = {}
        self.by_nickname_last: dict[tuple[str, str], list[Legislator]] = {}

        for leg in legislators:
            self.by_bioguide[leg.bioguide_id] = leg

            if leg.official_full:
                key = normalize_for_matching(leg.official_full).upper().strip()
                self.by_full_name.setdefault(key, []).append(leg)

            last_upper = normalize_for_matching(leg.last_name).upper().strip()
            self.by_last_name.setdefault(last_upper, []).append(leg)

            first_upper = normalize_for_matching(leg.first_name).upper().strip()
            self.by_first_last.setdefault((first_upper, last_upper), []).append(leg)

            if leg.state:
                self.by_state_last.setdefault((leg.state.upper(), last_upper), []).append(leg)

            if leg.nickname:
                nick_upper = normalize_for_matching(leg.nickname).upper().strip()
                self.by_nickname_last.setdefault((nick_upper, last_upper), []).append(leg)

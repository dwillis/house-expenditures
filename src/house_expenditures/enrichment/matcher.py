"""Match expenditure organization names to legislators via bioguide IDs."""

import json
import logging
import re
from pathlib import Path

from house_expenditures.enrichment.legislators import LegislatorIndex
from house_expenditures.models import DetailRecord, Legislator, SummaryRecord
from house_expenditures.parsers.normalize import is_member_org, normalize_for_matching, parse_member_name, strip_year_prefix

logger = logging.getLogger(__name__)


def _unique_match(matches: list[Legislator]) -> Legislator | None:
    """Return a legislator if all matches refer to the same person."""
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    bioguide_ids = {m.bioguide_id for m in matches}
    if len(bioguide_ids) == 1:
        return matches[0]
    return None


def _load_overrides(path: Path | None) -> dict[str, str]:
    """Load manual name -> bioguide_id overrides from JSON file.

    Tolerates trailing commas (a common JSON editing mistake).
    """
    if path is None or not path.exists():
        return {}
    with open(path, "r") as f:
        raw = f.read()
    # Strip trailing commas before } or ] (not valid JSON but common)
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    data = json.loads(raw)
    return {k.upper().strip(): v for k, v in data.items()}


def _state_from_org_code(org_code: str | None) -> str:
    """Extract state abbreviation from organization_code (e.g., 'AL03ROM' -> 'AL').

    Only available in the 18-column format (2023+).
    """
    if not org_code or len(org_code) < 2:
        return ""
    prefix = org_code[:2].upper()
    # Verify it looks like a state abbreviation (two uppercase letters)
    if prefix.isalpha():
        return prefix
    return ""


def match_legislator(
    org: str,
    index: LegislatorIndex,
    overrides: dict[str, str] | None = None,
    org_code: str | None = None,
) -> Legislator | None:
    """Attempt to match an organization name to a legislator.

    Uses hierarchical fallback matching:
    1. Manual overrides
    2. Exact match on official_full name
    3. First + last name
    4. Nickname + last name
    5. Last name only (if unique)
    6. Last name + state hint
    7. Compound last name

    The org_code parameter (from 18-column format) provides a state hint
    when the organization name doesn't include one in parentheses.
    """
    if not is_member_org(org):
        return None

    parsed = parse_member_name(org)
    if not parsed["is_member"]:
        return None

    first = normalize_for_matching(parsed["first"] or "").upper().strip()
    last = normalize_for_matching(parsed["last"] or "").upper().strip()
    middle = normalize_for_matching(parsed["middle"] or "").upper().strip()
    state_hint = (parsed["state_hint"] or "").upper().strip()

    # Fall back to state from organization_code if name has no state hint
    if not state_hint:
        state_hint = _state_from_org_code(org_code)

    if not last:
        return None

    # 1. Manual overrides — try the cleaned name ("MIKE ROGERS")
    #    and the full original org string ("2020 HON. MIKE ROGERS")
    if overrides:
        raw_name = parsed["full_raw"].upper().strip()
        org_upper = org.upper().strip()
        for candidate in (raw_name, org_upper):
            if candidate in overrides:
                bio_id = overrides[candidate]
                if bio_id in index.by_bioguide:
                    return index.by_bioguide[bio_id]

    # 2. Exact match on official_full
    full_raw = normalize_for_matching(parsed["full_raw"] or "").upper().strip()
    if full_raw in index.by_full_name:
        matches = index.by_full_name[full_raw]
        result = _unique_match(matches)
        if result:
            return result

    # Also try with suffix removed from official_full comparison
    if first and last:
        parts = [first]
        if middle:
            parts.append(middle)
        parts.append(last)
        if parsed["suffix"]:
            parts.append(parsed["suffix"].upper())
        reconstructed = " ".join(parts)
        if reconstructed in index.by_full_name:
            matches = index.by_full_name[reconstructed]
            result = _unique_match(matches)
            if result:
                return result

    # 3. First + last name match
    if first:
        key = (first, last)
        if key in index.by_first_last:
            matches = index.by_first_last[key]
            result = _unique_match(matches)
            if result:
                return result
            if state_hint and len(matches) > 1:
                state_filtered = [m for m in matches if m.state.upper() == state_hint]
                result = _unique_match(state_filtered)
                if result:
                    return result

    # 4. Nickname + last name
    if first:
        nick_key = (first, last)
        if nick_key in index.by_nickname_last:
            matches = index.by_nickname_last[nick_key]
            result = _unique_match(matches)
            if result:
                return result

    # 5. Last name only (if unique)
    if last in index.by_last_name:
        matches = index.by_last_name[last]
        result = _unique_match(matches)
        if result:
            return result
        # Disambiguate by state if multiple matches
        if state_hint and len(matches) > 1:
            state_filtered = [m for m in matches if m.state.upper() == state_hint]
            result = _unique_match(state_filtered)
            if result:
                return result

    # 6. Last name + state hint
    if state_hint and last:
        key = (state_hint, last)
        if key in index.by_state_last:
            matches = index.by_state_last[key]
            result = _unique_match(matches)
            if result:
                return result

    # 7. Compound last name: try middle + last as a compound
    if middle:
        compound = f"{middle} {last}"
        if compound in index.by_last_name:
            matches = index.by_last_name[compound]
            result = _unique_match(matches)
            if result:
                return result

        # Try with hyphenated compound (DIAZ BARRAGAN -> DIAZ-BARRAGAN)
        compound_hyphen = f"{middle}-{last}"
        if compound_hyphen in index.by_last_name:
            matches = index.by_last_name[compound_hyphen]
            result = _unique_match(matches)
            if result:
                return result

        if first:
            for full_name, fn_matches in index.by_full_name.items():
                if last in full_name and first in full_name:
                    result = _unique_match(fn_matches)
                    if result:
                        return result

    # 8. Try middle name as first name (some reps go by their middle name)
    if middle:
        mid_key = (middle, last)
        if mid_key in index.by_first_last:
            matches = index.by_first_last[mid_key]
            result = _unique_match(matches)
            if result:
                return result

    # 9. Quoted nickname match (e.g., JESUS G. "CHUY" GARCIA)
    quoted_nick = (parsed.get("quoted_nickname") or "").upper().strip()
    if quoted_nick:
        nick_key = (quoted_nick, last)
        if nick_key in index.by_nickname_last:
            matches = index.by_nickname_last[nick_key]
            result = _unique_match(matches)
            if result:
                return result
        if nick_key in index.by_first_last:
            matches = index.by_first_last[nick_key]
            result = _unique_match(matches)
            if result:
                return result

    # 10. Try first name + initial matching (GREGORY FRANCIS -> Gregory F.)
    if first and middle and len(middle) > 1:
        initial = middle[0] + "."
        for full_name, fn_matches in index.by_full_name.items():
            if first in full_name and initial in full_name and last in full_name:
                result = _unique_match(fn_matches)
                if result:
                    return result

    # 11. Try matching just first initial + last (G. MURPHY -> Gregory Murphy)
    if first and len(first) >= 1:
        for (idx_first, idx_last), fn_matches in index.by_first_last.items():
            if idx_last == last and idx_first.startswith(first[0]):
                result = _unique_match(fn_matches)
                if result:
                    return result

    # 12. Hyphen/space normalization (WASSERMAN-SCHULTZ -> WASSERMAN SCHULTZ)
    if "-" in last:
        space_last = last.replace("-", " ")
        if space_last in index.by_last_name:
            matches = index.by_last_name[space_last]
            result = _unique_match(matches)
            if result:
                return result

    # 13. O' prefix handling (O HALLERAN -> O'HALLERAN)
    if middle and len(middle) <= 2 and middle in ("O", "MC", "DE", "LA"):
        compound = f"{middle}'{last}" if middle == "O" else f"{middle}{last}"
        for idx_last, fn_matches in index.by_last_name.items():
            normalized_idx = idx_last.replace("'", "'").replace("’", "'")
            if normalized_idx == compound:
                result = _unique_match(fn_matches)
                if result:
                    return result

    logger.warning("Unmatched member: %s", org)
    return None


def enrich_detail_records(
    records: list[DetailRecord],
    index: LegislatorIndex,
    congress: int,
    quarter_label: str,
    overrides_path: Path | None = None,
) -> list[DetailRecord]:
    """Enrich detail records with legislator info."""
    overrides = _load_overrides(overrides_path)
    match_cache: dict[str, Legislator | None] = {}
    matched_count = 0
    member_count = 0

    for record in records:
        record.congress = congress
        record.quarter_label = quarter_label
        record.is_member = is_member_org(record.organization)

        if not record.is_member:
            continue

        member_count += 1
        org_key = record.organization.upper().strip()

        if org_key not in match_cache:
            match_cache[org_key] = match_legislator(
                record.organization, index, overrides,
                org_code=record.organization_code,
            )

        leg = match_cache[org_key]
        if leg:
            record.bioguide_id = leg.bioguide_id
            record.member_name = leg.official_full or f"{leg.first_name} {leg.last_name}"
            record.party = leg.party[0] if leg.party else None  # "Democrat" -> "D"
            record.state = leg.state
            record.district = leg.district
            matched_count += 1

    unmatched = member_count - matched_count
    unique_unmatched = len([v for v in match_cache.values() if v is None])
    logger.info(
        "Matched %d/%d member records (%d unique unmatched names)",
        matched_count, member_count, unique_unmatched,
    )

    return records


def build_org_code_map(detail_records: list[DetailRecord]) -> dict[str, str]:
    """Build a mapping from org name to organization_code from detail records.

    Summary CSVs lack organization_code, but detail CSVs have it.
    This lets the summary enricher use org_code for state disambiguation.
    """
    org_codes: dict[str, str] = {}
    for r in detail_records:
        if r.organization and r.organization_code:
            key = r.organization.upper().strip()
            if key not in org_codes:
                org_codes[key] = r.organization_code
    return org_codes


def enrich_summary_records(
    records: list[SummaryRecord],
    index: LegislatorIndex,
    congress: int,
    quarter_label: str,
    overrides_path: Path | None = None,
    org_code_map: dict[str, str] | None = None,
) -> list[SummaryRecord]:
    """Enrich summary records with legislator info.

    org_code_map provides organization_code values from detail records,
    since summary CSVs don't include them.
    """
    overrides = _load_overrides(overrides_path)
    match_cache: dict[str, Legislator | None] = {}
    org_codes = org_code_map or {}

    for record in records:
        record.congress = congress
        record.quarter_label = quarter_label
        record.is_member = is_member_org(record.organization)

        if not record.is_member:
            continue

        org_key = record.organization.upper().strip()
        if org_key not in match_cache:
            match_cache[org_key] = match_legislator(
                record.organization, index, overrides,
                org_code=org_codes.get(org_key),
            )

        leg = match_cache[org_key]
        if leg:
            record.bioguide_id = leg.bioguide_id
            record.member_name = leg.official_full or f"{leg.first_name} {leg.last_name}"
            record.party = leg.party[0] if leg.party else None
            record.state = leg.state
            record.district = leg.district

    return records

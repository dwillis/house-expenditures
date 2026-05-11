"""Text normalization and name parsing for House expenditure data."""

import re
import unicodedata

from house_expenditures.config import NAME_SUFFIXES


def strip_accents(s: str) -> str:
    """Remove accent marks from characters (é -> e, ñ -> n, etc.)."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_for_matching(s: str) -> str:
    """Normalize a string for name matching: strip accents, unify apostrophes."""
    result = strip_accents(s)
    result = result.replace("‘", "'").replace("’", "'").replace("`", "'")
    return result


def normalize_text(s: str) -> str:
    """Normalize characters: en-dashes, smart quotes, whitespace."""
    s = s.replace("–", "-")  # en-dash
    s = s.replace("—", "-")  # em-dash
    s = s.replace("‘", "'").replace("’", "'")  # smart single quotes
    s = s.replace("“", '"').replace("”", '"')  # smart double quotes
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def strip_year_prefix(org: str) -> tuple[str | None, str]:
    """Extract year prefix from organization name.

    "2024 HON. JOHN SMITH" -> ("2024", "HON. JOHN SMITH")
    "OFFICE OF THE CLERK" -> (None, "OFFICE OF THE CLERK")
    """
    match = re.match(r"^(\d{4})\s+(.+)$", org.strip())
    if match:
        return match.group(1), match.group(2)
    return None, org.strip()


def parse_member_name(org: str) -> dict:
    """Parse a member organization name into components.

    Input like "HON. MIKE ROGERS (MI)" produces:
    {
        "full_raw": "MIKE ROGERS (MI)",
        "first": "MIKE",
        "last": "ROGERS",
        "middle": None,
        "suffix": None,
        "state_hint": "MI",
        "is_member": True,
    }
    """
    result = {
        "full_raw": org,
        "first": None,
        "last": None,
        "middle": None,
        "suffix": None,
        "state_hint": None,
        "quoted_nickname": None,
        "is_member": False,
    }

    _, cleaned = strip_year_prefix(org)

    if not cleaned.startswith("HON."):
        return result

    result["is_member"] = True
    name = cleaned[4:].strip()  # remove "HON. "

    # Normalize stray double-quotes used as apostrophes (e.g., O"ROURKE -> O'ROURKE)
    name = re.sub(r'(\w)"(\w)', r"\1'\2", name)

    result["full_raw"] = name

    state_match = re.search(r"\(([A-Z]{2})\)\s*$", name)
    if state_match:
        result["state_hint"] = state_match.group(1)
        name = name[: state_match.start()].strip()

    # Extract quoted nicknames like EARL L. "BUDDY" CARTER
    nick_match = re.search(r'"([^"]+)"', name)
    if nick_match:
        result["quoted_nickname"] = nick_match.group(1).strip()
    name = re.sub(r'"[^"]*"\s*', "", name).strip()

    parts = name.split()
    if not parts:
        return result

    # Check last token(s) for suffix
    if len(parts) >= 2 and parts[-1].rstrip(".").upper() in NAME_SUFFIXES:
        result["suffix"] = parts[-1]
        parts = parts[:-1]

    if len(parts) == 1:
        result["last"] = parts[0]
    elif len(parts) == 2:
        result["first"] = parts[0]
        result["last"] = parts[1]
    else:
        result["first"] = parts[0]
        result["last"] = parts[-1]
        result["middle"] = " ".join(parts[1:-1])

    return result


def normalize_date(s: str) -> str | None:
    """Convert date strings like '1-Nov-24' or '18-Mar-16' to yyyy-mm-dd."""
    if not s or not s.strip():
        return None
    from datetime import datetime
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            # Two-digit years: Python's %y uses a 69/31 cutoff.
            # Expenditure data spans 2009-2026, so this is fine.
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s.strip()


def clean_title(desc: str) -> str:
    """Clean job title by removing compensation addenda."""
    if not desc:
        return ""
    cleaned = re.sub(r"\s*\(OTHER COMPENSATION\)\s*$", "", desc, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(OVERTIME\)\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def is_member_org(org: str) -> bool:
    """Check if an organization name represents a member's office."""
    _, cleaned = strip_year_prefix(org)
    return cleaned.startswith("HON.")

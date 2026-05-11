from pathlib import Path

HOUSE_GOV_BASE = "https://www.house.gov"
MAIN_PAGE_URL = (
    "https://www.house.gov/the-house-explained/open-government/"
    "statement-of-disbursements"
)
ARCHIVE_PAGE_URL = (
    "https://www.house.gov/the-house-explained/open-government/"
    "statement-of-disbursements/archive"
)
LEGISLATORS_BASE_URL = (
    "https://raw.githubusercontent.com/unitedstates/"
    "congress-legislators/main"
)

DEFAULT_CACHE_DIR = Path.home() / ".house-expenditures" / "cache"
DEFAULT_OUTPUT_DIR = Path("output")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

LEGISLATORS_CACHE_TTL_DAYS = 7

DETAIL_COLUMNS_12 = [
    "ORGANIZATION",
    "PROGRAM",
    "SORT SUBTOTAL DESCRIPTION",
    "SORT SEQUENCE",
    "TRANSACTION DATE",
    "DATA SOURCE",
    "DOCUMENT",
    "VENDOR NAME",
    "PERFORM START DT",
    "PERFORM END DT",
    "DESCRIPTION",
    "AMOUNT",
]

DETAIL_COLUMNS_18 = [
    "ORGANIZATION",
    "FISCAL YEAR OR LEGISLATIVE YEAR",
    "ORGANIZATION CODE",
    "PROGRAM",
    "PROGRAM CODE",
    "SORT SUBTOTAL DESCRIPTION",
    "BUDGET OBJECT CLASS",
    "SORT SEQUENCE",
    "TRANSACTION DATE",
    "DATA SOURCE",
    "DOCUMENT",
    "VENDOR NAME",
    "VENDOR ID",
    "PERFORM START DT",
    "PERFORM END DT",
    "DESCRIPTION",
    "BUDGET OBJECT CODE",
    "AMOUNT",
]

SUMMARY_COLUMNS = [
    "ORGANIZATION",
    "PROGRAM",
    "DESCRIPTION",
    "YTD AMOUNT",
    "QTD AMOUNT",
]

SPENDING_CATEGORIES = [
    "FRANKED MAIL",
    "PERSONNEL COMPENSATION",
    "PERSONNEL BENEFITS",
    "TRAVEL",
    "RENT, COMMUNICATION, UTILITIES",
    "PRINTING AND REPRODUCTION",
    "OTHER SERVICES",
    "SUPPLIES AND MATERIALS",
    "EQUIPMENT",
    "TRANSPORTATION OF THINGS",
]

DATA_SOURCE_CODES = {
    "AP": "Accounts Payable",
    "AR": "Accounts Receivable",
    "GL": "General Ledger",
}

# Which party held the House majority in each Congress (CSV era: 114th onward)
MAJORITY_PARTY: dict[int, str] = {
    114: "R",  # 2015-2017
    115: "R",  # 2017-2019
    116: "D",  # 2019-2021
    117: "D",  # 2021-2023
    118: "R",  # 2023-2025
    119: "R",  # 2025-2027
}

LEADERSHIP_OFFICES_MAJORITY = [
    "OFFICE OF THE SPEAKER",
    "OFFICE OF THE MAJORITY LEADER",
    "OFFICE OF THE MAJORITY WHIP",
    "OFFICE OF THE CHIEF DEPUTY MAJORITY WHIP",
]

LEADERSHIP_OFFICES_MINORITY = [
    "OFFICE OF THE MINORITY LEADER",
    "OFFICE OF THE MINORITY WHIP",
    "OFFICE OF THE CHIEF DEPUTY MINORITY WHIP",
]

PARTY_ORGANIZATIONS: dict[str, str] = {
    "REPUBLICAN CONFERENCE": "R",
    "REPUBLICAN STUDY COMMITTEE": "R",
    "DEMOCRATIC CAUCUS": "D",
    "DEMOCRATIC STEERING AND POLICY COMMITTEE": "D",
    "CONGRESSIONAL PROGRESSIVE CAUCUS": "D",
    "CONGRESSIONAL BLACK CAUCUS": "D",
    "CONGRESSIONAL HISPANIC CAUCUS": "D",
}

# Common name suffixes to detect during matching
NAME_SUFFIXES = {"JR", "JR.", "SR", "SR.", "II", "III", "IV", "V", "MD", "MD.", "DDS", "PHD", "PH.D."}

from dataclasses import dataclass, field
from pathlib import Path


# Vendors that are card-gateway aggregators or known institutional payees —
# exclude from rare-vendor and wash-pair detectors.
KNOWN_INSTITUTIONAL_VENDORS: frozenset[str] = frozenset({
    "CITIBANK",
    "CITIBANK GOV CARD SERVICE",
    "UNITED STATES POSTAL SERVICE",
    "US POSTAL SERVICE",
    "USPS",
    "UPS",
    "FEDEX",
    "AT&T",
    "VERIZON",
    "VERIZON WIRELESS",
    "T-MOBILE",
    "COMCAST",
    "SPECTRUM",
    "COX COMMUNICATIONS",
    "AMAZON",
    "AMAZON.COM",
    "AMAZON WEB SERVICES",
    "MICROSOFT",
    "APPLE",
    "GOOGLE",
    "UNITED AIRLINES",
    "AMERICAN AIRLINES",
    "DELTA AIR LINES",
    "SOUTHWEST AIRLINES",
    "JETBLUE",
    "AMTRAK",
    "LEIDOS DIGITAL SOLUTIONS INC",
    "ACCURATE WORD",
    "READYREFRESH BY NESTLE",
    "IMPACTOFFICE",
    "CONGRESSIONAL FEDERAL CREDIT UNION",
    "HOUSE OF REPRESENTATIVES",
    "ARCHITECT OF THE CAPITOL",
    "GOVERNMENT PUBLISHING OFFICE",
    "GPO",
    "CONGRESSIONAL RESEARCH SERVICE",
    "LIBRARY OF CONGRESS",
    "NATIONAL ARCHIVES",
    "FEDERAL EXPRESS",
    "DHL",
    "STAPLES",
    "OFFICE DEPOT",
    "OFFICEMAX",
    "W B MASON CO INC",
    "W.B. MASON",
})

# Vendor name prefixes that indicate a card-gateway sub-merchant — these are
# real specific vendors and should NOT be excluded.
CARD_GATEWAY_PREFIXES: tuple[str, ...] = ("CITIBANK -",)

# Spending categories treated as "rare" — their dominance flags potential waste.
RARE_CATEGORIES: frozenset[str] = frozenset({
    "EQUIPMENT",
    "INSURANCE CLAIMS & INDEMNITIES",
    "BENEFITS TO FORMER PERSONNEL",
    "FRANKED MAIL",
})

# Personnel categories — exclude from vendor-level and transaction-level detectors.
PERSONNEL_CATEGORIES: frozenset[str] = frozenset({
    "PERSONNEL COMPENSATION",
    "PERSONNEL BENEFITS",
})

def is_election_year(year: int) -> bool:
    """Federal general elections fall in even years."""
    return year % 2 == 0


# Communications categories that surge before elections.
COMMS_CATEGORIES: frozenset[str] = frozenset({
    "FRANKED MAIL",
    "PRINTING AND REPRODUCTION",
})

# Categories prone to year-end budget-exhaustion buying (MRA is use-it-or-lose-it).
YEAR_END_CATEGORIES: frozenset[str] = frozenset({
    "EQUIPMENT",
    "SUPPLIES AND MATERIALS",
})

# Newsworthiness weight per detector, used by triage scoring. Higher = a
# finding from this detector is more likely to be a pursuable story on its own.
DETECTOR_WEIGHTS: dict[str, float] = {
    "L": 3.0,   # member-name vendor match (self-dealing shape)
    "N": 2.5,   # pre-election communications surge
    "M": 2.0,   # person-shaped payee
    "O": 2.0,   # departing-member spend-down
    "E": 1.5,   # rare vendor
    "P": 1.5,   # year-end exhaustion
    "F": 1.2,   # vendor concentration
    "G": 1.2,   # new expensive vendor
    "C": 1.0,   # category outlier
    "D": 1.0,   # rare category dominance
    "H": 1.0,   # large transaction
    "B": 0.5,   # cross-quarter negatives
    "I": 0.4,   # round numbers
    "J": 0.4,   # wash pairs
    "A": 0.3,   # negative AP rate (bookkeeping signal)
    "K": 0.2,   # velocity (busy != wrong)
}

# Detectors whose findings are corroborating context only — they never form a
# story lead by themselves (bookkeeping artifacts, volume effects).
CORROBORATION_ONLY_DETECTORS: frozenset[str] = frozenset({"A", "I", "J", "K"})


@dataclass
class AnomalyConfig:
    output_dir: Path = Path("output")
    since_quarter: str | None = None      # e.g. "2022Q1" — ignore earlier quarters
    member_only: bool = True

    # ── Negative amount detectors ──────────────────────────────────────────
    neg_office_zscore: float = 3.0
    neg_cross_quarter_min: int = 3        # quarters with ≥1 negative to qualify
    neg_vendor_exclude: frozenset = field(
        default_factory=lambda: frozenset({"CITIBANK", "CITIBANK GOV CARD SERVICE"})
    )

    # ── Category detectors ────────────────────────────────────────────────
    category_zscore: float = 3.0
    category_min_amount: float = 5000.0   # floor — don't flag trivial outliers
    category_fdr_q: float = 0.10          # Benjamini–Hochberg FDR across share tests
    category_min_share: float = 0.10      # outlier must be ≥10% of non-personnel spend
    category_rare_dominance: float = 0.30 # rare category > 30% of non-personnel spend

    # ── Vendor detectors ──────────────────────────────────────────────────
    vendor_rare_office_count: int = 2
    vendor_rare_min_amount: float = 5000.0
    vendor_rare_solo_high_amount: float = 25000.0  # solo-office vendor needs this for HIGH
    vendor_concentration_threshold: float = 0.70
    vendor_concentration_min_total: float = 10000.0
    new_vendor_debut_year: int = 2023
    new_vendor_min_offices: int = 3
    new_vendor_min_amount: float = 50000.0

    # ── Transaction-level detectors ───────────────────────────────────────
    large_tx_zscore: float = 4.0
    large_tx_min_amount: float = 25000.0
    round_number_modulus: float = 500.0
    round_number_min: float = 2000.0
    round_number_min_cluster: int = 4     # ≥N round payments to same vendor = pattern
    wash_tolerance_pct: float = 0.02
    wash_min_amount: float = 5000.0
    wash_max_days_apart: int = 90
    wash_recurring_count: int = 3         # same positive amount ≥N times = recurring, skip
    velocity_zscore: float = 3.5

    # ── Insider detectors (L/M) ───────────────────────────────────────────
    insider_min_amount: float = 1000.0    # cumulative office×vendor floor for surname match
    insider_shared_surname_min: float = 5000.0  # higher floor when surname shared by members
    person_vendor_min_amount: float = 10000.0   # cumulative floor for person-shaped payees

    # ── Timing detectors (N/O/P) ──────────────────────────────────────────
    election_surge_ratio: float = 2.0     # election-year comms spend vs own baseline
    election_surge_min_delta: float = 5000.0
    spend_down_ratio: float = 1.5         # final-quarters spend vs own trailing mean
    spend_down_min_delta: float = 10000.0
    year_end_ratio: float = 2.0           # Q4 equipment/supplies vs own Q1–Q3 average
    year_end_min_delta: float = 15000.0

    # ── Triage / output ───────────────────────────────────────────────────
    max_leads: int = 50
    lead_min_amount: float = 5000.0       # leads under this total take a score penalty
    detector_weights: dict = field(default_factory=lambda: dict(DETECTOR_WEIGHTS))
    institutional_vendors: frozenset = frozenset()  # populated at runtime from data
    report_path: Path = Path("anomaly_report.txt")
    flagged_csv_path: Path = Path("anomaly_flagged.csv")
    leads_csv_path: Path = Path("anomaly_leads.csv")

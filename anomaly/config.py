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

# Election years — franked mail in Q3/Q4 of these years is suspicious.
ELECTION_YEARS: frozenset[int] = frozenset({2016, 2018, 2020, 2022, 2024})


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
    category_min_amount: float = 1000.0   # floor — don't flag trivial outliers
    category_rare_dominance: float = 0.30 # rare category > 30% of non-personnel spend

    # ── Vendor detectors ──────────────────────────────────────────────────
    vendor_rare_office_count: int = 2
    vendor_rare_min_amount: float = 5000.0
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
    round_number_min_cluster: int = 2     # ≥N round payments to same vendor = pattern
    wash_tolerance_pct: float = 0.02
    wash_min_amount: float = 1000.0
    wash_max_days_apart: int = 90
    velocity_zscore: float = 3.5

    # ── Output ────────────────────────────────────────────────────────────
    report_path: Path = Path("anomaly_report.txt")
    flagged_csv_path: Path = Path("anomaly_flagged.csv")
    max_findings_per_detector: int = 100

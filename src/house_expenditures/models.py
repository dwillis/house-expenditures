from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class Quarter:
    year: int
    quarter: int

    @property
    def congress(self) -> int:
        # Congress terms start Jan 3 of odd years.
        # Q4 (Oct-Dec) of even years is still the current congress.
        # Q1 (Jan-Mar) of odd years belongs to the NEW congress.
        return ((self.year - 1789) // 2) + 1

    @property
    def start_date(self) -> date:
        month = {1: 1, 2: 4, 3: 7, 4: 10}[self.quarter]
        return date(self.year, month, 1)

    @property
    def end_date(self) -> date:
        ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        month, day = ends[self.quarter]
        return date(self.year, month, day)

    @property
    def label(self) -> str:
        return f"{self.year}Q{self.quarter}"


@dataclass
class DetailRecord:
    organization: str = ""
    fiscal_year: str | None = None
    organization_code: str | None = None
    program: str = ""
    program_code: str | None = None
    category: str = ""
    budget_object_class: str | None = None
    sort_sequence: str = ""
    transaction_date: str | None = None
    data_source: str | None = None
    document: str | None = None
    vendor_name: str | None = None
    vendor_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    budget_object_code: str | None = None
    amount: Decimal | None = None
    # enrichment fields
    bioguide_id: str | None = None
    member_name: str | None = None
    party: str | None = None
    state: str | None = None
    district: int | None = None
    congress: int | None = None
    quarter_label: str = ""
    is_member: bool = False


@dataclass
class SummaryRecord:
    organization: str = ""
    program: str = ""
    description: str = ""
    ytd_amount: Decimal | None = None
    qtd_amount: Decimal | None = None
    # enrichment fields
    bioguide_id: str | None = None
    member_name: str | None = None
    party: str | None = None
    state: str | None = None
    district: int | None = None
    congress: int | None = None
    quarter_label: str = ""
    is_member: bool = False


@dataclass
class StafferRecord:
    name: str = ""
    title: str = ""
    office: str = ""
    bioguide_id: str | None = None
    party: str | None = None
    state: str | None = None
    district: int | None = None
    quarter: str = ""
    start_date: str | None = None
    end_date: str | None = None
    amount: Decimal | None = None


@dataclass
class Legislator:
    bioguide_id: str = ""
    first_name: str = ""
    last_name: str = ""
    official_full: str | None = None
    nickname: str | None = None
    suffix: str | None = None
    middle: str | None = None
    party: str = ""
    state: str = ""
    district: int | None = None
    chamber: str = "rep"
    term_start: str = ""
    term_end: str = ""

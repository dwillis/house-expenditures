"""Tests for the anomaly detectors against planted synthetic anomalies."""

from anomaly.config import AnomalyConfig
from anomaly.detectors import category, insider, timing, transactions, vendor
from tests.anomaly_helpers import make_detail, make_summary, vanilla_offices


def cfg(**overrides) -> AnomalyConfig:
    return AnomalyConfig(**overrides)


class TestWashPairs:
    """Regression tests for the cross-product bug: one refund against a
    recurring payment must not generate a finding per occurrence."""

    def test_recurring_rent_with_one_refund_yields_nothing(self):
        rows = vanilla_offices()
        for month in ("01", "02", "03"):
            rows.append({
                "bioguide_id": "X1", "member_name": "Xavier One",
                "vendor_name": "LANDLORD LLC", "amount": 6000.0,
                "transaction_date": f"2025-{month}-01",
            })
        rows.append({
            "bioguide_id": "X1", "member_name": "Xavier One",
            "vendor_name": "LANDLORD LLC", "amount": -6000.0,
            "transaction_date": "2025-02-15",
        })
        found = transactions.detect_wash_pairs(make_detail(rows), cfg())
        assert found == []

    def test_single_pair_matched_once(self):
        rows = vanilla_offices()
        rows.append({
            "bioguide_id": "X1", "member_name": "Xavier One",
            "vendor_name": "ONEOFF VENDOR", "amount": 8000.0,
            "transaction_date": "2025-01-10",
        })
        rows.append({
            "bioguide_id": "X1", "member_name": "Xavier One",
            "vendor_name": "ONEOFF VENDOR", "amount": -8000.0,
            "transaction_date": "2025-01-20",
        })
        found = transactions.detect_wash_pairs(make_detail(rows), cfg())
        assert len(found) == 1
        assert found[0].extra["days_apart"] == 10

    def test_two_positives_one_negative_yields_one_pair(self):
        rows = []
        rows.append({
            "bioguide_id": "X1", "member_name": "Xavier One",
            "vendor_name": "TWICE VENDOR", "amount": 8000.0,
            "transaction_date": "2025-01-10",
        })
        rows.append({
            "bioguide_id": "X1", "member_name": "Xavier One",
            "vendor_name": "TWICE VENDOR", "amount": 8000.0,
            "transaction_date": "2025-02-10",
        })
        rows.append({
            "bioguide_id": "X1", "member_name": "Xavier One",
            "vendor_name": "TWICE VENDOR", "amount": -8000.0,
            "transaction_date": "2025-01-12",
        })
        found = transactions.detect_wash_pairs(make_detail(rows), cfg())
        assert len(found) == 1


class TestCategoryOutliers:
    """Regression tests for zero-inflated share distributions."""

    def _summary(self, outlier_amount: float, n_zero: int = 0, n_spenders: int = 14):
        rows = []
        for i in range(n_spenders):
            bid, name = f"S{i}", f"Spender {i}"
            rows.append({"bioguide_id": bid, "member_name": name,
                         "description": "TRAVEL", "qtd_amount": 47000.0 + i * 100})
            rows.append({"bioguide_id": bid, "member_name": name,
                         "description": "EQUIPMENT", "qtd_amount": 2500.0 + i * 10})
        for i in range(n_zero):
            bid, name = f"Z{i}", f"Zero {i}"
            rows.append({"bioguide_id": bid, "member_name": name,
                         "description": "TRAVEL", "qtd_amount": 50000.0})
        rows.append({"bioguide_id": "OUT1", "member_name": "Out Lier",
                     "description": "TRAVEL", "qtd_amount": 10000.0})
        rows.append({"bioguide_id": "OUT1", "member_name": "Out Lier",
                     "description": "EQUIPMENT", "qtd_amount": outlier_amount})
        return make_summary(rows)

    def test_modest_spender_not_flagged_despite_zero_peers(self):
        # Many offices spend nothing on EQUIPMENT; a modest spender must not
        # blow up the z-score the way the raw-MAD version did.
        summary = self._summary(outlier_amount=3000.0, n_zero=30)
        found = category.detect_category_outliers(summary, cfg())
        assert all(f.bioguide_id != "OUT1" for f in found)

    def test_extreme_share_among_nonzero_peers_flagged(self):
        summary = self._summary(outlier_amount=40000.0)  # 80% share vs ~5% peers
        found = category.detect_category_outliers(summary, cfg())
        assert any(
            f.bioguide_id == "OUT1" and f.extra["category"] == "EQUIPMENT"
            for f in found
        )

    def test_share_capped_when_office_total_dragged_negative(self):
        # A refund-heavy quarter must not produce shares above 100%
        rows = []
        for i in range(14):
            bid, name = f"S{i}", f"Spender {i}"
            rows.append({"bioguide_id": bid, "member_name": name,
                         "description": "TRAVEL", "qtd_amount": 47000.0 + i * 100})
            rows.append({"bioguide_id": bid, "member_name": name,
                         "description": "EQUIPMENT", "qtd_amount": 2500.0})
        rows.append({"bioguide_id": "NEG1", "member_name": "Neg Office",
                     "description": "TRAVEL", "qtd_amount": -30000.0})
        rows.append({"bioguide_id": "NEG1", "member_name": "Neg Office",
                     "description": "EQUIPMENT", "qtd_amount": 8000.0})
        found = category.detect_category_outliers(make_summary(rows), cfg())
        for f in found:
            share = float(f.extra["category_share"].rstrip("%")) / 100
            assert share <= 1.0

    def test_small_dollars_not_flagged(self):
        rows = []
        for i in range(14):
            bid, name = f"S{i}", f"Spender {i}"
            rows.append({"bioguide_id": bid, "member_name": name,
                         "description": "TRAVEL", "qtd_amount": 900.0})
            rows.append({"bioguide_id": bid, "member_name": name,
                         "description": "EQUIPMENT", "qtd_amount": 50.0})
        rows.append({"bioguide_id": "OUT1", "member_name": "Out Lier",
                     "description": "TRAVEL", "qtd_amount": 200.0})
        rows.append({"bioguide_id": "OUT1", "member_name": "Out Lier",
                     "description": "EQUIPMENT", "qtd_amount": 800.0})
        found = category.detect_category_outliers(make_summary(rows), cfg())
        assert found == []  # under the $5k floor


class TestRareVendors:
    def test_solo_vendor_needs_high_amount_for_high_severity(self):
        rows = vanilla_offices()
        rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                     "vendor_name": "BIG SOLO VENDOR", "amount": 30000.0})
        rows.append({"bioguide_id": "X2", "member_name": "Xavier Two",
                     "vendor_name": "SMALL SOLO VENDOR", "amount": 6000.0})
        found = vendor.detect_rare_vendors(make_detail(rows), cfg())
        by_vendor = {f.vendor_name: f for f in found}
        assert by_vendor["BIG SOLO VENDOR"].severity == "HIGH"
        assert by_vendor["SMALL SOLO VENDOR"].severity == "MEDIUM"

    def test_member_reimbursement_excluded_from_rare_vendors(self):
        rows = vanilla_offices()
        rows.append({"bioguide_id": "X1", "member_name": "Pete Sessions",
                     "vendor_name": "HON PETE SESSIONS", "amount": 190000.0})
        found = vendor.detect_rare_vendors(make_detail(rows), cfg())
        assert all("HON" not in (f.vendor_name or "") for f in found)

    def test_institutional_vendor_excluded(self):
        rows = vanilla_offices()
        rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                     "vendor_name": "AMAZON.COM", "amount": 50000.0})
        found = vendor.detect_rare_vendors(make_detail(rows), cfg())
        assert all(f.vendor_name != "AMAZON COM" for f in found)


class TestRoundNumbers:
    def test_two_round_payments_below_cluster_minimum(self):
        rows = vanilla_offices()
        for date in ("2025-01-10", "2025-02-10"):
            rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                         "vendor_name": "ROUNDY", "amount": 2500.0,
                         "transaction_date": date})
        found = transactions.detect_round_numbers(make_detail(rows), cfg())
        assert found == []

    def test_four_round_payments_flagged(self):
        rows = vanilla_offices()
        for date in ("2025-01-10", "2025-02-10", "2025-03-10", "2025-04-10"):
            rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                         "vendor_name": "ROUNDY", "amount": 2500.0,
                         "transaction_date": date})
        found = transactions.detect_round_numbers(make_detail(rows), cfg())
        assert len(found) == 1
        assert found[0].vendor_name == "ROUNDY"


class TestInsiderDetectors:
    def test_member_surname_vendor_flagged(self):
        rows = vanilla_offices()
        rows.append({"bioguide_id": "X1", "member_name": "Jane Smithfield",
                     "vendor_name": "SMITHFIELD CONSULTING LLC", "amount": 4000.0})
        found = insider.detect_member_name_vendors(make_detail(rows), cfg())
        assert len(found) == 1
        assert found[0].severity == "HIGH"
        assert found[0].extra["matched_surname"] == "SMITHFIELD"

    def test_other_members_vendor_not_flagged(self):
        rows = vanilla_offices()
        rows.append({"bioguide_id": "X1", "member_name": "Jane Smithfield",
                     "vendor_name": "JOHNSONVILLE CATERING", "amount": 4000.0})
        found = insider.detect_member_name_vendors(make_detail(rows), cfg())
        assert found == []

    def test_shared_surname_requires_higher_floor(self):
        rows = vanilla_offices()
        for bid, name in (("X1", "Jane Smithfield"), ("X2", "Bob Smithfield")):
            rows.append({"bioguide_id": bid, "member_name": name,
                         "vendor_name": "SOMETHING ELSE", "amount": 100.0})
        rows.append({"bioguide_id": "X1", "member_name": "Jane Smithfield",
                     "vendor_name": "SMITHFIELD CONSULTING", "amount": 4000.0})
        found = insider.detect_member_name_vendors(make_detail(rows), cfg())
        assert found == []  # $4k < $5k shared-surname floor

    def test_member_reimbursement_not_flagged_as_self_dealing(self):
        # "HON <member>" vendors are routine expense reimbursements
        rows = vanilla_offices()
        rows.append({"bioguide_id": "X1", "member_name": "Pete Sessions",
                     "vendor_name": "HON PETE SESSIONS", "amount": 190000.0})
        found = insider.detect_member_name_vendors(make_detail(rows), cfg())
        assert found == []
        found = insider.detect_person_payees(make_detail(rows), cfg())
        assert found == []

    def test_person_shaped_payee_flagged(self):
        rows = vanilla_offices()
        rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                     "vendor_name": "JOHN DOE", "amount": 12000.0})
        rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                     "vendor_name": "ACME GROUP", "amount": 12000.0})
        found = insider.detect_person_payees(make_detail(rows), cfg())
        assert [f.vendor_name for f in found] == ["JOHN DOE"]


class TestTimingDetectors:
    def test_year_end_exhaustion_flagged(self):
        rows = []
        for q in ("Q1", "Q2", "Q3", "Q4"):
            amount = 40000.0 if q == "Q4" else 2000.0
            rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                         "description": "EQUIPMENT", "qtd_amount": amount,
                         "quarter_label": f"2025{q}"})
        found = timing.detect_year_end_exhaustion(make_summary(rows), cfg())
        assert len(found) == 1
        assert found[0].quarter == "2025Q4"

    def test_steady_spender_not_flagged(self):
        rows = []
        for q in ("Q1", "Q2", "Q3", "Q4"):
            rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                         "description": "EQUIPMENT", "qtd_amount": 5000.0,
                         "quarter_label": f"2025{q}"})
        found = timing.detect_year_end_exhaustion(make_summary(rows), cfg())
        assert found == []

    def test_departing_member_spend_down(self):
        rows = []
        quarters = ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"]
        for q in quarters:
            amount = 60000.0 if q.startswith("2026") else 20000.0
            rows.append({"bioguide_id": "DEP1", "member_name": "Dee Parting",
                         "description": "OTHER SERVICES", "qtd_amount": amount,
                         "quarter_label": q, "congress": 119})
        # A continuing member so congress 120 exists in the data
        rows.append({"bioguide_id": "CONT1", "member_name": "Carry On",
                     "description": "OTHER SERVICES", "qtd_amount": 20000.0,
                     "quarter_label": "2027Q1", "congress": 120})
        for q in quarters:
            rows.append({"bioguide_id": "CONT1", "member_name": "Carry On",
                         "description": "OTHER SERVICES", "qtd_amount": 20000.0,
                         "quarter_label": q, "congress": 119})
        found = timing.detect_departing_spend_down(make_summary(rows), cfg())
        assert [f.bioguide_id for f in found] == ["DEP1"]
        assert found[0].extra["ratio"] == 3.0

    def test_election_comms_surge(self):
        rows = []
        # Off-year baseline 2025, election-year surge 2026
        for year, amount in (("2025", 5000.0), ("2026", 25000.0)):
            for q in ("Q2", "Q3"):
                rows.append({"bioguide_id": "X1", "member_name": "Xavier One",
                             "description": "FRANKED MAIL", "qtd_amount": amount,
                             "quarter_label": f"{year}{q}"})
        found = timing.detect_election_comms_surge(make_summary(rows), cfg())
        assert len(found) == 1
        assert found[0].extra["election_year"] == 2026
        assert found[0].extra["baseline_source"] == "own off-year Q2+Q3 mean"

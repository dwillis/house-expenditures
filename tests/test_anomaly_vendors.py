"""Tests for vendor canonicalization and institutional-vendor identification."""

from anomaly.vendors import (
    add_canonical_vendor,
    clean_vendor_name,
    institutional_vendors,
)
from tests.anomaly_helpers import make_detail


class TestCleanVendorName:
    def test_strips_entity_suffixes(self):
        assert clean_vendor_name("ACME CONSULTING LLC") == ("ACME CONSULTING", False)
        assert clean_vendor_name("Acme Consulting, Inc.") == ("ACME CONSULTING", False)

    def test_collapses_punctuation(self):
        assert clean_vendor_name("W.B. MASON CO INC")[0] == "W B MASON"

    def test_gateway_prefix_stripped_and_flagged(self):
        name, is_gateway = clean_vendor_name("CITIBANK -EZCATER BONCHON")
        assert is_gateway
        assert name == "EZCATER BONCHON"

    def test_bare_gateway_not_flagged(self):
        name, is_gateway = clean_vendor_name("CITIBANK")
        assert not is_gateway
        assert name == "CITIBANK"

    def test_empty_and_none(self):
        assert clean_vendor_name(None) == ("", False)
        assert clean_vendor_name("") == ("", False)


class TestCanonicalVendor:
    def test_vendor_id_merges_typo_variants(self):
        df = make_detail([
            {"bioguide_id": "A1", "member_name": "A", "vendor_name": "SHARP ELECTRONICS",
             "vendor_id": "0000009514", "amount": 100},
            {"bioguide_id": "A1", "member_name": "A", "vendor_name": "SHARP ELECTRONICS",
             "vendor_id": "9514", "amount": 100},
            {"bioguide_id": "A2", "member_name": "B", "vendor_name": "SHARP ELECTRONICS CORPORATIION",
             "vendor_id": "9514", "amount": 100},
        ])
        assert set(df["canonical_vendor"]) == {"SHARP ELECTRONICS"}

    def test_gateway_submerchants_not_merged_by_shared_id(self):
        df = make_detail([
            {"bioguide_id": "A1", "member_name": "A", "vendor_name": "CITIBANK -MAILCHIMP",
             "vendor_id": "33707", "amount": 100},
            {"bioguide_id": "A2", "member_name": "B", "vendor_name": "CITIBANK -USHR CATERING",
             "vendor_id": "33707", "amount": 100},
        ])
        assert set(df["canonical_vendor"]) == {"MAILCHIMP", "USHR CATERING"}
        assert df["is_gateway_submerchant"].all()

    def test_null_vendor_id_keeps_cleaned_name(self):
        df = make_detail([
            {"bioguide_id": "A1", "member_name": "A", "vendor_name": "SOLO VENDOR LLC",
             "vendor_id": None, "amount": 100},
        ])
        assert df["canonical_vendor"].iloc[0] == "SOLO VENDOR"


class TestInstitutionalVendors:
    def test_ubiquitous_vendor_is_institutional(self):
        rows = []
        for i in range(10):
            rows.append({"bioguide_id": f"B{i}", "member_name": f"M{i}",
                         "vendor_name": "EVERYONE USES THIS", "amount": 100})
        rows.append({"bioguide_id": "B0", "member_name": "M0",
                     "vendor_name": "NICHE VENDOR", "amount": 100})
        df = make_detail(rows)
        inst = institutional_vendors(df, office_share_threshold=0.25)
        assert "EVERYONE USES THIS" in inst
        assert "NICHE VENDOR" not in inst

    def test_seed_list_included_in_cleaned_form(self):
        df = make_detail([
            {"bioguide_id": "B0", "member_name": "M0", "vendor_name": "X", "amount": 1},
        ])
        inst = institutional_vendors(df)
        assert "AMAZON COM" in inst  # "AMAZON.COM" cleaned
        assert "W B MASON" in inst   # "W.B. MASON" cleaned

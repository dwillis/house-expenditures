"""Tests for the story-lead triage layer."""

from anomaly.config import AnomalyConfig
from anomaly.report import Finding
from anomaly.triage import build_leads


def finding(detector_id="E", detector_name="Rare vendor", severity="MEDIUM",
            bioguide_id="X1", member_name="Xavier One", vendor_name="VENDOR A",
            amount=10000.0, quarter="2025Q1", **extra) -> Finding:
    return Finding(
        detector_id=detector_id, detector_name=detector_name, severity=severity,
        bioguide_id=bioguide_id, member_name=member_name, party="D", state="MD",
        quarter=quarter, description="test", amount=amount,
        vendor_name=vendor_name, extra=extra,
    )


class TestBuildLeads:
    def test_corroborated_lead_outranks_single_finding(self):
        findings = [
            # One member-vendor pair hit by three detectors
            finding(detector_id="E", amount=10000.0),
            finding(detector_id="F", detector_name="Vendor concentration", amount=10000.0),
            finding(detector_id="I", detector_name="Round numbers", amount=10000.0),
            # A single, larger finding elsewhere
            finding(detector_id="E", bioguide_id="Y1", member_name="Solo",
                    vendor_name="VENDOR B", amount=40000.0),
        ]
        leads = build_leads(findings, AnomalyConfig())
        assert leads[0].vendor_name == "VENDOR A"
        assert leads[0].detectors == {"E", "F", "I"}
        assert leads[0].score > leads[1].score

    def test_findings_grouped_per_member_vendor(self):
        findings = [
            finding(quarter="2025Q1"),
            finding(quarter="2025Q2"),
            finding(bioguide_id="Y1", member_name="Other", vendor_name="VENDOR A"),
        ]
        leads = build_leads(findings, AnomalyConfig())
        assert len(leads) == 2
        lead = next(l for l in leads if l.bioguide_id == "X1")
        assert lead.quarters == ["2025Q1", "2025Q2"]
        assert len(lead.findings) == 2

    def test_corroboration_only_detectors_never_lead_alone(self):
        findings = [
            finding(detector_id="A", detector_name="Negative AP rate", amount=50000.0),
            finding(detector_id="K", detector_name="Velocity", vendor_name=None,
                    amount=None),
            finding(detector_id="J", detector_name="Wash pair", amount=60000.0),
        ]
        leads = build_leads(findings, AnomalyConfig())
        assert leads == []

    def test_corroboration_only_attaches_to_primary_lead(self):
        findings = [
            finding(detector_id="E", amount=10000.0),
            finding(detector_id="I", amount=10000.0),
        ]
        leads = build_leads(findings, AnomalyConfig())
        assert len(leads) == 1
        assert leads[0].detectors == {"E", "I"}

    def test_amount_uses_max_not_sum(self):
        findings = [
            finding(detector_id="E", amount=10000.0),
            finding(detector_id="F", amount=10000.0),
        ]
        leads = build_leads(findings, AnomalyConfig())
        assert leads[0].amount == 10000.0

    def test_max_leads_cap(self):
        findings = [
            finding(bioguide_id=f"M{i}", member_name=f"Member {i}",
                    vendor_name=f"VENDOR {i}", amount=10000.0 + i)
            for i in range(60)
        ]
        leads = build_leads(findings, AnomalyConfig(max_leads=10))
        assert len(leads) == 10

    def test_small_amount_penalized(self):
        findings = [
            finding(bioguide_id="A1", vendor_name="TINY", amount=500.0),
            finding(bioguide_id="B1", vendor_name="BIGGER", amount=20000.0),
        ]
        leads = build_leads(findings, AnomalyConfig())
        assert leads[0].vendor_name == "BIGGER"

    def test_hook_mentions_member_vendor_and_pattern(self):
        leads = build_leads([finding()], AnomalyConfig())
        hook = leads[0].hook
        assert "Xavier One" in hook
        assert "VENDOR A" in hook
        assert "vendor used by almost no other offices" in hook

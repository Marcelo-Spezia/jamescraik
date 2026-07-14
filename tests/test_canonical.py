"""Tests for canonical models (§4) — Account, Contact, Signal, enums."""

from datetime import date

import pytest
from pydantic import ValidationError

from icp_engine.canonical.enums import (
    Department,
    FundingStage,
    Industry,
    Seniority,
    SignalStrength,
)
from icp_engine.canonical.models import Account, Contact, Signal


class TestSignal:
    def test_valid_signal(self):
        s = Signal(
            type="funding_round",
            strength=SignalStrength.STRONG,
            observed_at=date(2026, 5, 1),
            source="crunchbase",
            detail="Series B closed.",
        )
        assert s.type == "funding_round"
        assert s.strength == SignalStrength.STRONG

    def test_invalid_strength_rejected(self):
        with pytest.raises(ValidationError):
            Signal(
                type="funding_round",
                strength="ultra",  # not a valid SignalStrength
                observed_at=date(2026, 5, 1),
                source="test",
            )


class TestAccount:
    def test_minimal_valid_account(self):
        acc = Account(account_id="acc_1", name="Test Corp")
        assert acc.account_id == "acc_1"
        assert acc.domain is None
        assert acc.industry is None
        assert acc.employee_count is None
        assert acc.tech_stack == []
        assert acc.intent_signals == []

    def test_full_account(self):
        acc = Account(
            account_id="acc_2",
            name="Full Corp",
            domain="fullcorp.com",
            industry=Industry.SOFTWARE,
            employee_count=500,
            revenue_usd=20_000_000,
            country="US",
            region="NA",
            founded_year=2015,
            funding_stage=FundingStage.SERIES_B,
            tech_stack=["salesforce", "snowflake"],
            source="fixture",
            raw={"original": "data"},
        )
        assert acc.industry == Industry.SOFTWARE
        assert acc.funding_stage == FundingStage.SERIES_B
        assert "salesforce" in acc.tech_stack
        assert acc.raw["original"] == "data"

    def test_invalid_industry_rejected(self):
        with pytest.raises(ValidationError):
            Account(account_id="acc_3", name="Bad", industry="space_mining")

    def test_negative_employee_count_rejected(self):
        with pytest.raises(ValidationError):
            Account(account_id="acc_4", name="Negative", employee_count=-10)

    def test_enum_serialises_as_string(self):
        acc = Account(
            account_id="acc_5",
            name="Enum Test",
            industry=Industry.FINTECH,
        )
        data = acc.model_dump()
        assert data["industry"] == "fintech"


class TestContact:
    def test_minimal_valid_contact(self):
        ct = Contact(
            contact_id="ct_1",
            account_id="acc_1",
            full_name="Jane Doe",
        )
        assert ct.seniority == Seniority.UNKNOWN
        assert ct.department == Department.OTHER
        assert ct.email is None

    def test_full_contact(self):
        ct = Contact(
            contact_id="ct_2",
            account_id="acc_1",
            full_name="John Doe",
            title="VP of Engineering",
            seniority=Seniority.VP,
            department=Department.ENGINEERING,
            country="US",
            linkedin_url="https://linkedin.com/in/johndoe",
            email="john@example.com",
            source="fixture",
        )
        assert ct.seniority == Seniority.VP
        assert ct.department == Department.ENGINEERING

    def test_invalid_seniority_rejected(self):
        with pytest.raises(ValidationError):
            Contact(
                contact_id="ct_3",
                account_id="acc_1",
                full_name="Bad",
                seniority="supreme_leader",
            )


class TestEnums:
    def test_all_industries_are_strings(self):
        for ind in Industry:
            assert isinstance(ind.value, str)

    def test_strenum_comparison(self):
        """StrEnum values should compare equal to their string representation."""
        assert Industry.SOFTWARE == "software"
        assert Seniority.VP == "vp"
        assert Department.ENGINEERING == "engineering"
        assert FundingStage.SERIES_B == "series_b"

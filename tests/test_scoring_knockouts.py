"""Tests for knockouts and disqualifiers — Step 1 of scoring (§6.1)."""

from pathlib import Path

import pytest

from fixtures.accounts import (
    make_government_account,
    make_ideal_account,
    make_small_account,
)
from fixtures.contacts import make_ideal_contact
from icp_engine.registry.loader import load_icp
from icp_engine.scoring.pipeline import score

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "icps"


@pytest.fixture
def basic_icp():
    return load_icp(FIXTURES_DIR / "valid_basic.yaml")


class TestKnockouts:
    def test_small_account_is_disqualified(self, basic_icp):
        """Account with 30 employees fails knockout (gte 50) → tier D."""
        account = make_small_account()  # 30 employees
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.disqualified is True
        assert result.tier == "D"
        # Knockout should be recorded
        failed = [ko for ko in result.knockouts if not ko.passed]
        assert len(failed) == 1
        assert failed[0].field == "employee_count"
        assert "Too small" in failed[0].reason

    def test_ideal_account_passes_knockout(self, basic_icp):
        """Account with 800 employees passes knockout (gte 50)."""
        account = make_ideal_account()  # 800 employees
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.disqualified is False
        passed = [ko for ko in result.knockouts if ko.passed]
        assert len(passed) == 1

    def test_knockout_with_none_field_fails(self, basic_icp):
        """If employee_count is None, knockout condition gte 50 fails."""
        account = make_ideal_account(employee_count=None)
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.disqualified is True
        assert result.tier == "D"


class TestDisqualifiers:
    def test_government_is_disqualified(self, basic_icp):
        """Government industry matches disqualifier → tier D."""
        account = make_government_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.disqualified is True
        assert result.tier == "D"
        triggered = [dq for dq in result.disqualifiers if dq.matched]
        assert len(triggered) == 1
        assert triggered[0].field == "industry"
        assert "Compliance" in triggered[0].reason

    def test_software_not_disqualified(self, basic_icp):
        """Software industry does NOT match disqualifier."""
        account = make_ideal_account()  # software industry
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        triggered = [dq for dq in result.disqualifiers if dq.matched]
        assert len(triggered) == 0


class TestDisqualifiedAlwaysTierD:
    def test_disqualified_even_with_high_score_is_tier_d(self, basic_icp):
        """Even if all criteria match, a knockout failure forces tier D."""
        # Perfect match on everything except employee_count = 30 (knockout)
        account = make_ideal_account(employee_count=30)
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.disqualified is True
        assert result.tier == "D"
        # Score is still computed (informative) but tier is D
        assert result.fit_score > 0

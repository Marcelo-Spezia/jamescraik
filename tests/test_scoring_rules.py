"""Tests for deterministic rules scoring — Step 2 (§6.2) and intent boost (§6.4)."""

from pathlib import Path

import pytest

from fixtures.accounts import (
    make_ideal_account,
    make_intent_rich_account,
    make_partial_match_account,
)
from fixtures.contacts import make_ideal_contact, make_partial_contact, make_wrong_persona_contact
from icp_engine.registry.loader import load_icp
from icp_engine.scoring.pipeline import score

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "icps"


@pytest.fixture
def basic_icp():
    return load_icp(FIXTURES_DIR / "valid_basic.yaml")


class TestAccountScoring:
    def test_ideal_account_scores_100(self, basic_icp):
        """Account matching all criteria should get account_score = 100."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.account_score == 100.0

    def test_partial_match_account(self, basic_icp):
        """Account matching some criteria gets partial score."""
        account = make_partial_match_account()  # misses employee_count + tech_stack
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        # Matches: industry (30) + region (15) + funding_stage (15) = 60/100
        assert result.account_score == 60.0

    def test_contributions_recorded(self, basic_icp):
        """Every criterion should have a contribution record."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        account_contribs = [c for c in result.contributions if c.level == "account"]
        assert len(account_contribs) == 5  # 5 account_criteria in basic ICP


class TestContactScoring:
    def test_ideal_contact_scores_100(self, basic_icp):
        """Contact matching all criteria should get contact_score = 100."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.contact_score == 100.0

    def test_wrong_persona_scores_0(self, basic_icp):
        """Contact matching no criteria gets contact_score = 0."""
        account = make_ideal_account()
        contact = make_wrong_persona_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.contact_score == 0.0

    def test_partial_contact(self, basic_icp):
        """Director in marketing: seniority matches (50) but dept doesn't (0)."""
        account = make_ideal_account()
        contact = make_partial_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.contact_score == 50.0


class TestCombination:
    def test_ideal_fit_score(self, basic_icp):
        """Ideal account + ideal contact + intent → high fit score."""
        account = make_ideal_account()  # has leadership_change signal
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        # account=100, contact=100, intent=8 (leadership_change)
        # base = 0.6*100 + 0.4*100 = 100
        # fit = 100 + 8 = 108 → clamped to 100
        assert result.fit_score == 100.0
        assert result.tier == "A"
        assert result.intent_points == 8

    def test_no_intent_signals(self, basic_icp):
        """Account without signals gets 0 intent points."""
        account = make_ideal_account(intent_signals=[])
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.intent_points == 0

    def test_intent_boost_cap(self, basic_icp):
        """Intent points are capped at intent_max_boost (20)."""
        account = make_intent_rich_account()
        # Has funding_round(10) + leadership_change(8) + job_post_revops(6) = 24
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        # Capped at 20
        assert result.intent_points == 20


class TestTierBoundaries:
    def test_score_80_is_tier_a(self, basic_icp):
        """Score exactly 80 should be tier A."""
        # This is hard to engineer exactly, so we test through the combiner directly
        from icp_engine.scoring.combiner import assign_tier
        assert assign_tier(80.0, basic_icp.scoring, disqualified=False) == "A"

    def test_score_79_is_tier_b(self, basic_icp):
        assert (
            __import__("icp_engine.scoring.combiner", fromlist=["assign_tier"])
            .assign_tier(79.9, basic_icp.scoring, disqualified=False) == "B"
        )

    def test_score_60_is_tier_b(self, basic_icp):
        from icp_engine.scoring.combiner import assign_tier
        assert assign_tier(60.0, basic_icp.scoring, disqualified=False) == "B"

    def test_score_40_is_tier_c(self, basic_icp):
        from icp_engine.scoring.combiner import assign_tier
        assert assign_tier(40.0, basic_icp.scoring, disqualified=False) == "C"

    def test_score_39_is_tier_d(self, basic_icp):
        from icp_engine.scoring.combiner import assign_tier
        assert assign_tier(39.0, basic_icp.scoring, disqualified=False) == "D"

    def test_score_0_is_tier_d(self, basic_icp):
        from icp_engine.scoring.combiner import assign_tier
        assert assign_tier(0.0, basic_icp.scoring, disqualified=False) == "D"


class TestExplanation:
    def test_explanation_not_empty(self, basic_icp):
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.explanation != ""
        assert "Fit" in result.explanation

    def test_disqualified_explanation(self, basic_icp):
        account = make_ideal_account(employee_count=30)
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert "DISQUALIFIED" in result.explanation

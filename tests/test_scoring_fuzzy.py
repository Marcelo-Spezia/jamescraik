"""Tests for fuzzy criteria scoring — Step 3 (§6.3)."""

from pathlib import Path

import pytest

from fixtures.accounts import make_ideal_account
from fixtures.contacts import make_ideal_contact
from icp_engine.adapters.base import FuzzyResult
from icp_engine.adapters.stub import StubJudgeModel
from icp_engine.registry.loader import load_icp
from icp_engine.scoring.pipeline import score

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "icps"


@pytest.fixture
def fuzzy_icp():
    return load_icp(FIXTURES_DIR / "valid_with_fuzzy.yaml")


class TestFuzzyWithStub:
    def test_stub_judge_adds_points(self, fuzzy_icp):
        """Stub judge with 0.7 score → 14 points (0.7 * 20 weight)."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)
        judge = StubJudgeModel(default_score=0.7, default_rationale="Strong signals.")

        result = score(account, contact, fuzzy_icp, judge=judge)

        assert len(result.fuzzy) == 1
        assert result.fuzzy[0].id == "digital_maturity"
        assert result.fuzzy[0].score_0_1 == 0.7
        assert result.fuzzy[0].points == 14.0
        assert result.fuzzy[0].rationale == "Strong signals."

    def test_stub_judge_zero_score(self, fuzzy_icp):
        """Stub judge with 0.0 score adds nothing."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)
        judge = StubJudgeModel(default_score=0.0, default_rationale="Insufficient data.")

        result = score(account, contact, fuzzy_icp, judge=judge)

        assert result.fuzzy[0].points == 0.0
        assert result.fuzzy[0].rationale == "Insufficient data."

    def test_fuzzy_affects_account_score(self, fuzzy_icp):
        """Fuzzy points should increase the account_score.

        Uses an account that matches only one of the two account_criteria
        (industry, not region) so the deterministic rules score is 50 — leaving
        headroom for fuzzy points to lift it (otherwise account_score saturates
        at 100 and the additive fuzzy contribution is invisible, §6.4).
        """
        account = make_ideal_account(region="EMEA")
        contact = make_ideal_contact(account_id=account.account_id)

        # Without fuzzy
        judge_zero = StubJudgeModel(default_score=0.0)
        result_no_fuzzy = score(account, contact, fuzzy_icp, judge=judge_zero)

        # With fuzzy
        judge_high = StubJudgeModel(default_score=0.8)
        result_with_fuzzy = score(account, contact, fuzzy_icp, judge=judge_high)

        assert result_with_fuzzy.account_score > result_no_fuzzy.account_score

    def test_per_criterion_overrides(self, fuzzy_icp):
        """StubJudgeModel can override scores per criterion by prompt substring.

        The JudgeModel contract (§12) only receives the criterion prompt, so
        overrides are matched against a substring of that prompt — here
        "digital maturity", which appears in the digital_maturity criterion's
        prompt.
        """
        judge = StubJudgeModel(
            default_score=0.5,
            overrides={
                "digital maturity": FuzzyResult(
                    score_0_1=0.9,
                    rationale="Highly digitally mature.",
                ),
            },
        )
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, fuzzy_icp, judge=judge)

        assert result.fuzzy[0].score_0_1 == 0.9
        assert result.fuzzy[0].points == 18.0  # 0.9 * 20


class TestFuzzyDisabled:
    def test_no_judge_degrades_gracefully(self, fuzzy_icp):
        """When judge=None, fuzzy criteria should still appear with 0 points."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, fuzzy_icp, judge=None)

        assert len(result.fuzzy) == 1
        assert result.fuzzy[0].points == 0.0
        assert "disabled" in result.fuzzy[0].rationale.lower()

    def test_fuzzy_disabled_in_config(self):
        """When fuzzy.enabled=false in ICP, fuzzy criteria are skipped."""
        basic_icp = load_icp(FIXTURES_DIR / "valid_basic.yaml")
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        # Basic ICP has fuzzy.enabled=false and no fuzzy_criteria
        assert len(result.fuzzy) == 0

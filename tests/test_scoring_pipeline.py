"""End-to-end pipeline tests — full scoring flow (§6, §7, §14)."""

from pathlib import Path

import pytest

from fixtures.accounts import make_ideal_account, make_partial_match_account, make_small_account
from fixtures.contacts import make_ideal_contact, make_partial_contact, make_wrong_persona_contact
from icp_engine.adapters.stub import StubJudgeModel
from icp_engine.registry.loader import load_icp
from icp_engine.scoring.pipeline import score
from icp_engine.scoring.result import ScoreResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "icps"


@pytest.fixture
def basic_icp():
    return load_icp(FIXTURES_DIR / "valid_basic.yaml")


@pytest.fixture
def fuzzy_icp():
    return load_icp(FIXTURES_DIR / "valid_with_fuzzy.yaml")


class TestE2EPipeline:
    def test_ideal_match_tier_a(self, basic_icp):
        """Ideal account + ideal contact → tier A."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert isinstance(result, ScoreResult)
        assert result.tier == "A"
        assert result.fit_score >= 80
        assert result.disqualified is False
        assert result.icp_id == "test-basic"
        assert result.icp_version == "1.0.0"
        assert result.account_id == account.account_id
        assert result.contact_id == contact.contact_id

    def test_partial_match_tier_b_or_c(self, basic_icp):
        """Partial account + partial contact → B or C tier."""
        account = make_partial_match_account()
        contact = make_partial_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.tier in ("B", "C")
        assert 40 <= result.fit_score < 80
        assert result.disqualified is False

    def test_bad_everything_tier_d(self, basic_icp):
        """Small account (knockout) → tier D regardless of score."""
        account = make_small_account()
        contact = make_wrong_persona_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        assert result.tier == "D"
        assert result.disqualified is True

    def test_score_result_has_all_fields(self, basic_icp):
        """ScoreResult must contain all §7 fields."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        # Required fields from §7
        assert result.account_id
        assert result.contact_id
        assert result.icp_id
        assert result.icp_version
        assert result.scored_at is not None
        assert isinstance(result.fit_score, float)
        assert result.tier in ("A", "B", "C", "D")
        assert isinstance(result.disqualified, bool)
        assert isinstance(result.account_score, float)
        assert isinstance(result.contact_score, float)
        assert isinstance(result.intent_points, float)
        assert isinstance(result.knockouts, list)
        assert isinstance(result.disqualifiers, list)
        assert isinstance(result.contributions, list)
        assert isinstance(result.fuzzy, list)
        assert isinstance(result.intent, list)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0

    def test_score_result_json_serialisable(self, basic_icp):
        """ScoreResult must be JSON-serialisable (§7: JSON output)."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)
        json_str = result.model_dump_json()

        assert isinstance(json_str, str)
        assert '"fit_score"' in json_str
        assert '"tier"' in json_str

    def test_version_association(self):
        """Scores must be associated with their ICP version (§9, §14.5)."""
        icp_v1 = load_icp(FIXTURES_DIR / "valid_basic.yaml")
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, icp_v1)

        assert result.icp_id == icp_v1.meta.id
        assert result.icp_version == icp_v1.meta.version

    def test_contributions_are_auditable(self, basic_icp):
        """Every contribution should have field, expected, observed, match, points."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)

        result = score(account, contact, basic_icp)

        for contrib in result.contributions:
            assert contrib.level in ("account", "contact")
            assert contrib.field != ""
            assert isinstance(contrib.match, bool)
            assert isinstance(contrib.points, float)


class TestE2EWithFuzzy:
    def test_fuzzy_pipeline_with_stub(self, fuzzy_icp):
        """Full pipeline with fuzzy criteria using stub judge."""
        account = make_ideal_account()
        contact = make_ideal_contact(account_id=account.account_id)
        judge = StubJudgeModel(default_score=0.7, default_rationale="Good signals.")

        result = score(account, contact, fuzzy_icp, judge=judge)

        assert result.tier in ("A", "B")
        assert len(result.fuzzy) == 1
        assert result.fuzzy[0].points > 0

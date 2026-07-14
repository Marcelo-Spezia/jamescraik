"""Tests for feedback loop and ICP-fit rate (§10, §11)."""


from icp_engine.feedback.fit_rate import calculate_fit_rate, calculate_tier_correlation
from icp_engine.feedback.models import FeedbackRecord, ReasonCode, Verdict


def _make_feedback(
    verdict: Verdict,
    icp_version: str = "1.0.0",
    tier: str = "B",
    **kwargs,
) -> FeedbackRecord:
    defaults = dict(
        account_id="acc_001",
        contact_id="ct_001",
        icp_id="test-basic",
        icp_version=icp_version,
        predicted_tier=tier,
        predicted_fit_score=75.0,
        verdict=verdict,
        reason_code=ReasonCode.GOOD_FIT if verdict == Verdict.FIT else ReasonCode.WRONG_SIZE,
        marked_by="sdr_test",
    )
    defaults.update(kwargs)
    return FeedbackRecord(**defaults)


class TestFeedbackModel:
    def test_valid_feedback(self):
        fb = _make_feedback(Verdict.FIT)
        assert fb.verdict == Verdict.FIT
        assert fb.icp_version == "1.0.0"

    def test_no_fit_with_reason(self):
        fb = _make_feedback(
            Verdict.NO_FIT,
            reason_code=ReasonCode.WRONG_INDUSTRY,
            reason_note="They're actually a consultancy, not software.",
        )
        assert fb.verdict == Verdict.NO_FIT
        assert fb.reason_code == ReasonCode.WRONG_INDUSTRY


class TestFitRate:
    def test_all_fit(self):
        feedbacks = [_make_feedback(Verdict.FIT) for _ in range(10)]
        results = calculate_fit_rate(feedbacks)

        assert len(results) == 1
        assert results[0].fit_rate == 1.0
        assert results[0].fit_count == 10

    def test_all_no_fit(self):
        feedbacks = [_make_feedback(Verdict.NO_FIT) for _ in range(5)]
        results = calculate_fit_rate(feedbacks)

        assert results[0].fit_rate == 0.0
        assert results[0].no_fit_count == 5

    def test_mixed(self):
        feedbacks = [
            _make_feedback(Verdict.FIT),
            _make_feedback(Verdict.FIT),
            _make_feedback(Verdict.NO_FIT),
            _make_feedback(Verdict.FIT),
            _make_feedback(Verdict.NO_FIT),
        ]
        results = calculate_fit_rate(feedbacks)

        assert results[0].fit_rate == 0.6
        assert results[0].fit_rate_pct == 60.0

    def test_empty_feedbacks(self):
        results = calculate_fit_rate([])
        assert len(results) == 0

    def test_filter_by_version(self):
        feedbacks = [
            _make_feedback(Verdict.FIT, icp_version="1.0.0"),
            _make_feedback(Verdict.FIT, icp_version="1.0.0"),
            _make_feedback(Verdict.NO_FIT, icp_version="2.0.0"),
            _make_feedback(Verdict.NO_FIT, icp_version="2.0.0"),
        ]

        v1 = calculate_fit_rate(feedbacks, icp_version="1.0.0")
        v2 = calculate_fit_rate(feedbacks, icp_version="2.0.0")

        assert v1[0].fit_rate == 1.0
        assert v2[0].fit_rate == 0.0

    def test_grouped_by_version(self):
        feedbacks = [
            _make_feedback(Verdict.FIT, icp_version="1.0.0"),
            _make_feedback(Verdict.NO_FIT, icp_version="1.0.0"),
            _make_feedback(Verdict.FIT, icp_version="2.0.0"),
        ]

        results = calculate_fit_rate(feedbacks)

        assert len(results) == 2
        v1 = next(r for r in results if r.icp_version == "1.0.0")
        v2 = next(r for r in results if r.icp_version == "2.0.0")
        assert v1.fit_rate == 0.5
        assert v2.fit_rate == 1.0


class TestTierCorrelation:
    def test_tier_a_fits_more(self):
        feedbacks = [
            _make_feedback(Verdict.FIT, tier="A"),
            _make_feedback(Verdict.FIT, tier="A"),
            _make_feedback(Verdict.NO_FIT, tier="A"),
            _make_feedback(Verdict.FIT, tier="D"),
            _make_feedback(Verdict.NO_FIT, tier="D"),
            _make_feedback(Verdict.NO_FIT, tier="D"),
            _make_feedback(Verdict.NO_FIT, tier="D"),
        ]

        results = calculate_tier_correlation(feedbacks)

        tier_a = next(r for r in results if r.tier == "A")
        tier_d = next(r for r in results if r.tier == "D")

        # A should have higher fit rate than D
        assert tier_a.fit_rate > tier_d.fit_rate
        assert abs(tier_a.fit_rate - 0.6667) < 0.01
        assert tier_d.fit_rate == 0.25

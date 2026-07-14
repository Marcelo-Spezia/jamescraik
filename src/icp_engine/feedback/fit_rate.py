"""ICP-fit rate calculation (§11 of the spec).

ICP-fit rate (version, period) = # leads marked "fit" / # leads marked (fit + no_fit)

Reported per ICP version so we can see if v2 improves over v1.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from icp_engine.feedback.models import FeedbackRecord, Verdict


@dataclass
class FitRateResult:
    """Result of fit-rate calculation for a specific ICP version."""

    icp_id: str
    icp_version: str
    total: int
    fit_count: int
    no_fit_count: int
    fit_rate: float  # 0.0 to 1.0

    @property
    def fit_rate_pct(self) -> float:
        """Fit rate as a percentage (0-100)."""
        return round(self.fit_rate * 100, 2)


@dataclass
class TierCorrelation:
    """Correlation between predicted tier and actual verdict (§11 secondary metric)."""

    tier: str
    total: int
    fit_count: int
    no_fit_count: int
    fit_rate: float


def calculate_fit_rate(
    feedbacks: list[FeedbackRecord],
    icp_id: str | None = None,
    icp_version: str | None = None,
) -> list[FitRateResult]:
    """Calculate ICP-fit rate, optionally filtered by id and/or version.

    If neither filter is provided, calculates fit-rate for each
    (icp_id, icp_version) pair found in the feedbacks.

    Returns:
        List of FitRateResult, one per (icp_id, icp_version) group.
    """
    # Filter
    filtered = feedbacks
    if icp_id is not None:
        filtered = [f for f in filtered if f.icp_id == icp_id]
    if icp_version is not None:
        filtered = [f for f in filtered if f.icp_version == icp_version]

    # Group by (icp_id, icp_version)
    groups: dict[tuple[str, str], list[FeedbackRecord]] = defaultdict(list)
    for fb in filtered:
        groups[(fb.icp_id, fb.icp_version)].append(fb)

    results: list[FitRateResult] = []
    for (gid, gver), records in sorted(groups.items()):
        fit = sum(1 for r in records if r.verdict == Verdict.FIT)
        no_fit = sum(1 for r in records if r.verdict == Verdict.NO_FIT)
        total = fit + no_fit
        rate = fit / total if total > 0 else 0.0

        results.append(FitRateResult(
            icp_id=gid,
            icp_version=gver,
            total=total,
            fit_count=fit,
            no_fit_count=no_fit,
            fit_rate=round(rate, 4),
        ))

    return results


def calculate_tier_correlation(
    feedbacks: list[FeedbackRecord],
    icp_id: str | None = None,
    icp_version: str | None = None,
) -> list[TierCorrelation]:
    """Calculate fit-rate per predicted tier (§11 secondary metric).

    Shows whether A/B tiers are really fit more often than C/D.
    """
    filtered = feedbacks
    if icp_id is not None:
        filtered = [f for f in filtered if f.icp_id == icp_id]
    if icp_version is not None:
        filtered = [f for f in filtered if f.icp_version == icp_version]

    by_tier: dict[str, list[FeedbackRecord]] = defaultdict(list)
    for fb in filtered:
        by_tier[fb.predicted_tier].append(fb)

    results: list[TierCorrelation] = []
    for tier in sorted(by_tier.keys()):
        records = by_tier[tier]
        fit = sum(1 for r in records if r.verdict == Verdict.FIT)
        no_fit = sum(1 for r in records if r.verdict == Verdict.NO_FIT)
        total = fit + no_fit
        rate = fit / total if total > 0 else 0.0

        results.append(TierCorrelation(
            tier=tier,
            total=total,
            fit_count=fit,
            no_fit_count=no_fit,
            fit_rate=round(rate, 4),
        ))

    return results

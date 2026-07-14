"""Feedback loop — sales feedback + ICP-fit rate (§10, §11)."""

from icp_engine.feedback.fit_rate import calculate_fit_rate
from icp_engine.feedback.models import FeedbackRecord, ReasonCode, Verdict

__all__ = ["FeedbackRecord", "ReasonCode", "Verdict", "calculate_fit_rate"]

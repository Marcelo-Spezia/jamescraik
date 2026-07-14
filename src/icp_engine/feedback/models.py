"""Feedback data model (§10 of the spec).

Sales marks each worked lead as fit / no_fit.  This record captures the
verdict together with the predicted score so we can measure accuracy and
refine the ICP.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Verdict(StrEnum):
    """Sales verdict on a scored lead."""

    FIT = "fit"
    NO_FIT = "no_fit"


class ReasonCode(StrEnum):
    """Controlled taxonomy for no-fit reasons (§10).

    Short codes that can be aggregated to find ICP error patterns.
    """

    WRONG_SIZE = "wrong_size"
    WRONG_INDUSTRY = "wrong_industry"
    WRONG_PERSONA = "wrong_persona"
    BAD_TIMING = "bad_timing"
    GOOD_FIT = "good_fit"
    OTHER = "other"


class FeedbackRecord(BaseModel):
    """A single feedback entry from sales (§10).

    Ties a human verdict back to the ICP version and predicted score,
    enabling ICP-fit rate measurement and refinement.
    """

    account_id: str
    contact_id: str
    icp_id: str
    icp_version: str

    predicted_tier: str
    predicted_fit_score: float

    verdict: Verdict
    reason_code: ReasonCode = ReasonCode.OTHER
    reason_note: str = ""

    marked_by: str = ""
    marked_at: datetime = Field(default_factory=lambda: datetime.now())

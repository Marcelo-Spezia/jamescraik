"""ScoreResult — the output of the scoring engine (§7 of the spec).

This is what sales, handoff, and the feedback loop consume.
Explainability is mandatory: every score carries its "why".
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnockoutResult(BaseModel):
    """Result of evaluating a single knockout criterion."""

    field: str
    op: str
    value: int | float | str | list
    passed: bool
    reason: str = ""


class DisqualifierResult(BaseModel):
    """Result of evaluating a single disqualifier criterion."""

    field: str
    op: str
    value: int | float | str | list
    matched: bool
    reason: str = ""


class Contribution(BaseModel):
    """How a single scored criterion contributed to the total (§6.2).

    This IS the explanation: field, expected, observed, match, points.
    """

    level: str  # "account" or "contact"
    field: str
    expected: int | float | str | list
    observed: int | float | str | list | None
    match: bool
    points: float


class FuzzyContribution(BaseModel):
    """How a single fuzzy criterion contributed (§6.3)."""

    id: str
    score_0_1: float
    points: float
    rationale: str


class IntentContribution(BaseModel):
    """How an intent signal contributed to the final score (§6.4)."""

    signal_type: str
    points: int
    detail: str = ""


class ScoreResult(BaseModel):
    """Complete scoring result for a (Account, Contact, ICP@version) tuple (§7).

    JSON-serialisable.  The ``contributions`` list is the auditable source of
    truth; ``explanation`` is a human-readable summary derived from it.
    """

    account_id: str
    contact_id: str
    icp_id: str
    icp_version: str
    scored_at: datetime = Field(default_factory=datetime.utcnow)

    fit_score: float = 0
    tier: str = "D"
    disqualified: bool = False

    account_score: float = 0
    contact_score: float = 0
    intent_points: float = 0

    knockouts: list[KnockoutResult] = Field(default_factory=list)
    disqualifiers: list[DisqualifierResult] = Field(default_factory=list)
    contributions: list[Contribution] = Field(default_factory=list)
    fuzzy: list[FuzzyContribution] = Field(default_factory=list)
    intent: list[IntentContribution] = Field(default_factory=list)

    explanation: str = ""

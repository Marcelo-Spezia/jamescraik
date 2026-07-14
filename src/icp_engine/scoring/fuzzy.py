"""Fuzzy criteria evaluation — Step 3 of the scoring pipeline (§6.3).

Delegates to a JudgeModel (LLM) for each fuzzy_criterion defined in the ICP.
Handles graceful degradation: if data is insufficient, score is 0.
"""

from __future__ import annotations

from typing import Any

from icp_engine.adapters.base import JudgeModel
from icp_engine.canonical.models import Account, Contact
from icp_engine.registry.schema import FuzzyCriterion
from icp_engine.scoring.result import FuzzyContribution


def _build_entity_data(
    account: Account,
    contact: Contact,
    applies_to: str,
) -> dict[str, Any]:
    """Build a dict of relevant entity data for the LLM prompt.

    Only includes non-None fields to keep the context focused.
    """
    if applies_to == "account":
        data = account.model_dump(exclude_none=True, exclude={"raw"})
    else:
        data = contact.model_dump(exclude_none=True, exclude={"raw"})
        # Include account context for contact-level fuzzy criteria
        data["account_name"] = account.name
        data["account_industry"] = str(account.industry) if account.industry else None
    return data


class FuzzyEval:
    """Aggregated result of the fuzzy step, split by level (§6.3).

    ``*_earned`` are the points won (``Σ score_0_1 * weight``).
    ``*_weight`` are the total fuzzy weights that participate in the
    denominator (§6.4).  When the step does not run, weights are 0 so the
    level normalises on its deterministic criteria only (graceful degradation).
    """

    def __init__(self) -> None:
        self.account_earned = 0.0
        self.account_weight = 0.0
        self.contact_earned = 0.0
        self.contact_weight = 0.0
        self.contributions: list[FuzzyContribution] = []


async def evaluate_fuzzy_criteria(
    account: Account,
    contact: Contact,
    criteria: list[FuzzyCriterion],
    judge: JudgeModel | None,
) -> FuzzyEval:
    """Evaluate all fuzzy criteria using the JudgeModel.

    Args:
        account: The account being scored.
        contact: The contact being scored.
        criteria: Fuzzy criteria from the ICP segment.
        judge: JudgeModel implementation (can be None if fuzzy is disabled).

    Returns:
        A ``FuzzyEval`` with earned points and participating weights per level,
        plus the per-criterion contributions for the explanation.

    If judge is None the step does not run: contributions are recorded with 0
    points and a rationale, and no fuzzy weight enters the denominator (§6.3,
    §6.4 graceful degradation).
    """
    out = FuzzyEval()

    if judge is None:
        # Fuzzy disabled — record zero contributions, contribute no weight.
        for criterion in criteria:
            out.contributions.append(FuzzyContribution(
                id=criterion.id,
                score_0_1=0.0,
                points=0.0,
                rationale="Fuzzy evaluation disabled (no JudgeModel configured).",
            ))
        return out

    for criterion in criteria:
        entity_data = _build_entity_data(account, contact, criterion.applies_to)

        result = await judge.evaluate(
            criterion_prompt=criterion.prompt,
            entity_data=entity_data,
        )

        # Clamp score to [0, 1]
        clamped_score = max(0.0, min(1.0, result.score_0_1))
        points = clamped_score * criterion.weight

        if criterion.applies_to == "account":
            out.account_earned += points
            out.account_weight += criterion.weight
        else:
            out.contact_earned += points
            out.contact_weight += criterion.weight

        out.contributions.append(FuzzyContribution(
            id=criterion.id,
            score_0_1=clamped_score,
            points=round(points, 2),
            rationale=result.rationale,
        ))

    return out

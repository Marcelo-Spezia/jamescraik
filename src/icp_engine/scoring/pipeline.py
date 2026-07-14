"""Scoring pipeline orchestrator (§6 of the spec).

Entry point: ``score(account, contact, icp, judge) → ScoreResult``.
Runs the 5-step pipeline in order:
  1. Knockouts & disqualifiers (gate)
  2. Deterministic rules scoring
  3. Fuzzy criteria (LLM via JudgeModel)
  4. Combination + intent boost
  5. Tier assignment

Produces a complete, explainable ScoreResult (§7).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from icp_engine.adapters.base import JudgeModel
from icp_engine.canonical.models import Account, Contact
from icp_engine.registry.schema import ICPDefinition
from icp_engine.scoring.combiner import assign_tier, calculate_intent_points, combine_scores
from icp_engine.scoring.fuzzy import FuzzyEval, evaluate_fuzzy_criteria
from icp_engine.scoring.result import (
    Contribution,
    FuzzyContribution,
    ScoreResult,
)
from icp_engine.scoring.rules import (
    evaluate_account_criteria,
    evaluate_contact_criteria,
    evaluate_disqualifiers,
    evaluate_knockouts,
)


def _generate_explanation(result: ScoreResult) -> str:
    """Generate a human-readable explanation from contributions.

    Deterministic template-based approach (no LLM needed).
    """
    parts: list[str] = []

    # Header
    parts.append(f"Fit {result.tier} ({result.fit_score:.0f}).")

    # Disqualification
    if result.disqualified:
        failed_kos = [ko for ko in result.knockouts if not ko.passed]
        triggered_dqs = [dq for dq in result.disqualifiers if dq.matched]
        reasons = [ko.reason for ko in failed_kos] + [dq.reason for dq in triggered_dqs]
        if reasons:
            parts.append("DISQUALIFIED: " + "; ".join(reasons))
        return " ".join(parts)

    # Account & contact scores
    parts.append(
        f"Account score {result.account_score:.0f}, "
        f"contact score {result.contact_score:.0f}."
    )

    # Key matches
    matches = [c for c in result.contributions if c.match]
    if matches:
        match_fields = [c.field for c in matches]
        parts.append("Matches: " + ", ".join(match_fields) + ".")

    # Key misses
    misses = [c for c in result.contributions if not c.match]
    if misses:
        miss_fields = [c.field for c in misses]
        parts.append("Gaps: " + ", ".join(miss_fields) + ".")

    # Fuzzy
    for fc in result.fuzzy:
        if fc.points > 0:
            parts.append(f"Fuzzy '{fc.id}': +{fc.points:.0f}pts ({fc.rationale})")

    # Intent
    if result.intent_points > 0:
        intent_details = [f"{ic.signal_type} +{ic.points}" for ic in result.intent]
        parts.append("Intent boost: " + ", ".join(intent_details) + ".")

    return " ".join(parts)


async def score_async(
    account: Account,
    contact: Contact,
    icp: ICPDefinition,
    judge: JudgeModel | None = None,
) -> ScoreResult:
    """Score an (Account, Contact) pair against an ICP definition.

    This is the async version. For synchronous usage, use ``score()``.

    Args:
        account: The account to evaluate.
        contact: The contact to evaluate.
        icp: The ICP definition to score against.
        judge: JudgeModel implementation for fuzzy criteria. None disables fuzzy.

    Returns:
        Complete ScoreResult with all contributions and explanation.
    """
    # For now, we use the first segment (single-segment).
    # Multi-segment would weight-average across segments.
    segment = icp.segments[0]
    config = icp.scoring

    # --- Step 1: Knockouts & Disqualifiers ---
    ko_disqualified, ko_results = evaluate_knockouts(account, contact, segment)
    dq_disqualified, dq_results = evaluate_disqualifiers(account, contact, segment)
    disqualified = ko_disqualified or dq_disqualified

    # --- Step 2: Rules scoring (raw weights; normalised in step 4) ---
    account_matched, account_total, account_contribs = evaluate_account_criteria(
        account, segment.account_criteria
    )
    contact_matched, contact_total, contact_contribs = evaluate_contact_criteria(
        contact, segment.contact_criteria
    )
    all_contributions: list[Contribution] = account_contribs + contact_contribs

    # --- Step 3: Fuzzy criteria ---
    fuzzy = FuzzyEval()
    if config.fuzzy.enabled and segment.fuzzy_criteria:
        fuzzy = await evaluate_fuzzy_criteria(
            account, contact, segment.fuzzy_criteria, judge
        )
    fuzzy_contribs: list[FuzzyContribution] = fuzzy.contributions

    # --- Step 4: Combination + Intent ---
    intent_points, intent_contribs = calculate_intent_points(
        account, segment.intent_boost, config.intent_max_boost
    )

    fit_score, account_score, contact_score = combine_scores(
        account_rules_matched=account_matched,
        account_rules_total=account_total,
        contact_rules_matched=contact_matched,
        contact_rules_total=contact_total,
        fuzzy_account_earned=fuzzy.account_earned,
        fuzzy_account_weight=fuzzy.account_weight,
        fuzzy_contact_earned=fuzzy.contact_earned,
        fuzzy_contact_weight=fuzzy.contact_weight,
        intent_points=intent_points,
        config=config,
    )

    # --- Step 5: Tier ---
    tier = assign_tier(fit_score, config, disqualified)

    # --- Build result ---
    result = ScoreResult(
        account_id=account.account_id,
        contact_id=contact.contact_id,
        icp_id=icp.meta.id,
        icp_version=icp.meta.version,
        scored_at=datetime.now(UTC),
        fit_score=round(fit_score, 2),
        tier=tier,
        disqualified=disqualified,
        account_score=round(account_score, 2),
        contact_score=round(contact_score, 2),
        intent_points=round(intent_points, 2),
        knockouts=ko_results,
        disqualifiers=dq_results,
        contributions=all_contributions,
        fuzzy=fuzzy_contribs,
        intent=intent_contribs,
    )

    result.explanation = _generate_explanation(result)
    return result


def score(
    account: Account,
    contact: Contact,
    icp: ICPDefinition,
    judge: JudgeModel | None = None,
) -> ScoreResult:
    """Synchronous wrapper around ``score_async``.

    Convenience for scripts and tests that don't need an event loop.
    """
    return asyncio.run(score_async(account, contact, icp, judge))

"""Combination and tier assignment — Steps 4 & 5 of the scoring pipeline (§6.4, §6.5).

Step 4: Combine account + contact scores, apply intent boost.
Step 5: Derive tier from fit_score via the ICP's tier config.
"""

from __future__ import annotations

from icp_engine.canonical.models import Account
from icp_engine.registry.schema import IntentBoost, ScoringConfig
from icp_engine.scoring.result import IntentContribution


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))


def calculate_intent_points(
    account: Account,
    intent_boosts: list[IntentBoost],
    max_boost: int,
) -> tuple[float, list[IntentContribution]]:
    """Calculate intent boost points from account signals (§6.4).

    Each signal whose type matches an intent_boost entry earns its points.
    The total is capped at ``max_boost``.

    Returns:
        (total_points, list of IntentContribution)
    """
    contributions: list[IntentContribution] = []
    total = 0.0

    # Build a lookup: signal_type → boost points
    boost_map = {ib.signal_type: ib.points for ib in intent_boosts}

    for signal in account.intent_signals:
        if signal.type in boost_map:
            points = boost_map[signal.type]
            total += points
            contributions.append(IntentContribution(
                signal_type=signal.type,
                points=points,
                detail=signal.detail,
            ))

    capped_total = min(total, max_boost)
    return capped_total, contributions


def _level_score(
    rules_matched: float,
    rules_total: float,
    fuzzy_earned: float,
    fuzzy_weight: float,
) -> float:
    """Normalise a single level (account/contact) over a shared pool (§6.4).

    The deterministic and fuzzy criteria share one denominator so a high-weight
    fuzzy criterion can dominate the level score, not just nudge it::

        score = clamp((rules_matched + fuzzy_earned) / (rules_total + fuzzy_weight) * 100)

    ``fuzzy_weight`` is 0 when the fuzzy step did not run, so the level falls
    back to deterministic-only normalisation (graceful degradation, §6.3).
    Returns 0 when the pool is empty.
    """
    total = rules_total + fuzzy_weight
    if total <= 0:
        return 0.0
    return _clamp((rules_matched + fuzzy_earned) / total * 100)


def combine_scores(
    account_rules_matched: float,
    account_rules_total: float,
    contact_rules_matched: float,
    contact_rules_total: float,
    fuzzy_account_earned: float,
    fuzzy_account_weight: float,
    fuzzy_contact_earned: float,
    fuzzy_contact_weight: float,
    intent_points: float,
    config: ScoringConfig,
) -> tuple[float, float, float]:
    """Combine sub-scores into the final fit_score (§6.4).

    Each level normalises its deterministic + fuzzy criteria over a single
    pool (see ``_level_score``); then::

        base = account_weight * account_score + contact_weight * contact_score
        fit_score = clamp(base + intent_points, 0, 100)

    Returns:
        (fit_score, account_score, contact_score)
    """
    account_score = _level_score(
        account_rules_matched, account_rules_total,
        fuzzy_account_earned, fuzzy_account_weight,
    )
    contact_score = _level_score(
        contact_rules_matched, contact_rules_total,
        fuzzy_contact_earned, fuzzy_contact_weight,
    )
    base = config.account_weight * account_score + config.contact_weight * contact_score
    fit_score = _clamp(base + intent_points)
    return fit_score, account_score, contact_score


def assign_tier(fit_score: float, config: ScoringConfig, disqualified: bool) -> str:
    """Derive tier from fit_score using the ICP's tier configuration (§6.5).

    If disqualified → always tier D.
    Otherwise, tiers are checked in descending order of min threshold.
    A score below the lowest tier threshold defaults to 'D'.
    """
    if disqualified:
        return "D"

    # Tiers are pre-sorted descending by _tiers_sorted_descending validator
    for tier_cfg in config.tiers:
        if fit_score >= tier_cfg.min:
            return tier_cfg.tier

    return "D"

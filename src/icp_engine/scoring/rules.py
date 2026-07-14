"""Rules evaluation — Steps 1 & 2 of the scoring pipeline (§6.1, §6.2).

Step 1: Knockouts and disqualifiers (gate).
Step 2: Deterministic score by rules (weighted criteria matching).
"""

from __future__ import annotations

from typing import Any

from icp_engine.canonical.models import Account, Contact
from icp_engine.registry.schema import (
    AccountCriterion,
    ContactCriterion,
    CriterionOp,
    Segment,
)
from icp_engine.scoring.result import (
    Contribution,
    DisqualifierResult,
    KnockoutResult,
)

# ---------------------------------------------------------------------------
# Operator evaluation
# ---------------------------------------------------------------------------

def _evaluate_op(op: CriterionOp, field_value: Any, expected: Any) -> bool:
    """Evaluate a comparison operator against a field value.

    Returns True if the condition is met.  Handles None field_value gracefully
    (always returns False — missing data can't satisfy a criterion).
    """
    if field_value is None:
        return False

    match op:
        case CriterionOp.EQ:
            return field_value == expected
        case CriterionOp.NEQ:
            return field_value != expected
        case CriterionOp.IN:
            if not isinstance(expected, list):
                return False
            # field_value could be a string or enum — compare as strings
            return str(field_value) in [str(v) for v in expected]
        case CriterionOp.NOT_IN:
            if not isinstance(expected, list):
                return True
            return str(field_value) not in [str(v) for v in expected]
        case CriterionOp.GTE:
            return field_value >= expected
        case CriterionOp.LTE:
            return field_value <= expected
        case CriterionOp.BETWEEN:
            if not isinstance(expected, list) or len(expected) != 2:
                return False
            return expected[0] <= field_value <= expected[1]
        case CriterionOp.CONTAINS_ANY:
            if not isinstance(expected, list):
                return False
            if not isinstance(field_value, list):
                return False
            field_set = {str(v) for v in field_value}
            return bool(field_set & {str(v) for v in expected})
        case _:
            return False


def _get_field_value(entity: Account | Contact, field: str) -> Any:
    """Safely extract a field value from a canonical model instance."""
    return getattr(entity, field, None)


# ---------------------------------------------------------------------------
# Step 1 — Knockouts & Disqualifiers (§6.1)
# ---------------------------------------------------------------------------

def evaluate_knockouts(
    account: Account,
    contact: Contact,
    segment: Segment,
) -> tuple[bool, list[KnockoutResult]]:
    """Evaluate all knockouts in a segment.

    A knockout is a must-have: if the condition is NOT met, the lead is
    disqualified.  Knockouts can reference either account or contact fields.

    Returns:
        (is_disqualified, list of KnockoutResult)
    """
    results: list[KnockoutResult] = []
    disqualified = False

    for ko in segment.knockouts:
        # Try account first, then contact
        field_val = _get_field_value(account, ko.field)
        if field_val is None:
            field_val = _get_field_value(contact, ko.field)

        passed = _evaluate_op(ko.op, field_val, ko.value)
        if not passed:
            disqualified = True

        results.append(KnockoutResult(
            field=ko.field,
            op=ko.op,
            value=ko.value,
            passed=passed,
            reason=ko.reason if not passed else "",
        ))

    return disqualified, results


def evaluate_disqualifiers(
    account: Account,
    contact: Contact,
    segment: Segment,
) -> tuple[bool, list[DisqualifierResult]]:
    """Evaluate all disqualifiers in a segment.

    A disqualifier fires if the condition IS met (opposite of knockout).

    Returns:
        (is_disqualified, list of DisqualifierResult)
    """
    results: list[DisqualifierResult] = []
    disqualified = False

    for dq in segment.disqualifiers:
        field_val = _get_field_value(account, dq.field)
        if field_val is None:
            field_val = _get_field_value(contact, dq.field)

        matched = _evaluate_op(dq.op, field_val, dq.value)
        if matched:
            disqualified = True

        results.append(DisqualifierResult(
            field=dq.field,
            op=dq.op,
            value=dq.value,
            matched=matched,
            reason=dq.reason if matched else "",
        ))

    return disqualified, results


# ---------------------------------------------------------------------------
# Step 2 — Deterministic score by rules (§6.2)
# ---------------------------------------------------------------------------

def evaluate_account_criteria(
    account: Account,
    criteria: list[AccountCriterion],
) -> tuple[float, float, list[Contribution]]:
    """Evaluate account-level scored criteria (§6.2).

    Returns:
        (matched_weight, total_weight, list of Contribution)

    Raw weights — NOT normalised here.  Normalisation to 0-100 happens in
    ``combiner.combine_scores`` (§6.4), where the deterministic pool is merged
    with the fuzzy pool so both share a single denominator.
    """
    contributions: list[Contribution] = []
    total_weight = float(sum(c.weight for c in criteria if c.kind == "scored"))
    matched_weight = 0.0

    for criterion in criteria:
        if criterion.kind != "scored":
            continue
        field_val = _get_field_value(account, criterion.field)
        match = _evaluate_op(criterion.op, field_val, criterion.value)
        points = float(criterion.weight) if match else 0.0
        matched_weight += points

        contributions.append(Contribution(
            level="account",
            field=criterion.field,
            expected=criterion.value,
            observed=field_val if not isinstance(field_val, list) else field_val,
            match=match,
            points=points,
        ))

    return matched_weight, total_weight, contributions


def evaluate_contact_criteria(
    contact: Contact,
    criteria: list[ContactCriterion],
) -> tuple[float, float, list[Contribution]]:
    """Evaluate contact-level scored criteria (§6.2).

    Same contract as ``evaluate_account_criteria``: returns raw
    ``(matched_weight, total_weight, contributions)``; normalisation is in §6.4.
    """
    contributions: list[Contribution] = []
    total_weight = float(sum(c.weight for c in criteria if c.kind == "scored"))
    matched_weight = 0.0

    for criterion in criteria:
        if criterion.kind != "scored":
            continue
        field_val = _get_field_value(contact, criterion.field)
        match = _evaluate_op(criterion.op, field_val, criterion.value)
        points = float(criterion.weight) if match else 0.0
        matched_weight += points

        contributions.append(Contribution(
            level="contact",
            field=criterion.field,
            expected=criterion.value,
            observed=field_val if not isinstance(field_val, list) else field_val,
            match=match,
            points=points,
        ))

    return matched_weight, total_weight, contributions

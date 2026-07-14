"""Stub implementations of adapters for testing (no real providers).

The StubJudgeModel returns configurable, deterministic scores so the scoring
pipeline can be tested end-to-end without any LLM call.
"""

from __future__ import annotations

from typing import Any

from icp_engine.adapters.base import FuzzyResult, JudgeModel


class StubJudgeModel(JudgeModel):
    """Deterministic JudgeModel for tests.

    Returns a fixed ``score_0_1`` and ``rationale`` for every call, or
    per-criterion overrides if configured.

    Usage::

        # Fixed score for all criteria
        judge = StubJudgeModel(default_score=0.7, default_rationale="Looks good.")

        # Per-criterion overrides (matched by substring in criterion_prompt)
        judge = StubJudgeModel(
            default_score=0.5,
            overrides={
                "digital_maturity": FuzzyResult(score_0_1=0.9, rationale="Strong signals."),
                "build_vs_buy": FuzzyResult(score_0_1=0.2, rationale="Mostly buys."),
            },
        )
    """

    def __init__(
        self,
        default_score: float = 0.5,
        default_rationale: str = "Stub evaluation.",
        overrides: dict[str, FuzzyResult] | None = None,
    ) -> None:
        self._default_score = default_score
        self._default_rationale = default_rationale
        self._overrides = overrides or {}

    async def evaluate(
        self,
        criterion_prompt: str,
        entity_data: dict[str, Any],
    ) -> FuzzyResult:
        # Check if any override key is a substring of the prompt
        for key, result in self._overrides.items():
            if key in criterion_prompt:
                return result

        return FuzzyResult(
            score_0_1=self._default_score,
            rationale=self._default_rationale,
        )

"""Scoring engine — pipeline de 5 pasos (§6, §7)."""

from icp_engine.scoring.pipeline import score
from icp_engine.scoring.result import ScoreResult

__all__ = ["ScoreResult", "score"]

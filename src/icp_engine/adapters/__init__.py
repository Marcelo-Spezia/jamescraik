"""Adapter interfaces and stubs (§12)."""

from icp_engine.adapters.base import (
    CrmGateway,
    EnrichmentProvider,
    FeedbackSource,
    IngestionSource,
    JudgeModel,
    ResultSink,
)
from icp_engine.adapters.stub import StubJudgeModel

__all__ = [
    "CrmGateway",
    "EnrichmentProvider",
    "FeedbackSource",
    "IngestionSource",
    "JudgeModel",
    "ResultSink",
    "StubJudgeModel",
]

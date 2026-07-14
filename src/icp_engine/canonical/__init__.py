"""Canonical models — Account, Contact, Signal (§4 del spec)."""

from icp_engine.canonical.enums import Department, FundingStage, Industry, Seniority, SignalStrength
from icp_engine.canonical.models import Account, Contact, Signal

__all__ = [
    "Account",
    "Contact",
    "Signal",
    "Industry",
    "Seniority",
    "Department",
    "FundingStage",
    "SignalStrength",
]

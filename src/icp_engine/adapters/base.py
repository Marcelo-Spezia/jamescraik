"""Abstract base classes for all external adapters (§12 of the spec).

The scoring engine depends ONLY on these interfaces — never on concrete
provider implementations.  This is what makes the solution swappable:
implementing a new adapter ≠ touching the engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from icp_engine.canonical.models import Account, Contact

# ---------------------------------------------------------------------------
# JudgeModel — LLM for fuzzy criteria (§6.3, §12)
# ---------------------------------------------------------------------------

class FuzzyResult(BaseModel):
    """Structured output from the JudgeModel for a single fuzzy criterion."""

    score_0_1: float  # 0.0 to 1.0
    rationale: str


class JudgeModel(ABC):
    """Interface for the LLM that evaluates fuzzy criteria.

    Configurable by env (principle: provider-agnostic).  The scoring pipeline
    calls ``evaluate()`` and never knows which model is behind it.
    """

    @abstractmethod
    async def evaluate(
        self,
        criterion_prompt: str,
        entity_data: dict[str, Any],
    ) -> FuzzyResult:
        """Evaluate a fuzzy criterion against entity data.

        Args:
            criterion_prompt: The question to evaluate (from ICP fuzzy_criteria).
            entity_data: Relevant fields from the Account or Contact.

        Returns:
            Structured result with score (0-1) and rationale.
            If data is insufficient, return score_0_1=0.0 with rationale
            explaining the gap (§6.3: never invent).
        """
        ...


# ---------------------------------------------------------------------------
# IngestionSource — bring in raw accounts/contacts (§12)
# ---------------------------------------------------------------------------

class IngestionSource(ABC):
    """Brings raw accounts/contacts from an external source and normalises
    them to the canonical model (§4)."""

    @abstractmethod
    async def fetch_accounts(self, **params: Any) -> list[Account]:
        ...

    @abstractmethod
    async def fetch_contacts(self, **params: Any) -> list[Contact]:
        ...


# ---------------------------------------------------------------------------
# EnrichmentProvider — fill gaps in canonical records (§12)
# ---------------------------------------------------------------------------

class EnrichmentProvider(ABC):
    """Completes missing fields that scoring needs."""

    @abstractmethod
    async def enrich_account(self, account: Account) -> Account:
        ...

    @abstractmethod
    async def enrich_contact(self, contact: Contact) -> Contact:
        ...


# ---------------------------------------------------------------------------
# CrmGateway — dedup and status check (§12)
# ---------------------------------------------------------------------------

class CrmGateway(ABC):
    """Checks if an account/contact already exists in the CRM."""

    @abstractmethod
    async def check_account(self, account: Account) -> dict[str, Any]:
        """Returns CRM status dict, e.g. {'exists': True, 'in_pipeline': False}."""
        ...


# ---------------------------------------------------------------------------
# ResultSink — persist/deliver ScoreResults (§12)
# ---------------------------------------------------------------------------

class ResultSink(ABC):
    """Persists or delivers ScoreResults downstream."""

    @abstractmethod
    async def send(self, results: list[dict[str, Any]]) -> None:
        ...


# ---------------------------------------------------------------------------
# FeedbackSource — read sales feedback records (§12)
# ---------------------------------------------------------------------------

class FeedbackSource(ABC):
    """Reads feedback records from sales (§10)."""

    @abstractmethod
    async def fetch(self, **filters: Any) -> list[dict[str, Any]]:
        ...

"""Canonical data models — Account, Contact, Signal (§4 of the spec).

These are the internal representation, independent of any tool or provider.
Every ingestion adapter normalises external data to these models.
Null fields are allowed where the spec indicates (gaps to be resolved by enrichment).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from icp_engine.canonical.enums import Department, FundingStage, Industry, Seniority, SignalStrength


class Signal(BaseModel):
    """Intent signal observed on an account (§4.4)."""

    type: str = Field(..., description="Signal type, e.g. job_post_revops, funding_round.")
    strength: SignalStrength = Field(..., description="strong | moderate | weak.")
    observed_at: date = Field(..., description="When the signal was observed (for temporal decay).")
    source: str = Field(..., description="Where the signal was detected.")
    detail: str = Field("", description="Observable text, e.g. 'Posted Head of Growth opening'.")


class Account(BaseModel):
    """Company entity in the canonical model (§4.1).

    Fields can be None when data is not yet available — enrichment is expected
    to fill gaps before scoring.  The ``raw`` field preserves the original
    provider payload for auditing.
    """

    account_id: str = Field(..., description="Stable internal canonical ID.")
    name: str = Field(..., description="Company name / trade name.")
    domain: str | None = Field(None, description="Web domain. Primary dedup key.")
    industry: Industry | None = Field(None, description="Normalised vertical (taxonomy).")
    employee_count: int | None = Field(None, ge=0, description="Headcount.")
    revenue_usd: int | None = Field(None, ge=0, description="Estimated annual revenue (USD).")
    country: str | None = Field(None, description="ISO-3166 country code.")
    region: str | None = Field(None, description="e.g. NA, LATAM, EMEA.")
    founded_year: int | None = Field(None, description="Year the company was founded.")
    funding_stage: FundingStage | None = Field(None, description="Current funding stage.")
    tech_stack: list[str] = Field(default_factory=list, description="Detected technologies.")
    intent_signals: list[Signal] = Field(
        default_factory=list, description="Observed intent signals."
    )
    source: str = Field("", description="Ingestion adapter that produced this record.")
    enriched_fields: list[str] = Field(
        default_factory=list,
        description="Which fields were completed by enrichment (traceability).",
    )
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Original provider payload (audit trail).",
    )


class Contact(BaseModel):
    """Person entity in the canonical model (§4.2).

    Linked to an Account via ``account_id``.  Email can be None in the POC.
    """

    contact_id: str = Field(..., description="Stable internal canonical ID.")
    account_id: str = Field(..., description="FK to Account.")
    full_name: str = Field(..., description="Full name.")
    title: str | None = Field(None, description="Literal job title.")
    seniority: Seniority = Field(Seniority.UNKNOWN, description="Normalised seniority level.")
    department: Department = Field(Department.OTHER, description="Normalised department.")
    country: str | None = Field(None)
    linkedin_url: str | None = Field(None)
    email: str | None = Field(None, description="Can be null in the POC.")
    source: str = Field("")
    enriched_fields: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

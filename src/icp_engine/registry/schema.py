"""Pydantic models for the ICP YAML schema (§5 of the spec).

These models validate the structure of an ICP definition file at load time.
An invalid ICP file is rejected with a clear error — it cannot be activated (§8).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Enums local to ICP schema
# ---------------------------------------------------------------------------

class CriterionOp(StrEnum):
    """Supported comparison operators for criteria (§5.3)."""

    EQ = "eq"
    NEQ = "neq"
    IN = "in"
    NOT_IN = "not_in"
    GTE = "gte"
    LTE = "lte"
    BETWEEN = "between"
    CONTAINS_ANY = "contains_any"


class CriterionKind(StrEnum):
    """Whether a criterion contributes to score or is a hard gate."""

    SCORED = "scored"
    KNOCKOUT = "knockout"


class ICPStatus(StrEnum):
    """Lifecycle status of an ICP definition (§8)."""

    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class ChangelogEntry(BaseModel):
    """A single entry in the ICP changelog (§9)."""

    version: str
    date: date
    note: str


class ICPMeta(BaseModel):
    """Identity and versioning metadata (§5.2)."""

    id: str = Field(..., description="Stable slug, e.g. icp-saas-midmarket.")
    name: str
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="Semver string.")
    status: ICPStatus = ICPStatus.DRAFT
    created: date
    updated: date
    author: str
    changelog: list[ChangelogEntry] = Field(default_factory=list)


class AccountCriterion(BaseModel):
    """A single account-level scored criterion (§5.3)."""

    field: str = Field(..., description="Canonical model field name (§4.1).")
    op: CriterionOp
    value: int | float | str | list = Field(..., description="Expected value(s).")
    weight: int = Field(..., ge=0, le=100)
    kind: CriterionKind = CriterionKind.SCORED


class ContactCriterion(BaseModel):
    """A single contact-level scored criterion (§5.3)."""

    field: str = Field(..., description="Canonical model field name (§4.2).")
    op: CriterionOp
    value: int | float | str | list = Field(..., description="Expected value(s).")
    weight: int = Field(..., ge=0, le=100)
    kind: CriterionKind = CriterionKind.SCORED


class FuzzyCriterion(BaseModel):
    """A criterion evaluated by the LLM JudgeModel (§6.3)."""

    id: str
    prompt: str = Field(..., description="Question for the LLM to evaluate.")
    weight: int = Field(..., ge=0)
    applies_to: Literal["account", "contact"] = "account"


class Knockout(BaseModel):
    """Must-have gate: if the condition is NOT met → disqualified (§5.3)."""

    field: str
    op: CriterionOp
    value: int | float | str | list
    reason: str


class Disqualifier(BaseModel):
    """If the condition IS met → disqualified (§5.3)."""

    field: str
    op: CriterionOp
    value: int | float | str | list
    reason: str


class IntentBoost(BaseModel):
    """Signal type that adds points to the final score (§5.3)."""

    signal_type: str
    points: int = Field(..., ge=0)


class Sourcing(BaseModel):
    """Hints de SOURCING para los adapters de ingestion (§12).

    NO afectan el scoring: sirven para acotar el pool de candidatos en la fuente
    (ej. palabras clave de sector que se mandan a la búsqueda de Apollo). Separa
    'a quién buscar' (sourcing) de 'cómo calificar lo que vuelve' (criterios).
    """

    industry_keywords: list[str] = Field(
        default_factory=list,
        description="Palabras clave de sector/vertical para filtrar la búsqueda.",
    )
    person_titles: list[str] = Field(
        default_factory=list,
        description="Títulos específicos del contacto a buscar (ej. 'Operating Partner').",
    )


class Segment(BaseModel):
    """A segment within the ICP, self-contained with its own criteria (§5.3)."""

    id: str
    name: str
    weight: float = Field(1.0, gt=0, description="Relative weight if multiple segments.")

    account_criteria: list[AccountCriterion] = Field(default_factory=list)
    contact_criteria: list[ContactCriterion] = Field(default_factory=list)
    fuzzy_criteria: list[FuzzyCriterion] = Field(default_factory=list)
    knockouts: list[Knockout] = Field(default_factory=list)
    disqualifiers: list[Disqualifier] = Field(default_factory=list)
    intent_boost: list[IntentBoost] = Field(default_factory=list)
    sourcing: Sourcing = Field(default_factory=Sourcing)


# ---------------------------------------------------------------------------
# Scoring config
# ---------------------------------------------------------------------------

class TierConfig(BaseModel):
    """Maps a minimum score to a tier label (§5.4)."""

    tier: str = Field(..., pattern=r"^[A-D]$")
    min: int = Field(..., ge=0, le=100)


class FuzzyConfig(BaseModel):
    """Config for the fuzzy (LLM) scoring step (§5.4)."""

    enabled: bool = True
    model_hint: str = ""


class ScoringConfig(BaseModel):
    """Top-level scoring configuration (§5.4)."""

    account_weight: float = Field(0.6, ge=0, le=1)
    contact_weight: float = Field(0.4, ge=0, le=1)
    intent_max_boost: int = Field(20, ge=0)
    tiers: list[TierConfig] = Field(default_factory=list)
    fuzzy: FuzzyConfig = Field(default_factory=FuzzyConfig)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> ScoringConfig:
        total = self.account_weight + self.contact_weight
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"account_weight + contact_weight must equal 1.0, got {total:.2f}"
            )
        return self

    @model_validator(mode="after")
    def _tiers_sorted_descending(self) -> ScoringConfig:
        """Ensure tiers are sorted by min descending so tier lookup works."""
        self.tiers = sorted(self.tiers, key=lambda t: t.min, reverse=True)
        return self


# ---------------------------------------------------------------------------
# Top-level ICP definition
# ---------------------------------------------------------------------------

class ICPDefinition(BaseModel):
    """Complete ICP definition loaded from YAML (§5.1).

    One file = one ICP.  Validated at load time; an invalid ICP cannot be
    activated (§8).
    """

    meta: ICPMeta
    segments: list[Segment] = Field(..., min_length=1)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)

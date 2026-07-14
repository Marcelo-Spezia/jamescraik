"""Controlled enums for the canonical model (§4.3).

These enums are the single source of truth for valid values of industry,
seniority, department, funding_stage, and signal strength. They mirror the
taxonomy YAML files in docs/taxonomies/ and are enforced by Pydantic validation
on Account, Contact, and Signal models.

If a new value is needed, update the taxonomy YAML first, then add it here.
"""

from enum import StrEnum


class Industry(StrEnum):
    """Normalised industry vertical (§4.3)."""

    SOFTWARE = "software"
    FINTECH = "fintech"
    HEALTHTECH = "healthtech"
    EDTECH = "edtech"
    ECOMMERCE = "ecommerce"
    MEDIA = "media"
    MANUFACTURING = "manufacturing"
    LOGISTICS = "logistics"
    ENERGY = "energy"
    REAL_ESTATE = "real_estate"
    TELECOM = "telecom"
    INSURANCE = "insurance"
    GOVERNMENT = "government"
    EDUCATION_K12 = "education_k12"
    NONPROFIT = "nonprofit"
    OTHER = "other"


class Seniority(StrEnum):
    """Contact seniority level (§4.2)."""

    C_LEVEL = "c_level"
    VP = "vp"
    DIRECTOR = "director"
    MANAGER = "manager"
    IC = "ic"
    UNKNOWN = "unknown"


class Department(StrEnum):
    """Contact department / functional area (§4.2)."""

    ENGINEERING = "engineering"
    PRODUCT = "product"
    DATA = "data"
    OPS = "ops"
    MARKETING = "marketing"
    SALES = "sales"
    EXEC = "exec"
    OTHER = "other"


class FundingStage(StrEnum):
    """Company funding stage (§4.1)."""

    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"
    BOOTSTRAPPED = "bootstrapped"
    PUBLIC = "public"
    UNKNOWN = "unknown"


class SignalStrength(StrEnum):
    """Intent signal strength (§4.4)."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"

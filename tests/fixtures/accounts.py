"""Factory functions for synthetic Account fixtures."""

from __future__ import annotations

from datetime import date

from icp_engine.canonical.enums import FundingStage, Industry, SignalStrength
from icp_engine.canonical.models import Account, Signal


def make_ideal_account(**overrides) -> Account:
    """A mid-market SaaS company that should score A against the example ICP."""
    defaults = dict(
        account_id="acc_ideal_001",
        name="Acme SaaS Inc.",
        domain="acmesaas.com",
        industry=Industry.SOFTWARE,
        employee_count=800,
        revenue_usd=50_000_000,
        country="US",
        region="NA",
        founded_year=2015,
        funding_stage=FundingStage.SERIES_B,
        tech_stack=["salesforce", "snowflake", "kubernetes"],
        intent_signals=[
            Signal(
                type="leadership_change",
                strength=SignalStrength.STRONG,
                observed_at=date(2026, 4, 15),
                source="fixture",
                detail="Nuevo VP Eng (hace 2 meses).",
            ),
        ],
        source="fixture",
    )
    defaults.update(overrides)
    return Account(**defaults)


def make_small_account(**overrides) -> Account:
    """A company too small — should trigger knockout (employee_count < 50)."""
    defaults = dict(
        account_id="acc_small_001",
        name="TinyStartup LLC",
        domain="tinystartup.io",
        industry=Industry.SOFTWARE,
        employee_count=30,
        revenue_usd=1_000_000,
        country="US",
        region="NA",
        founded_year=2023,
        funding_stage=FundingStage.SEED,
        tech_stack=["hubspot"],
        source="fixture",
    )
    defaults.update(overrides)
    return Account(**defaults)


def make_government_account(**overrides) -> Account:
    """A government org — should trigger disqualifier."""
    defaults = dict(
        account_id="acc_gov_001",
        name="Federal Agency X",
        domain="agency-x.gov",
        industry=Industry.GOVERNMENT,
        employee_count=5000,
        revenue_usd=0,
        country="US",
        region="NA",
        founded_year=1950,
        funding_stage=FundingStage.UNKNOWN,
        tech_stack=[],
        source="fixture",
    )
    defaults.update(overrides)
    return Account(**defaults)


def make_partial_match_account(**overrides) -> Account:
    """Matches some account criteria but not all — should score B/C."""
    defaults = dict(
        account_id="acc_partial_001",
        name="MediumCorp",
        domain="mediumcorp.com",
        industry=Industry.FINTECH,
        employee_count=150,  # below 200 — misses between(200,2000)
        revenue_usd=10_000_000,
        country="US",
        region="NA",
        founded_year=2018,
        funding_stage=FundingStage.GROWTH,
        tech_stack=["stripe"],  # no salesforce/hubspot match
        source="fixture",
    )
    defaults.update(overrides)
    return Account(**defaults)


def make_intent_rich_account(**overrides) -> Account:
    """Account with multiple intent signals for testing intent boost capping."""
    defaults = dict(
        account_id="acc_intent_001",
        name="SignalHeavy Corp",
        domain="signalheavy.com",
        industry=Industry.SOFTWARE,
        employee_count=500,
        revenue_usd=30_000_000,
        country="US",
        region="NA",
        founded_year=2016,
        funding_stage=FundingStage.SERIES_B,
        tech_stack=["salesforce", "hubspot"],
        intent_signals=[
            Signal(type="funding_round", strength=SignalStrength.STRONG,
                   observed_at=date(2026, 5, 1), source="fixture", detail="Series C raised."),
            Signal(type="leadership_change", strength=SignalStrength.MODERATE,
                   observed_at=date(2026, 5, 10), source="fixture", detail="New CTO."),
            Signal(type="job_post_revops", strength=SignalStrength.WEAK,
                   observed_at=date(2026, 5, 20), source="fixture", detail="Hiring RevOps lead."),
        ],
        source="fixture",
    )
    defaults.update(overrides)
    return Account(**defaults)

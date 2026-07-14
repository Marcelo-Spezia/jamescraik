"""Factory functions for synthetic Contact fixtures."""

from __future__ import annotations

from icp_engine.canonical.enums import Department, Seniority
from icp_engine.canonical.models import Contact


def make_ideal_contact(account_id: str = "acc_ideal_001", **overrides) -> Contact:
    """VP of Engineering — perfect persona match for example ICP."""
    defaults = dict(
        contact_id="ct_ideal_001",
        account_id=account_id,
        full_name="María García",
        title="VP of Engineering",
        seniority=Seniority.VP,
        department=Department.ENGINEERING,
        country="US",
        linkedin_url="https://linkedin.com/in/mariagarcia",
        source="fixture",
    )
    defaults.update(overrides)
    return Contact(**defaults)


def make_wrong_persona_contact(account_id: str = "acc_ideal_001", **overrides) -> Contact:
    """Sales IC — wrong department and seniority for engineering ICP."""
    defaults = dict(
        contact_id="ct_wrong_001",
        account_id=account_id,
        full_name="John Smith",
        title="Sales Representative",
        seniority=Seniority.IC,
        department=Department.SALES,
        country="US",
        source="fixture",
    )
    defaults.update(overrides)
    return Contact(**defaults)


def make_partial_contact(account_id: str = "acc_ideal_001", **overrides) -> Contact:
    """Director but in marketing — partial match (seniority yes, dept no)."""
    defaults = dict(
        contact_id="ct_partial_001",
        account_id=account_id,
        full_name="Ana López",
        title="Director of Marketing",
        seniority=Seniority.DIRECTOR,
        department=Department.MARKETING,
        country="US",
        source="fixture",
    )
    defaults.update(overrides)
    return Contact(**defaults)

"""Tests del ApolloIngestionSource: mapeo a canónico + end-to-end con scoring.

El cliente HTTP está mockeado: no se hace ninguna llamada real a Apollo.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from icp_engine.adapters.apollo import (
    ApolloIngestionSource,
    map_department,
    map_industry,
    map_seniority,
    org_to_account,
    person_to_contact,
)
from icp_engine.adapters.stub import StubJudgeModel
from icp_engine.canonical.enums import Department, Industry, Seniority
from icp_engine.registry.loader import load_icp
from icp_engine.scoring.pipeline import score

FIXTURE = Path(__file__).parent / "fixtures" / "apollo" / "people_search.json"
ICP = Path(__file__).parent.parent / "icp" / "tech-enabled-services.yaml"


def _load_people() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# --- Cliente httpx falso (inyectable) ---
class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict, get_payload: dict | None = None) -> None:
        self._payload = payload
        self._get_payload = get_payload or {}
        self.calls: list[dict] = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "body": json})
        return _FakeResponse(self._payload)

    async def get(self, url, headers=None, params=None):
        self.calls.append({"url": url, "headers": headers, "params": params})
        return _FakeResponse(self._get_payload)


# --- Mapeo de taxonomías ---
def test_taxonomy_mapping():
    assert map_industry("information technology & services") == Industry.SOFTWARE
    assert map_industry("government administration") == Industry.GOVERNMENT
    assert map_industry("primary/secondary education") == Industry.EDUCATION_K12
    assert map_industry("algo raro que no existe") == Industry.OTHER
    assert map_industry(None) is None
    assert map_seniority("vp") == Seniority.VP
    assert map_seniority("c_suite") == Seniority.C_LEVEL
    assert map_seniority(None) == Seniority.UNKNOWN
    assert map_department(["engineering"]) == Department.ENGINEERING
    assert map_department(["operations"]) == Department.OPS
    assert map_department(["unknownfn"]) == Department.OTHER


def test_org_to_account_maps_fields():
    org = _load_people()["people"][0]["organization"]
    acc = org_to_account(org)
    assert acc.account_id == "org_1"
    assert acc.domain == "esquire.example"
    assert acc.industry == Industry.SOFTWARE
    assert acc.employee_count == 900
    assert acc.region == "NA"  # United States → NA
    assert acc.tech_stack == ["Amazon AWS", "React", "Python"]
    assert acc.source == "apollo"
    assert acc.raw["id"] == "org_1"  # payload original preservado (auditoría)


def test_person_to_contact_maps_fields():
    person = _load_people()["people"][0]
    ct = person_to_contact(person, account_id="org_1")
    assert ct.contact_id == "ppl_1"
    assert ct.account_id == "org_1"
    assert ct.seniority == Seniority.VP
    assert ct.department == Department.ENGINEERING
    assert ct.email == "dana@esquire.example"


def test_fetch_leads_returns_normalized_pairs():
    client = _FakeClient(_load_people())
    src = ApolloIngestionSource(api_key="test-key", client=client)

    pairs = asyncio.run(src.fetch_leads(person_titles=["VP of Engineering"]))

    assert len(pairs) == 3
    acc, ct = pairs[0]
    assert acc.name == "Esquire Legal Services"
    assert ct.full_name == "Dana Cruz"
    # mandó la API key en el header documentado
    assert client.calls[0]["headers"]["X-Api-Key"] == "test-key"
    assert client.calls[0]["url"].endswith("/mixed_people/search")


def test_end_to_end_apollo_to_scoring():
    """Apollo (fixture) → canónico → ScoreResult, sin tocar la red."""
    client = _FakeClient(_load_people())
    src = ApolloIngestionSource(api_key="k", client=client)
    icp = load_icp(ICP)
    judge = StubJudgeModel(default_score=0.5)

    pairs = asyncio.run(src.fetch_leads())
    results = [score(acc, ct, icp, judge=judge) for acc, ct in pairs]

    by_account = {r.account_id: r for r in results}
    # La agencia de gobierno cae por disqualifier → tier D.
    gov = by_account["org_3"]
    assert gov.disqualified is True
    assert gov.tier == "D"
    # Todas produjeron un ScoreResult explicable.
    assert all(r.explanation for r in results)


def test_enrich_account_by_domain():
    enrich = {"organization": {
        "id": "org_e", "name": "Stripe", "primary_domain": "stripe.com",
        "industry": "information technology & services", "estimated_num_employees": 8000,
        "country": "United States", "technology_names": [".NET", "AWS"],
    }}
    client = _FakeClient({}, get_payload=enrich)
    src = ApolloIngestionSource(api_key="k", client=client)

    acc = asyncio.run(src.enrich_account_by_domain("stripe.com"))

    assert acc is not None
    assert acc.name == "Stripe"
    assert acc.employee_count == 8000
    assert acc.industry == Industry.SOFTWARE
    assert client.calls[0]["url"].endswith("/organizations/enrich")
    assert client.calls[0]["params"] == {"domain": "stripe.com"}


class _RoutingClient:
    """Devuelve payloads distintos según el endpoint (search vs match)."""

    def __init__(self, by_path: dict) -> None:
        self.by_path = by_path
        self.calls: list[str] = []

    def _payload(self, url: str) -> dict:
        for frag, payload in self.by_path.items():
            if frag in url:
                return payload
        return {}

    async def post(self, url, headers=None, json=None):
        self.calls.append(url)
        return _FakeResponse(self._payload(url))


def test_build_leads_search_then_enrich():
    """build_leads: api_search devuelve ids → match enriquece cada uno → pares."""
    search_payload = {"people": [{"id": "p1", "title": "VP Eng"}, {"id": "p2", "title": "CTO"}]}
    match_payload = {"person": {
        "id": "px", "name": "Real Person", "title": "VP Engineering", "seniority": "vp",
        "departments": ["engineering"], "email": "r@acme.com",
        "organization": {"id": "o1", "name": "Acme", "primary_domain": "acme.com",
                         "industry": "computer software", "estimated_num_employees": 600,
                         "country": "United States", "technology_names": ["AWS"]},
    }}
    client = _RoutingClient({"api_search": search_payload, "people/match": match_payload})
    src = ApolloIngestionSource(api_key="k", client=client)

    pairs = asyncio.run(src.build_leads(limit=5, person_seniorities=["vp"]))

    assert len(pairs) == 2  # 2 ids descubiertos → 2 enriquecidos
    acc, ct = pairs[0]
    assert acc.name == "Acme" and acc.employee_count == 600
    assert ct.seniority == Seniority.VP
    # llamó primero a search y luego a match (una vez por id)
    assert any("api_search" in c for c in client.calls)
    assert sum(1 for c in client.calls if "people/match" in c) == 2


def test_build_leads_respects_limit():
    search_payload = {"people": [{"id": f"p{i}"} for i in range(10)]}
    match_payload = {"person": {"id": "x", "name": "P", "organization": {"id": "o", "name": "Org"}}}
    client = _RoutingClient({"api_search": search_payload, "people/match": match_payload})
    src = ApolloIngestionSource(api_key="k", client=client)

    pairs = asyncio.run(src.build_leads(limit=3))

    assert len(pairs) == 3
    assert sum(1 for c in client.calls if "people/match" in c) == 3  # solo 3 enriquecidos


def test_match_lead_returns_account_and_contact():
    person = {
        "id": "p9", "name": "Brian Chesky", "title": "Co-founder, CEO",
        "seniority": "founder", "departments": ["c_suite"], "email": "brian@airbnb.com",
        "linkedin_url": "https://linkedin.com/in/brianchesky", "country": "United States",
        "organization": {
            "id": "o9", "name": "Airbnb", "primary_domain": "airbnb.com",
            "industry": "information technology & services", "estimated_num_employees": 7300,
            "country": "United States", "technology_names": ["AWS", "React"],
        },
    }
    client = _FakeClient({"person": person})
    src = ApolloIngestionSource(api_key="k", client=client)

    result = asyncio.run(
        src.match_lead(first_name="Brian", last_name="Chesky", domain="airbnb.com")
    )

    assert result is not None
    acc, ct = result
    assert acc.name == "Airbnb"
    assert acc.employee_count == 7300
    assert ct.full_name == "Brian Chesky"
    assert ct.account_id == "o9"  # contacto ligado a la cuenta enriquecida
    assert client.calls[0]["url"].endswith("/people/match")


def test_missing_api_key_raises():
    src = ApolloIngestionSource(api_key=None)
    src.api_key = None  # asegurar ausencia aun si hay env
    try:
        asyncio.run(src.fetch_accounts())
        raise AssertionError("debería haber fallado por falta de API key")
    except RuntimeError as e:
        assert "API key" in str(e)

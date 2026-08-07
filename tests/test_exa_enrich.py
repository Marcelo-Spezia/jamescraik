"""Tests del adapter de enrichment de Exa (ui/exa_enrich.py). Sin red."""

from __future__ import annotations

import exa_enrich


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Cliente httpx falso: post crea el run, get devuelve el estado. Registra llamadas."""

    def __init__(self, run_id="run_1", get_payload=None):
        self.run_id = run_id
        self.get_payload = get_payload or {}
        self.posts, self.gets = [], []

    def post(self, url, headers=None, json=None):
        self.posts.append({"url": url, "json": json})
        return _Resp({"id": self.run_id})

    def get(self, url, headers=None):
        self.gets.append(url)
        return _Resp(self.get_payload)


_LEAD = {"name": "Ana", "title": "CTO", "company": "Acme", "domain": "acme.com",
         "linkedin": "https://linkedin.com/in/ana"}


def test_get_source_stub_without_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    src = exa_enrich.get_source()
    assert isinstance(src, exa_enrich.StubExaSource)
    assert src.configured is False
    assert src.request_enrichment(_LEAD) is None
    assert src.poll("x") is None


def test_get_source_real_with_key(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "k")
    assert isinstance(exa_enrich.get_source(), exa_enrich.ExaEnrichmentSource)


def test_request_enrichment_fires_and_returns_run_id():
    fake = _FakeClient(run_id="run_42")
    src = exa_enrich.ExaEnrichmentSource(api_key="k", client=fake)
    rid = src.request_enrichment(_LEAD)
    assert rid == "run_42"
    body = fake.posts[0]["json"]
    assert body["effort"] == "medium"                      # effort FIJO, nunca 'auto'
    assert "acme.com" in body["query"] and "ana" in body["query"].lower()
    assert "outputSchema" in body


def test_request_enrichment_needs_domain_or_linkedin():
    src = exa_enrich.ExaEnrichmentSource(api_key="k", client=_FakeClient())
    assert src.request_enrichment({"name": "Sin ancla"}) is None   # sin domain ni linkedin


def test_poll_returns_none_while_running():
    fake = _FakeClient(get_payload={"id": "r", "status": "running"})
    src = exa_enrich.ExaEnrichmentSource(api_key="k", client=fake)
    assert src.poll("r") is None


def test_poll_parses_company_and_person():
    payload = {"id": "r", "status": "completed", "output": {"structured": {
        "company": {
            "funding": {"stage": "Series F", "amount_usd": 750000000,
                        "date": "2026-06-04", "source_url": "https://pr.example/f"},
            "hiring": {"value": "Contrata backend", "source_url": "https://acme.com/jobs"},
            "geo_expansion": {"value": None, "source_url": None}},
        "person": {
            "public_activity": {"value": "Dio una charla en QCon",
                                "source_url": "https://qcon.example/ana"},
            "content": {"value": None, "source_url": None},
            "career_moves": {"value": "Ascendió a CTO en 2025", "source_url": "https://x/ana"},
            "press": {"value": "", "source_url": ""}},
    }}}
    src = exa_enrich.ExaEnrichmentSource(api_key="k", client=_FakeClient(get_payload=payload))
    out = src.poll("r")
    assert out["status"] == "completed" and out["run_id"] == "r"
    assert out["company"]["funding"]["stage"] == "Series F"
    assert out["company"]["funding"]["src"] == "https://pr.example/f"
    assert out["company"]["hiring"] == {"v": "Contrata backend", "src": "https://acme.com/jobs"}
    assert out["company"]["geo"] is None                    # value null → None
    assert out["person"]["public_activity"]["v"] == "Dio una charla en QCon"
    assert out["person"]["career_moves"]["v"] == "Ascendió a CTO en 2025"
    assert out["person"]["content"] is None and out["person"]["press"] is None  # vacíos → None


def test_poll_tolerant_when_structured_missing():
    fake = _FakeClient(get_payload={"id": "r", "status": "completed", "output": {}})
    out = exa_enrich.ExaEnrichmentSource(api_key="k", client=fake).poll("r")
    assert out["company"]["funding"] is None and out["person"]["press"] is None  # no rompe

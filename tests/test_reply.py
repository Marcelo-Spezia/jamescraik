"""Tests de la generación de respuesta (ui/reply.py) con cliente mockeado."""

from __future__ import annotations

import json

import reply


class _Block:
    def __init__(self, t):
        self.type, self.text = "text", t


class _Resp:
    def __init__(self, t):
        self.content = [_Block(t)]


class _FakeClient:
    def __init__(self, payload):
        self._t = json.dumps(payload)
        self.calls = []

    class _M:
        def __init__(self, o):
            self.o = o

        def create(self, **kw):
            self.o.calls.append(kw)
            return _Resp(self.o._t)

    @property
    def messages(self):
        return _FakeClient._M(self)


_SENDER = {"slug": "rodrigo-bdr", "name": "Rodrigo", "role": "BDR",
           "credibility": "fintech: OnDeck, LendKey", "voice": "humilde, directo, de sector",
           "examples": ["Hola {name}, trabajo con CTOs en fintech..."]}
_LEAD = {"name": "Ana", "title": "CTO", "company": "Acme", "hook": "su ronda Serie B",
         "activity": {"summary": "Posteó sobre modernizar su core."}}


def test_generate_reply_fit_true_returns_reply():
    client = _FakeClient({"fit": True, "reason": "encaja con segmento", "reply": "Hola Ana, ..."})
    out = reply.generate_reply(_LEAD, _SENDER, lead_reply="Gracias, contame más.",
                               context="MS: partner de Anthropic.", first_message="Hola Ana,",
                               client=client, lang="es")
    assert out == {"fit": True, "reason": "encaja con segmento", "reply": "Hola Ana, ..."}
    call = client.calls[0]
    # el system lleva la VOZ del remitente y el contexto de MS
    assert "Rodrigo" in call["system"] and "humilde, directo" in call["system"]
    assert "partner de Anthropic" in call["system"]
    assert "output_config" in call        # salida estructurada (fit/reason/reply)
    user = call["messages"][0]["content"]
    assert "Gracias, contame más." in user            # la respuesta del lead entra
    assert "su ronda Serie B" in user                 # contexto del enrichment (insight)
    assert "Posteó sobre modernizar su core." in user  # actividad de Clay


def test_generate_reply_not_fit_returns_no_message():
    client = _FakeClient({"fit": False, "reason": "empresa < 50 empleados", "reply": None})
    out = reply.generate_reply(_LEAD, _SENDER, lead_reply="No, gracias.", client=client)
    assert out["fit"] is False and out["reply"] is None
    assert "50 empleados" in out["reason"]


def test_lead_context_from_enrichment():
    lead = {"name": "Ana", "company": "Acme", "hook": "ronda B",
            "exa": {"company": {"funding": {"stage": "Series B", "src": "u"}, "hiring": None,
                                "geo": None}, "person": {}}}
    ctx = reply.lead_context(lead)
    assert ctx["name"] == "Ana" and ctx["insights"]["hook"] == "ronda B"
    assert "web_facts" in ctx and "company_funding" in ctx["web_facts"]

"""Test de la generación de mensaje (ui/message.py) con cliente mockeado."""

from __future__ import annotations

import message


class _Block:
    def __init__(self, t):
        self.type, self.text = "text", t


class _Resp:
    def __init__(self, t):
        self.content = [_Block(t)]


class _FakeClient:
    def __init__(self, text):
        self._t = text
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


def test_generate_message_uses_lead_insights_context_and_lang():
    client = _FakeClient("Hola Maxi, vi que Lemon viene creciendo…")
    lead = {"name": "Maxi", "title": "CFO", "company": "Lemon", "tier": "A",
            "reason": "fintech mid-market", "hook": "mencioná su ronda Serie B",
            "value_prop_match": "MS moderniza su core"}
    out = message.generate_message(lead, value_prop="software a medida",
                                   context="MS gana en fintech.", client=client, lang="es")
    assert out == "Hola Maxi, vi que Lemon viene creciendo…"
    call = client.calls[0]
    assert "MS gana en fintech." in call["system"]        # contexto inyectado
    assert "software a medida" in call["system"]           # propuesta de valor
    assert "español" in call["system"].lower()             # directiva de idioma
    user = call["messages"][0]["content"]
    assert "mencioná su ronda Serie B" in user             # el hook va como munición
    assert "Lemon" in user


def test_generate_message_english_directive():
    client = _FakeClient("Hi Maxi,")
    message.generate_message({"name": "Maxi"}, client=client, lang="en")
    assert "English" in client.calls[0]["system"]

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


def test_generate_message_uses_linkedin_activity_as_hook():
    client = _FakeClient("Hola Maxi,")
    lead = {"name": "Maxi", "company": "Lemon",
            "activity": {"summary": "Posteó sobre su ronda Serie B esta semana."}}
    message.generate_message(lead, client=client, lang="es")
    user = client.calls[0]["messages"][0]["content"]
    assert "Serie B esta semana" in user          # la actividad viaja al prompt
    assert "HOOK" in user                          # marcada como hook principal


def test_generate_message_injects_campaign_hypothesis_and_ms_context():
    client = _FakeClient("Hola,")
    message.generate_message(
        {"name": "Ana", "company": "Acme"}, value_prop="modernización de plataformas",
        context="Making Sense: partner de Anthropic, nearshore.",
        hypothesis="CTOs de portcos PE con mandato de IA sin equipo interno.",
        client=client, lang="es")
    system = client.calls[0]["system"]
    assert "CTOs de portcos PE con mandato de IA" in system    # la HIPÓTESIS entra al prompt
    assert "modernización de plataformas" in system            # value_prop de la campaña
    assert "partner de Anthropic" in system                    # contexto de ventas de MS
    assert "Esta campaña" in system and "Making Sense" in system  # bloques etiquetados


def test_generate_message_uses_exa_facts():
    client = _FakeClient("Hola Ana,")
    lead = {"name": "Ana", "company": "Acme", "exa": {"company": {
        "funding": {"stage": "Series F", "amount_usd": 750000000, "date": "2026-06-04",
                    "src": "https://pr/x"},
        "hiring": {"v": "Contrata backend", "src": "https://acme/jobs"}, "geo": None},
        "person": {"public_activity": None, "content": None,
                   "career_moves": {"v": "Ascendió a CTO en 2025", "src": "https://x"},
                   "press": None}}}
    message.generate_message(lead, client=client, lang="es")
    user = client.calls[0]["messages"][0]["content"]
    assert "Series F" in user and "Contrata backend" in user   # facts de Exa como munición
    assert "Ascendió a CTO en 2025" in user                    # dato de persona
    assert "https://pr/x" not in user                          # sin URLs de fuente en el prompt
    assert "NO repitas" in user                                # instrucción de dedupe vs Clay


def test_generate_message_english_directive():
    client = _FakeClient("Hi Maxi,")
    message.generate_message({"name": "Maxi"}, client=client, lang="en")
    assert "English" in client.calls[0]["system"]

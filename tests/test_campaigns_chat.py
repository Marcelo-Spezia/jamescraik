"""Tests de campañas (persistencia) y del builder multi-turno (mocked)."""

from __future__ import annotations

import json

import campaigns
import chat_builder


# --- campaigns ---
def test_save_list_load_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(campaigns, "CAMPAIGNS_DIR", tmp_path / "campaigns")
    slug = campaigns.save_campaign({
        "name": "CFOs fintech AR",
        "sales_nav_filters": ["Geo: Argentina", "Title: CFO"],
        "rubric": "A: fintech…", "value_prop": "software a medida",
    })
    assert slug == "cfos-fintech-ar"
    lst = campaigns.list_campaigns()
    assert len(lst) == 1 and lst[0]["name"] == "CFOs fintech AR"
    loaded = campaigns.load_campaign(slug)
    assert loaded["rubric"] == "A: fintech…"
    assert loaded["sales_nav_filters"] == ["Geo: Argentina", "Title: CFO"]


def test_save_campaign_updates_same_slug(tmp_path, monkeypatch):
    monkeypatch.setattr(campaigns, "CAMPAIGNS_DIR", tmp_path / "campaigns")
    campaigns.save_campaign({"name": "X", "rubric": "v1"})
    campaigns.save_campaign({"name": "X", "rubric": "v2"})
    lst = campaigns.list_campaigns()
    assert len(lst) == 1 and lst[0]["rubric"] == "v2"  # mismo slug → actualiza


def test_delete_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(campaigns, "CAMPAIGNS_DIR", tmp_path / "campaigns")
    campaigns.save_campaign({"name": "Borrar esta", "rubric": "x"})
    assert len(campaigns.list_campaigns()) == 1
    assert campaigns.delete_campaign("borrar-esta") is True
    assert campaigns.list_campaigns() == []
    assert campaigns.delete_campaign("no-existe") is False  # idempotente


# --- chat_builder (cliente mockeado) ---
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


def test_chat_reply_strips_leading_assistant():
    client = _FakeClient("¿Qué ofrecés?")
    history = [{"role": "assistant", "content": chat_builder.INTRO},
               {"role": "user", "content": "Vendo dev de software a fintechs"}]
    reply = chat_builder.chat_reply(history, client)
    assert reply == "¿Qué ofrecés?"
    # la API arranca con 'user' (se sacó el assistant inicial)
    assert client.calls[0]["messages"][0]["role"] == "user"


def test_suggest_improvements_uses_context_and_results():
    client = _FakeClient("- Ajustá la rúbrica…")
    camp = {"name": "CFOs", "rubric": "A: fintech", "value_prop": "software",
            "sales_nav_filters": ["Argentina"]}
    results = [{"tier": "D", "company": "Trafigura", "reason": "commodities, no tech"},
               {"tier": "A", "company": "Lemon", "reason": "fintech"}]
    out = chat_builder.suggest_improvements(camp, context="MS gana en fintech.",
                                            results=results, client=client)
    assert out == "- Ajustá la rúbrica…"
    call = client.calls[0]
    assert "MS gana en fintech." in call["system"]          # contexto inyectado
    user = call["messages"][0]["content"]
    assert "A: fintech" in user                              # la rúbrica va en el prompt
    assert "Trafigura" in user                               # motivos de C/D
    assert "A:1" in user and "D:1" in user                   # distribución de tiers


def test_extract_campaign_structured():
    payload = {"name": "CFOs fintech AR",
               "sales_nav_filters": ["Argentina", "CFO", "50-2000 empleados"],
               "rubric": "A: CFO de fintech…", "value_prop": "software a medida",
               "enrichment_signals": [{"label": "Inversión / funding", "question": "¿ronda?"},
                                      {"label": "Presión regulatoria", "question": "¿compliance?"}]}
    client = _FakeClient(json.dumps(payload))
    camp = chat_builder.extract_campaign(
        [{"role": "user", "content": "fintechs AR, CFOs"}], client)
    assert camp["name"] == "CFOs fintech AR"
    assert camp["sales_nav_filters"] == ["Argentina", "CFO", "50-2000 empleados"]
    assert client.calls[0]["output_config"]["format"]["type"] == "json_schema"
    # Claude propone señales de enrichment; se normalizan (catálogo → key canónica)
    keys = [s["key"] for s in camp["enrichment_signals"]]
    assert "funding" in keys and "regulatory" in keys

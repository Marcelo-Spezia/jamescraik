"""Tests del asistente con IA (ui/ai_assist.py) con cliente mockeado (sin API)."""

from __future__ import annotations

import json

import ai_assist


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, payload):
        self.content = [_Block(json.dumps(payload))]


class _FakeMessages:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return _Resp(self._payload)


class _FakeClient:
    def __init__(self, payload):
        self.messages = _FakeMessages(payload)


def test_propose_icp_maps_to_simple_model():
    payload = {
        "name": "Aseguradoras tech-enabled",
        "size": [500, 5000],
        "regions": ["NA", "LATAM", "MARTE"],   # MARTE inválido → se filtra
        "seniority": ["c_level", "vp"],
        "departments": ["engineering", "product"],
        "ideal": [
            {"id": "tech_enabled", "importance": "imprescindible"},
            {"id": "business_services_fit", "importance": "importante"},
        ],
        "dealbreakers": ["too_small", "gov_edu"],
        "keywords": ["insurance", "insurance brokers"],
        "reasoning": "Servicios de seguros con plataformas propias.",
    }
    client = _FakeClient(payload)
    simple = ai_assist.propose_icp("Aseguradoras que usan tecnología propia", client=client)

    assert simple["name"] == "Aseguradoras tech-enabled"
    assert simple["keywords"] == ["insurance", "insurance brokers"]
    assert simple["size"] == [500, 5000]
    assert simple["regions"] == ["NA", "LATAM"]          # MARTE filtrado
    assert simple["dealbreakers"] == ["too_small", "gov_edu"]
    # las 3 características siempre presentes; build_intent sin importancia
    by_id = {i["id"]: i["importance"] for i in simple["ideal"]}
    assert by_id["tech_enabled"] == "imprescindible"
    assert by_id["business_services_fit"] == "importante"
    assert by_id["build_intent"] is None
    # usó salida estructurada
    assert client.messages.calls[0]["output_config"]["format"]["type"] == "json_schema"


def test_normalize_fixes_bad_size_and_empty():
    s = ai_assist.normalize({"size": [2000, 200], "ideal": [], "regions": [],
                             "seniority": [], "departments": [], "dealbreakers": [], "name": ""})
    assert s["size"] == [200, 2000]   # ordena min,max
    assert s["regions"] == ["NA"]      # default si vacío
    assert s["seniority"] == ["c_level"]
    assert s["name"] == "Nuevo ICP"
    assert len(s["ideal"]) == 3

"""Tests del enrichment de negocio (ui/enrich.py): señales configurables, dedup Apollo,
schema/prompt dinámicos, degradación."""

from __future__ import annotations

import json

import enrich


# --- LLM mockeado (salida en lote) ---
class _Block:
    def __init__(self, t):
        self.type, self.text = "text", t


class _Resp:
    def __init__(self, payload):
        self.content = [_Block(json.dumps(payload))]


class _RawResp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeClient:
    def __init__(self, payload):
        self._p = payload
        self.calls = []

    class _M:
        def __init__(self, o):
            self.o = o

        def create(self, **kw):
            self.o.calls.append(kw)
            return _Resp(self.o._p)

    @property
    def messages(self):
        return _FakeClient._M(self)


# --- Apollo mockeado ---
class _Acc:
    def __init__(self, raw, **kw):
        self.raw = raw
        self.employee_count = kw.get("employee_count")
        self.founded_year = kw.get("founded_year")
        self.tech_stack = kw.get("tech_stack") or []


class _FakeSource:
    def __init__(self):
        self.domains = []

    async def enrich_account_by_domain(self, domain):
        self.domains.append(domain)
        return _Acc({"total_funding_printed": "$10M", "latest_funding_stage": "series a",
                     "annual_revenue": 5000000, "industry": "financial services"},
                    employee_count=120, founded_year=2015, tech_stack=["React", "AWS"])


def _payload_for(signals, n):
    """Arma un payload que responde exactamente las keys de `signals` (activas)."""
    return {"results": [
        {"index": i, **{s["key"]: f"{s['key']}-{i}" for s in signals}} for i in range(n)]}


# --- catálogo / resolución de señales ---
def test_resolve_signals_maps_catalog_and_custom():
    sigs = enrich.resolve_signals(["Inversión / funding", {"label": "Presión regulatoria X",
                                                            "question": "¿regulación?"}])
    assert sigs[0]["key"] == "funding" and sigs[0]["source"] == "apollo"  # del catálogo
    assert sigs[1]["key"] == "presion_regulatoria_x"                      # a medida (slug)


def test_resolve_signals_excludes_core_and_dedups():
    sigs = enrich.resolve_signals(["Inversión / funding", "Inversión / funding",
                                   {"label": "Hook", "question": "x"}])
    keys = [s["key"] for s in sigs]
    assert keys == ["funding"]  # dedup + el núcleo (hook) se excluye


def test_active_signals_defaults_and_appends_core():
    active = enrich.active_signals(None)  # sin señales → defaults + núcleo
    keys = [s["key"] for s in active]
    assert keys[-2:] == ["value_prop_match", "hook"]   # núcleo al final
    assert "funding" in keys                            # default


def test_parse_custom_signals():
    out = enrich.parse_custom_signals("- Legacy: ¿tienen sistemas viejos?\nCrecimiento")
    assert out[0]["key"] == "legacy" and out[0]["question"] == "¿tienen sistemas viejos?"
    assert out[1]["label"] == "Crecimiento" and out[1]["question"] == "Crecimiento"


# --- enrichment dinámico ---
def test_enrich_leads_dynamic_signals_and_dedups_apollo():
    signals = [dict(enrich._CATALOG_BY_KEY["funding"]),
               dict(enrich._CATALOG_BY_KEY["regulatory"])]
    active = enrich.active_signals(signals)
    client = _FakeClient(_payload_for(active, 3))
    source = _FakeSource()
    leads = [{"name": "A", "company": "Lemon", "domain": "lemon.me"},
             {"name": "B", "company": "Lemon", "domain": "lemon.me"},   # misma empresa
             {"name": "C", "company": "Ualá", "domain": "uala.com.ar"}]
    out = enrich.enrich_leads(leads, "vp", context="ctx", client=client, source=source,
                              signals=signals)
    # solo las keys elegidas + núcleo, no los campos viejos hardcodeados
    assert "funding" in out[0] and "regulatory" in out[0]
    assert "value_prop_match" in out[0] and "hook" in out[0]
    assert "business_momentum" not in out[0]
    # dedup: 2 dominios únicos → 2 llamadas a Apollo
    assert sorted(source.domains) == ["lemon.me", "uala.com.ar"]
    # el schema pedido refleja las señales activas
    schema = client.calls[0]["output_config"]["format"]["schema"]
    item_props = schema["properties"]["results"]["items"]["properties"]
    assert "funding" in item_props and "regulatory" in item_props


def test_enrich_batch_caches_system_injects_context_and_signal_questions():
    signals = enrich.active_signals([dict(enrich._CATALOG_BY_KEY["funding"])])
    client = _FakeClient(_payload_for(signals, 1))
    out = enrich.enrich_batch([{"name": "A", "domain": "lemon.me"}], "propuesta X",
                              "contexto MS", client, {"lemon.me": {"total_funding": "$10M"}},
                              signals)
    assert out[0]["funding"] == "funding-0"
    call = client.calls[0]
    assert isinstance(call["system"], list)
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    sys_text = call["system"][0]["text"]
    assert "contexto MS" in sys_text and "propuesta X" in sys_text
    assert "funding" in sys_text                       # la pregunta de la señal está en el prompt
    assert "$10M" in call["messages"][0]["content"]    # señales de empresa en el user


def test_enrich_batch_splits_on_truncation():
    """Si la salida viene truncada (JSON incompleto), parte la tanda y reintexta; un
    lead que aun solo falla queda con insights vacíos, sin tumbar el proceso."""
    signals = enrich.active_signals([dict(enrich._CATALOG_BY_KEY["funding"])])
    keys = [s["key"] for s in signals]

    class _C:
        def __init__(self):
            self.calls = []

        class _M:
            def __init__(self, o):
                self.o = o

            def create(self, **kw):
                self.o.calls.append(kw)
                items = json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1])
                if len(items) > 1:                       # tanda >1 → truncada
                    return _RawResp('{"results":[{"index":0,"' + keys[0] + '":"tru')
                payload = {"results": [{"index": 0, **{k: f"{k}-0" for k in keys}}]}
                return _RawResp(json.dumps(payload))

        @property
        def messages(self):
            return _C._M(self)

    client = _C()
    leads = [{"name": "A", "domain": "a.com"}, {"name": "B", "domain": "b.com"}]
    out = enrich.enrich_batch(leads, "vp", "", client, {}, signals)
    assert len(out) == 2
    assert out[0][keys[0]] == f"{keys[0]}-0"             # resuelto lead por lead
    assert len(client.calls) >= 3                        # 1 tanda de 2 (falla) + 2 de 1


def test_enrich_degrades_without_domain():
    signals = enrich.active_signals(None)
    client = _FakeClient(_payload_for(signals, 1))
    source = _FakeSource()
    out = enrich.enrich_leads([{"name": "X", "company": "Acme"}],  # sin domain
                              "vp", client=client, source=source)
    assert source.domains == []                    # Apollo no se tocó
    assert "hook" in out[0]                         # el LLM igual sintetizó el núcleo


def test_extract_signals_pulls_business_not_tech():
    acc = _Acc({"total_funding_printed": "$20M", "latest_funding_stage": "series b",
                "annual_revenue": 9000000, "industry": "software"},
               employee_count=300, founded_year=2012, tech_stack=["Java", "Oracle"])
    sig = enrich._extract_signals(acc)
    assert sig["total_funding"] == "$20M"
    assert sig["latest_funding_stage"] == "series b"
    assert sig["employees"] == 300
    assert sig["tech_stack_evidence"] == ["Java", "Oracle"]  # stack solo como evidencia

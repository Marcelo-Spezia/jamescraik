"""Tests del backend Supabase de campañas y contexto (con un cliente falso, sin red).

Verifica que, con credenciales, save/list/load/delete van a Supabase (y no al disco
efímero, que es lo que hacía perder las campañas en el deploy).
"""

from __future__ import annotations

import campaigns
import context as ms_context


# ---------------------------------------------------------------------------
# Cliente Supabase falso: soporta el subconjunto de la query-builder que usamos.
# ---------------------------------------------------------------------------
class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self._op = None
        self._filters = []
        self._order = None
        self._data = None
        self._conflict = None

    def select(self, _cols):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def upsert(self, data, on_conflict=None):
        self._op, self._data, self._conflict = "upsert", data, on_conflict
        return self

    def delete(self):
        self._op = "delete"
        return self

    def execute(self):
        if self._op == "upsert":
            key = self._conflict
            existing = next((r for r in self.rows if r.get(key) == self._data.get(key)), None)
            if existing:
                existing.clear()
                existing.update(self._data)
            else:
                self.rows.append(dict(self._data))
            return _Result([dict(self._data)])
        sel = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters)]
        if self._op == "delete":
            for r in list(sel):
                self.rows.remove(r)
            return _Result([dict(r) for r in sel])
        if self._order:
            col, desc = self._order
            sel = sorted(sel, key=lambda r: r.get(col) or "", reverse=desc)
        return _Result([dict(r) for r in sel])


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list] = {}

    def table(self, name):
        return _Query(self.tables.setdefault(name, []))


def _use_supabase(monkeypatch, module, client):
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setattr(module, "_client", lambda: client)


# ---------------------------------------------------------------------------
# Campañas
# ---------------------------------------------------------------------------
def test_campaign_roundtrip_supabase(monkeypatch):
    fake = FakeSupabase()
    _use_supabase(monkeypatch, campaigns, fake)
    slug = campaigns.save_campaign({
        "name": "CFOs fintech AR", "sales_nav_filters": ["Geo: AR"],
        "rubric": "A: fintech", "value_prop": "software", "enrichment_signals": []})
    assert slug == "cfos-fintech-ar"
    # se guardó en la tabla de Supabase, NO en disco
    assert len(fake.tables["campaigns"]) == 1
    lst = campaigns.list_campaigns()
    assert len(lst) == 1 and lst[0]["name"] == "CFOs fintech AR"
    loaded = campaigns.load_campaign(slug)
    assert loaded["rubric"] == "A: fintech" and loaded["sales_nav_filters"] == ["Geo: AR"]
    assert campaigns.delete_campaign(slug) is True
    assert campaigns.list_campaigns() == []


def test_campaign_upsert_same_slug_supabase(monkeypatch):
    fake = FakeSupabase()
    _use_supabase(monkeypatch, campaigns, fake)
    campaigns.save_campaign({"name": "X", "rubric": "v1"})
    campaigns.save_campaign({"name": "X", "rubric": "v2"})
    lst = campaigns.list_campaigns()
    assert len(lst) == 1 and lst[0]["rubric"] == "v2"  # mismo slug → actualiza, no duplica


def test_delete_missing_campaign_supabase(monkeypatch):
    fake = FakeSupabase()
    _use_supabase(monkeypatch, campaigns, fake)
    assert campaigns.delete_campaign("no-existe") is False


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------
def test_context_roundtrip_supabase(monkeypatch):
    fake = FakeSupabase()
    _use_supabase(monkeypatch, ms_context, fake)
    assert ms_context.has_saved_context() is False   # todavía no hay fila
    ms_context.save_context("# MS\nDesarrollo de software.")
    assert ms_context.has_saved_context() is True
    assert "Desarrollo de software" in ms_context.load_context()
    # una sola fila key='making_sense', se actualiza in place
    ms_context.save_context("# MS v2")
    assert len(fake.tables["app_context"]) == 1
    assert ms_context.load_context() == "# MS v2"


def test_context_unsaved_falls_back_to_seed_supabase(monkeypatch):
    fake = FakeSupabase()
    _use_supabase(monkeypatch, ms_context, fake)
    monkeypatch.setattr(ms_context, "SEED_SOURCE", ms_context.PROJECT_ROOT / "no_existe.md")
    # sin fila guardada y sin semilla → devuelve el template, no rompe
    assert ms_context.load_context().startswith("# Contexto de Making Sense")

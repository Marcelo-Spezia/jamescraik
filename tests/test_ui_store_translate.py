"""Tests de la persistencia de búsquedas (store) y la traducción simple↔ICP."""

from __future__ import annotations

from pathlib import Path

import icp_translate as tr
import store
from icp_io import load_icp_dict, validate_icp_dict

REAL_ICP = Path(__file__).parent.parent / "icp" / "tech-enabled-services.yaml"


# --- store ---
def test_save_list_load_run(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    leads = [{"empresa": "Acme", "tier": "A", "fit": 90},
             {"empresa": "Sharks", "tier": "D", "fit": 40}]
    run_id = store.save_run("icp-x", "0.1.0", {"per_page": 5}, leads)

    runs = store.list_runs("icp-x")
    assert len(runs) == 1
    assert runs[0]["n_leads"] == 2
    assert runs[0]["tier_counts"] == {"A": 1, "D": 1}

    run = store.load_run("icp-x", run_id)
    assert run["leads"][0]["lead_id"]  # se asignó id estable


def test_feedback_and_fit_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    leads = [{"empresa": "A", "tier": "A", "fit": 90},
             {"empresa": "B", "tier": "B", "fit": 70},
             {"empresa": "C", "tier": "D", "fit": 30}]
    run_id = store.save_run("icp-y", "0.1.0", {}, leads)
    ids = [lead["lead_id"] for lead in store.load_run("icp-y", run_id)["leads"]]

    assert store.icp_fit_rate("icp-y") is None  # sin feedback aún
    store.set_feedback("icp-y", run_id, ids[0], "fit")
    store.set_feedback("icp-y", run_id, ids[1], "fit")
    store.set_feedback("icp-y", run_id, ids[2], "no_fit")
    assert store.icp_fit_rate("icp-y") == round(2 / 3 * 100, 1)  # 2 fit / 3

    store.set_feedback("icp-y", run_id, ids[0], None)  # limpiar
    assert store.icp_fit_rate("icp-y") == 50.0  # 1 fit / 2


# --- traducción ---
def test_icp_to_simple_extracts_fields():
    data = load_icp_dict(REAL_ICP)
    simple = tr.icp_to_simple(data)
    # el tamaño debe coincidir con el del archivo (sea cual sea su valor actual)
    emp = next(c for c in data["segments"][0]["account_criteria"]
               if c["field"] == "employee_count" and c["op"] == "between")
    assert simple["size"] == list(emp["value"])
    assert set(simple["regions"]) == {"NA", "LATAM"}
    assert "c_level" in simple["seniority"]
    # tech_enabled tiene peso 60 → imprescindible
    te = next(i for i in simple["ideal"] if i["id"] == "tech_enabled")
    assert te["importance"] == "imprescindible"
    # deal-breakers del ICP real
    assert "too_small" in simple["dealbreakers"]
    assert "gov_edu" in simple["dealbreakers"]
    assert "outside_region" in simple["dealbreakers"]


def test_roundtrip_simple_preserves_and_validates():
    data = load_icp_dict(REAL_ICP)
    # algo que la UI NO maneja debe sobrevivir (intent_boost, tech_stack)
    assert data["segments"][0]["intent_boost"]
    simple = tr.icp_to_simple(data)

    # el usuario baja la importancia de tech_enabled y saca un deal-breaker
    next(i for i in simple["ideal"] if i["id"] == "tech_enabled")["importance"] = "importante"
    simple["dealbreakers"].remove("gov_edu")
    simple["keywords"] = ["legal services", "law firms"]  # filtro de sector

    tr.apply_simple_to_icp(data, simple)

    ok, err = validate_icp_dict(data)
    assert ok, err
    seg = data["segments"][0]
    # tech_enabled ahora pesa 30 (importante)
    te = next(f for f in seg["fuzzy_criteria"] if f["id"] == "tech_enabled")
    assert te["weight"] == 30
    # gov/edu disqualifier removido; sigue el de región
    assert not any(d["field"] == "industry" for d in seg["disqualifiers"])
    assert any(d["field"] == "region" for d in seg["disqualifiers"])
    # PRESERVADO lo no manejado por la UI
    assert seg["intent_boost"]
    assert any(c["field"] == "tech_stack" for c in seg["account_criteria"])
    # las keywords de sector quedan en sourcing (filtro de búsqueda)
    assert seg["sourcing"]["industry_keywords"] == ["legal services", "law firms"]


def test_new_icp_is_valid():
    data = tr.new_icp_dict("Mi ICP de prueba", "2026-06-19")
    simple = tr.icp_to_simple(data)
    simple["ideal"][0]["importance"] = "imprescindible"  # tech_enabled
    tr.apply_simple_to_icp(data, simple)
    ok, err = validate_icp_dict(data)
    assert ok, err
    assert data["meta"]["id"] == "mi-icp-de-prueba"

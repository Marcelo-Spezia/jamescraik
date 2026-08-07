"""Tests del benchmark Apollo vs Exa: normalización + métricas. Sin red.

El paquete vive en scripts/bench (fuera del pythonpath de pytest) → lo agregamos acá.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bench import metrics, normalize  # noqa: E402


# ---------------------------------------------------------------------------
# employee_count
# ---------------------------------------------------------------------------
def test_norm_employee_count():
    assert normalize.norm_employee_count(120) == 120
    assert normalize.norm_employee_count("1,200") == 1200
    assert normalize.norm_employee_count("~50 employees") == 50
    assert normalize.norm_employee_count(0) is None
    assert normalize.norm_employee_count(None) is None
    assert normalize.norm_employee_count(True) is None  # bool no es headcount


def test_within_pct_boundary():
    assert normalize.within_pct(100, 120, 0.20) is True     # 20/120 = 0.167
    assert normalize.within_pct(100, 125, 0.20) is True     # 25/125 = 0.20 exacto
    assert normalize.within_pct(100, 126, 0.20) is False    # 26/126 = 0.206


def test_employee_band_boundary():
    assert normalize.employee_band(200) == "51-200"
    assert normalize.employee_band(201) == "201-500"        # cruza de banda por 1
    assert normalize.employee_band(9000) == "5000+"
    assert normalize.employee_band(None) is None


# ---------------------------------------------------------------------------
# country
# ---------------------------------------------------------------------------
def test_norm_country_variants():
    assert normalize.norm_country("USA") == "US"
    assert normalize.norm_country("United States") == "US"
    assert normalize.norm_country("US") == "US"
    assert normalize.norm_country("u.s.") == "US"
    assert normalize.norm_country("United Kingdom") == "GB"   # UK → GB (alpha-2 real)
    assert normalize.norm_country("fr") == "FR"
    assert normalize.norm_country("Freedonia") is None
    assert normalize.norm_country(None) is None


# ---------------------------------------------------------------------------
# stage
# ---------------------------------------------------------------------------
def test_norm_stage_formats():
    assert normalize.norm_stage("Series A") == "a"
    assert normalize.norm_stage("Series A-1") == "a-1"
    assert normalize.norm_stage("SEED") == "early"
    assert normalize.norm_stage("Pre Seed") == "early"
    assert normalize.norm_stage("pre-seed") == "early"
    assert normalize.norm_stage("Angel") == "early"
    assert normalize.norm_stage("Series B") == "b"
    assert normalize.norm_stage(None) is None


# ---------------------------------------------------------------------------
# date
# ---------------------------------------------------------------------------
def test_norm_date_precision():
    assert normalize.norm_date("2025-03-15") == ("2025-03-15", "day")
    assert normalize.norm_date("2025-03-15T00:00:00Z") == ("2025-03-15", "day")
    assert normalize.norm_date("2025-03") == ("2025-03-01", "month")
    assert normalize.norm_date("March 2025") == ("2025-03-01", "month")
    assert normalize.norm_date("2025") == ("2025-01-01", "year")
    assert normalize.norm_date("no date") == (None, None)


def test_norm_funding_and_amount():
    f = normalize.norm_funding({"stage": "Series A", "amount_usd": "$1,500,000", "date": "2024"})
    assert f == {"stage": "a", "amount_usd": 1500000, "date": "2024-01-01",
                 "date_precision": "year"}
    assert normalize.norm_funding({"stage": None, "amount_usd": None, "date": None}) is None
    assert normalize.norm_funding(None) is None


def test_days_since_injected_today():
    assert normalize.days_since("2024-01-01", date(2025, 1, 1)) == 366  # 2024 bisiesto


# ---------------------------------------------------------------------------
# métricas: fill_rate
# ---------------------------------------------------------------------------
def _rec(apollo, exa):
    return {"domain": "x.com", "company": "X", "apollo": apollo, "exa": exa}


def test_fill_rate_counts_unmatched_as_null():
    records = [
        _rec({"matched": True, "employee_count": 100, "industry": "Fintech",
              "hq_country": "US", "last_funding": {"stage": "a", "date": "2024-01-01"}},
             {"matched": True, "search_matched": True, "employee_count": 110,
              "industry": "Financial", "hq_country": "US", "last_funding": None}),
        _rec({"matched": False, "employee_count": None, "industry": None,
              "hq_country": None, "last_funding": None},
             {"matched": True, "search_matched": False, "employee_count": None,
              "industry": None, "hq_country": None,
              "last_funding": {"stage": "b", "date": "2025-01-01"}}),
    ]
    fa = metrics.fill_rate(records, "apollo")
    fe = metrics.fill_rate(records, "exa")
    assert fa["employee_count"] == 0.5      # solo 1 de 2 (el otro matched:false)
    assert fa["last_funding"] == 0.5
    assert fe["employee_count"] == 0.5      # el search_matched:false quedó null
    assert fe["last_funding"] == 0.5        # viene del agente aunque el search no matcheó


# ---------------------------------------------------------------------------
# métricas: agreement
# ---------------------------------------------------------------------------
def test_agreement_agree_disagree_and_missing():
    records = [
        # acuerdo: emp dentro ±20% y misma banda; país igual; stage igual; fecha dentro 90d
        _rec({"matched": True, "employee_count": 100, "hq_country": "US",
              "last_funding": {"stage": "a", "date": "2024-01-01"}},
             {"matched": True, "search_matched": True, "employee_count": 110, "hq_country": "US",
              "last_funding": {"stage": "a", "date": "2024-02-15"}}),
        # desacuerdo: emp fuera de rango y de banda; país distinto; stage distinto; fecha lejana
        _rec({"matched": True, "employee_count": 50, "hq_country": "US",
              "last_funding": {"stage": "a", "date": "2024-01-01"}},
             {"matched": True, "search_matched": True, "employee_count": 500, "hq_country": "GB",
              "last_funding": {"stage": "b", "date": "2025-06-01"}}),
        # falta de un lado: no entra en ningún denominador
        _rec({"matched": True, "employee_count": 200, "hq_country": None, "last_funding": None},
             {"matched": True, "search_matched": False, "employee_count": None,
              "hq_country": None, "last_funding": None}),
    ]
    ag = metrics.agreement(records)
    assert ag["employee_count"]["n"] == 2
    assert ag["employee_count"]["within_20pct"] == 0.5
    assert ag["employee_count"]["same_band"] == 0.5
    assert ag["hq_country"] == {"exact": 0.5, "n": 2}
    assert ag["last_funding_stage"] == {"exact": 0.5, "n": 2}
    assert ag["last_funding_date"] == {"within_90d": 0.5, "n": 2}


# ---------------------------------------------------------------------------
# métricas: staleness (today inyectado)
# ---------------------------------------------------------------------------
def test_apollo_funding_staleness_fixed_today():
    records = [
        _rec({"matched": True, "last_funding": {"stage": "a", "date": "2024-01-01"}}, {}),
        _rec({"matched": True, "last_funding": {"stage": "b", "date": "2023-01-01"}}, {}),
        _rec({"matched": True, "last_funding": {"stage": "c", "date": "2021-01-01"}}, {}),
        _rec({"matched": True, "last_funding": None}, {}),   # sin fecha → no cuenta
    ]
    st = metrics.apollo_funding_staleness(records, date(2025, 1, 1))
    # edades: 366, 731, 1461 días
    assert st["n"] == 3
    assert st["median_days"] == 731
    assert st["pct_over_365d"] == round(3 / 3, 4)   # los 3 superan 365
    assert st["pct_over_730d"] == round(2 / 3, 4)   # 731 y 1461


def test_exa_grounding():
    records = [
        _rec({}, {"matched": True, "search_matched": True,
                  "last_funding": {"stage": "a", "date": "2024-01-01"},
                  "hiring_signal": "contrata backend", "geo_expansion_signal": None,
                  "sources": {"last_funding": "https://a.com", "hiring_signal": "",
                              "geo_expansion_signal": ""}}),
    ]
    gr = metrics.exa_grounding(records)
    assert gr["non_null_fields"] == 2           # last_funding + hiring (geo es None)
    assert gr["with_source"] == 1               # solo last_funding trae url
    assert gr["overall_pct"] == 0.5


def test_percentile_helper():
    assert metrics._percentile([10], 50) == 10.0
    assert metrics._percentile([10, 20], 50) == 15.0
    assert metrics._percentile([], 50) is None

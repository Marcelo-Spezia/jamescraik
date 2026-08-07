"""Cálculo de métricas del benchmark sobre los resultados YA normalizados.

NO decide nada: solo produce números. Cada `record` tiene la forma:

    {
      "domain": str, "company": str,
      "apollo": {employee_count, industry, hq_country, last_funding, matched},
      "exa":    {employee_count, industry, hq_country, last_funding, matched,
                 hiring_signal, geo_expansion_signal, sources: {field: url}},
    }

donde `last_funding` = {stage, amount_usd, date, date_precision} | None y los valores
vienen normalizados por `normalize.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from bench import normalize

HEAD_TO_HEAD = ["employee_count", "industry", "hq_country", "last_funding"]
# Campos de Exa que llevan cita (grounding auditable).
GROUNDED_FIELDS = ["last_funding", "hiring_signal", "geo_expansion_signal"]


def _present(prov: dict[str, Any] | None, field: str) -> bool:
    """True si el proveedor matcheó y el campo tiene valor no-null."""
    if not prov or not prov.get("matched"):
        return False
    return prov.get(field) is not None


def _percentile(values: list[float], p: float) -> float | None:
    """Percentil p (0-100) por interpolación lineal. None si no hay datos."""
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    rank = (p / 100) * (len(xs) - 1)
    lo = int(rank)
    frac = rank - lo
    if lo + 1 >= len(xs):
        return float(xs[-1])
    return float(xs[lo] + (xs[lo + 1] - xs[lo]) * frac)


# ---------------------------------------------------------------------------
# 1. Fill rate
# ---------------------------------------------------------------------------
def fill_rate(records: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    """% de valores no-null por campo. `matched: false` cuenta como null."""
    total = len(records)
    out: dict[str, Any] = {"_total": total}
    for field in HEAD_TO_HEAD:
        filled = sum(1 for r in records if _present(r.get(provider), field))
        out[field] = round(filled / total, 4) if total else None
    return out


# ---------------------------------------------------------------------------
# 2. Agreement (solo donde ambos tienen valor)
# ---------------------------------------------------------------------------
def agreement(records: list[dict[str, Any]]) -> dict[str, Any]:
    emp_pct = emp_band = emp_n = 0
    country_hits = country_n = 0
    stage_hits = stage_n = 0
    date_hits = date_n = 0
    for r in records:
        a, e = r.get("apollo") or {}, r.get("exa") or {}
        # employee_count
        if _present(a, "employee_count") and _present(e, "employee_count"):
            emp_n += 1
            av, ev = a["employee_count"], e["employee_count"]
            if normalize.within_pct(av, ev, 0.20):
                emp_pct += 1
            if normalize.employee_band(av) == normalize.employee_band(ev):
                emp_band += 1
        # hq_country (exacto, ya normalizado a alpha-2)
        if _present(a, "hq_country") and _present(e, "hq_country"):
            country_n += 1
            if a["hq_country"] == e["hq_country"]:
                country_hits += 1
        # last_funding.stage / .date
        af, ef = a.get("last_funding"), e.get("last_funding")
        if _present(a, "last_funding") and _present(e, "last_funding"):
            if af.get("stage") and ef.get("stage"):
                stage_n += 1
                if af["stage"] == ef["stage"]:
                    stage_hits += 1
            if af.get("date") and ef.get("date"):
                date_n += 1
                delta = abs(normalize.days_since(af["date"], date(2000, 1, 1))
                            - normalize.days_since(ef["date"], date(2000, 1, 1)))
                if delta <= 90:
                    date_hits += 1

    def pct(h: int, n: int) -> float | None:
        return round(h / n, 4) if n else None

    return {
        "employee_count": {"within_20pct": pct(emp_pct, emp_n),
                           "same_band": pct(emp_band, emp_n), "n": emp_n},
        "hq_country": {"exact": pct(country_hits, country_n), "n": country_n},
        "last_funding_stage": {"exact": pct(stage_hits, stage_n), "n": stage_n},
        "last_funding_date": {"within_90d": pct(date_hits, date_n), "n": date_n},
        "industry": "no scoreado — ver bench_side_by_side.csv / bench_report.md",
    }


# ---------------------------------------------------------------------------
# 3. Apollo funding staleness — la métrica que decide
# ---------------------------------------------------------------------------
def apollo_funding_staleness(records: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Antigüedad (días) de los registros de funding no-null de Apollo."""
    ages: list[int] = []
    for r in records:
        a = r.get("apollo") or {}
        if _present(a, "last_funding") and a["last_funding"].get("date"):
            ages.append(normalize.days_since(a["last_funding"]["date"], today))
    n = len(ages)
    if not n:
        return {"n": 0, "median_days": None, "p25_days": None, "p75_days": None,
                "pct_over_365d": None, "pct_over_730d": None}
    return {
        "n": n,
        "median_days": _percentile(ages, 50),
        "p25_days": _percentile(ages, 25),
        "p75_days": _percentile(ages, 75),
        "pct_over_365d": round(sum(1 for d in ages if d > 365) / n, 4),
        "pct_over_730d": round(sum(1 for d in ages if d > 730) / n, 4),
    }


# ---------------------------------------------------------------------------
# 4. Exa grounding
# ---------------------------------------------------------------------------
def exa_grounding(records: list[dict[str, Any]]) -> dict[str, Any]:
    """% de campos no-null de Exa (con cita) que traen source_url no vacía."""
    non_null = with_source = 0
    per_field: dict[str, dict[str, int]] = {f: {"non_null": 0, "with_source": 0}
                                            for f in GROUNDED_FIELDS}
    for r in records:
        e = r.get("exa") or {}
        sources = e.get("sources") or {}
        for field in GROUNDED_FIELDS:
            if _present(e, field):
                non_null += 1
                per_field[field]["non_null"] += 1
                if (sources.get(field) or "").strip():
                    with_source += 1
                    per_field[field]["with_source"] += 1
    return {
        "overall_pct": round(with_source / non_null, 4) if non_null else None,
        "non_null_fields": non_null,
        "with_source": with_source,
        "by_field": per_field,
    }


# ---------------------------------------------------------------------------
# 5. Costo
# ---------------------------------------------------------------------------
EXA_SEARCH_COST = 0.007
EXA_AGENT_COST = 0.10


def cost(records: list[dict[str, Any]], exec_counts: dict[str, int]) -> dict[str, Any]:
    """Costo del dataset (lo que costaría enriquecerlo entero) + gasto real de este corrido.

    `exec_counts` = llamadas REALES hechas ahora (no servidas por caché):
        {"exa_search": int, "exa_agent": int, "apollo_credits": int}
    """
    n = len(records)
    dataset_exa = round(n * (EXA_SEARCH_COST + EXA_AGENT_COST), 4)
    spent_exa = round(exec_counts.get("exa_search", 0) * EXA_SEARCH_COST
                      + exec_counts.get("exa_agent", 0) * EXA_AGENT_COST, 4)
    return {
        "exa_usd": {"dataset": dataset_exa, "spent_this_run": spent_exa,
                    "unit_search": EXA_SEARCH_COST, "unit_agent": EXA_AGENT_COST},
        "apollo_credits": {"dataset": n, "spent_this_run": exec_counts.get("apollo_credits", 0),
                           "note": "Apollo factura por crédito (1 por dominio único), no en USD"},
    }


# ---------------------------------------------------------------------------
# 6. Wall-clock
# ---------------------------------------------------------------------------
def wall_clock(timings: dict[str, list[float]]) -> dict[str, Any]:
    """p50/p95 (segundos) por proveedor. `timings` = {provider: [secs por lead]}."""
    out: dict[str, Any] = {}
    for provider, secs in timings.items():
        clean = [s for s in secs if s is not None]
        out[provider] = {"p50_s": round(_percentile(clean, 50), 3) if clean else None,
                         "p95_s": round(_percentile(clean, 95), 3) if clean else None,
                         "n": len(clean)}
    return out

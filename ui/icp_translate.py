"""Traducción entre el modelo SIMPLE de la UI y el ICP técnico (YAML/dict).

La UI muestra preguntas en lenguaje normal (importancia, tamaño, regiones,
persona, deal-breakers). Acá se mapea eso a/desde el schema del motor
(criterios, ops, pesos, knockouts, disqualifiers).

Principio: al aplicar el modelo simple sobre un ICP existente se actualizan SOLO
los campos que la UI maneja y se PRESERVA el resto (tech_stack, intent_boost,
tiers, scoring weights) — sin pérdida de datos.
"""

from __future__ import annotations

from typing import Any

# Catálogo fijo de criterios difusos (con su prompt canónico para el LLM).
FUZZY_CATALOG: dict[str, dict[str, str]] = {
    "tech_enabled": {
        "label": "Usa tecnología como parte central de su servicio",
        "hint": "plataformas propias, apps, automatización, data",
        "prompt": (
            "¿La empresa usa software/tecnología como parte central de cómo entrega su "
            "servicio (plataformas propias, apps, automatización, data), más allá de "
            "herramientas de oficina genéricas?"
        ),
    },
    "business_services_fit": {
        "label": "Es una empresa de servicios profesionales",
        "hint": "legal, financiero, seguros, logística, staffing…",
        "prompt": (
            "¿Es una empresa de servicios profesionales / business services (legal, "
            "financieros, seguros, logística, staffing, salud, etc.), en vez de un "
            "producto puramente físico o un SaaS de consumo masivo?"
        ),
    },
    "build_intent": {
        "label": "Invierte en desarrollo de software a medida",
        "hint": "equipos de producto/ingeniería propios",
        "prompt": (
            "¿Hay señales de que invierte en desarrollo de software a medida o "
            "tiene/expande equipos de producto e ingeniería?"
        ),
    },
}

IMPORTANCE_WEIGHT = {"suma": 15, "importante": 30, "imprescindible": 60}

REGION_LABELS = {"NA": "Norteamérica", "LATAM": "Latinoamérica",
                 "EMEA": "Europa", "APAC": "Asia-Pacífico"}
SENIORITY_LABELS = {"c_level": "C-level / Fundadores", "vp": "VP",
                    "director": "Directores", "manager": "Gerentes"}
DEPARTMENT_LABELS = {"engineering": "Tecnología", "product": "Producto", "data": "Data",
                     "ops": "Operaciones", "marketing": "Marketing", "sales": "Ventas"}

_GOV_EDU = ["government", "education_k12"]


def weight_to_importance(weight: int) -> str:
    if weight >= 50:
        return "imprescindible"
    if weight >= 25:
        return "importante"
    return "suma"


def _find(criteria: list[dict], field: str) -> dict | None:
    return next((c for c in criteria if c.get("field") == field), None)


def icp_to_simple(data: dict[str, Any]) -> dict[str, Any]:
    """Extrae el modelo simple desde un ICP dict (para mostrar en el builder)."""
    seg = (data.get("segments") or [{}])[0]
    meta = data.get("meta", {})
    acc = seg.get("account_criteria", [])
    ct = seg.get("contact_criteria", [])
    kos = seg.get("knockouts", [])
    dqs = seg.get("disqualifiers", [])

    emp = _find(acc, "employee_count")
    size = list(emp["value"]) if emp and emp.get("op") == "between" else [200, 2000]
    region_c = _find(acc, "region")
    regions = list(region_c["value"]) if region_c else ["NA", "LATAM"]
    sen_c = _find(ct, "seniority")
    seniority = list(sen_c["value"]) if sen_c else ["c_level", "vp", "director"]
    dep_c = _find(ct, "department")
    departments = list(dep_c["value"]) if dep_c else ["engineering", "product", "data"]

    # Difusos → importancia (catálogo + cualquier extra que ya exista)
    ideal = []
    existing = {f["id"]: f for f in seg.get("fuzzy_criteria", [])}
    for fid, info in FUZZY_CATALOG.items():
        w = existing.get(fid, {}).get("weight")
        ideal.append({
            "id": fid, "label": info["label"], "hint": info["hint"],
            "importance": weight_to_importance(w) if w is not None else None,  # None = desactivado
        })

    dealbreakers = []
    if any(k.get("field") == "employee_count" and k.get("op") == "gte" for k in kos):
        dealbreakers.append("too_small")
    if any(d.get("field") == "industry" for d in dqs):
        dealbreakers.append("gov_edu")
    if any(d.get("field") == "region" and d.get("op") == "not_in" for d in dqs):
        dealbreakers.append("outside_region")

    sourcing = seg.get("sourcing") or {}
    keywords = list(sourcing.get("industry_keywords", []))
    titles = list(sourcing.get("person_titles", []))

    return {
        "name": meta.get("name", ""),
        "status": meta.get("status", "draft"),
        "size": size, "regions": regions,
        "seniority": seniority, "departments": departments,
        "ideal": ideal, "dealbreakers": dealbreakers,
        "keywords": keywords, "titles": titles,
    }


def _set_criterion(criteria: list[dict], field: str, op: str, value: Any, weight: int) -> None:
    c = _find(criteria, field)
    if c is None:
        criteria.append({"field": field, "op": op, "value": value,
                         "weight": weight, "kind": "scored"})
    else:
        c["op"], c["value"] = op, value
        c.setdefault("weight", weight)
        c.setdefault("kind", "scored")


def apply_simple_to_icp(data: dict[str, Any], simple: dict[str, Any]) -> dict[str, Any]:
    """Aplica el modelo simple sobre el ICP dict, preservando lo no manejado."""
    meta = data.setdefault("meta", {})
    meta["name"] = simple.get("name", meta.get("name", ""))
    meta["status"] = simple.get("status", meta.get("status", "draft"))

    seg = data.setdefault("segments", [{}])[0]
    acc = seg.setdefault("account_criteria", [])
    ct = seg.setdefault("contact_criteria", [])

    _set_criterion(acc, "employee_count", "between", list(simple["size"]), 15)
    _set_criterion(acc, "region", "in", list(simple["regions"]), 10)
    _set_criterion(ct, "seniority", "in", list(simple["seniority"]), 50)
    _set_criterion(ct, "department", "in", list(simple["departments"]), 50)

    # Difusos: peso según importancia; desactivado (None) → se quita.
    fuzzy = {f["id"]: f for f in seg.get("fuzzy_criteria", [])}
    new_fuzzy = []
    for item in simple.get("ideal", []):
        imp = item.get("importance")
        if imp is None:
            continue
        fid = item["id"]
        prompt = fuzzy.get(fid, {}).get("prompt") or FUZZY_CATALOG.get(fid, {}).get("prompt", "")
        new_fuzzy.append({"id": fid, "prompt": prompt,
                          "weight": IMPORTANCE_WEIGHT[imp], "applies_to": "account"})
    # conservar difusos fuera del catálogo (avanzados)
    for fid, f in fuzzy.items():
        if fid not in FUZZY_CATALOG and not any(n["id"] == fid for n in new_fuzzy):
            new_fuzzy.append(f)
    seg["fuzzy_criteria"] = new_fuzzy

    # Deal-breakers
    db = set(simple.get("dealbreakers", []))
    kos = [k for k in seg.get("knockouts", [])
           if not (k.get("field") == "employee_count" and k.get("op") == "gte")]
    if "too_small" in db:
        kos.append({"field": "employee_count", "op": "gte", "value": 50,
                    "reason": "Muy chica (<50 empl.): el ACV no justifica el ciclo de venta."})
    seg["knockouts"] = kos

    dqs = [d for d in seg.get("disqualifiers", [])
           if d.get("field") not in ("industry", "region")]
    if "gov_edu" in db:
        dqs.append({"field": "industry", "op": "in", "value": list(_GOV_EDU),
                    "reason": "Gobierno / educación: ciclos y compliance fuera de fit."})
    if "outside_region" in db:
        dqs.append({"field": "region", "op": "not_in", "value": list(simple["regions"]),
                    "reason": "Fuera de las geografías que cubre el equipo."})
    seg["disqualifiers"] = dqs

    # Sourcing: palabras clave de sector + títulos específicos (filtran la búsqueda).
    seg["sourcing"] = {
        "industry_keywords": list(simple.get("keywords", [])),
        "person_titles": list(simple.get("titles", [])),
    }

    return data


def new_icp_dict(name: str, today: str) -> dict[str, Any]:
    """ICP base nuevo (con tiers y scoring por defecto) para arrancar en el builder."""
    slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-") or "nuevo-icp"
    return {
        "meta": {"id": slug, "name": name, "version": "0.1.0", "status": "draft",
                 "created": today, "updated": today, "author": "ui",
                 "changelog": [{"version": "0.1.0", "date": today,
                                "note": "Creado desde el builder."}]},
        "segments": [{
            "id": "core", "name": "Core", "weight": 1.0,
            "account_criteria": [], "contact_criteria": [], "fuzzy_criteria": [],
            "knockouts": [], "disqualifiers": [], "intent_boost": [],
        }],
        "scoring": {
            "account_weight": 0.6, "contact_weight": 0.4, "intent_max_boost": 20,
            "tiers": [{"tier": "A", "min": 80}, {"tier": "B", "min": 65}, {"tier": "C", "min": 45}],
            "fuzzy": {"enabled": True},
        },
    }

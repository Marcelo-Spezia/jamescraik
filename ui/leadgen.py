"""Orquestación de armado de listas para la UI.

ICP (dict) → query de Apollo → People Search + enrich → scoring. Devuelve dicts
listos para renderizar. Sin Streamlit acá (testeable). Las llamadas reales a
Apollo/Claude se hacen solo al ejecutar `build_and_score`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv() -> None:
    """Carga .env de la raíz (KEY=valor) sin pisar variables ya seteadas."""
    env = PROJECT_ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_query_from_icp(data: dict[str, Any], per_page: int = 10) -> dict[str, Any]:
    """Traduce los criterios del ICP a parámetros de Apollo People Search.

    Nota: NO se filtra por departamento (Apollo usa su taxonomía propia y nuestros
    valores devuelven 0); el departamento se evalúa al scorear el contacto.
    """
    seg = (data.get("segments") or [{}])[0]
    params: dict[str, Any] = {"per_page": per_page}

    # Sourcing: palabras clave de sector → filtro de keywords en Apollo.
    # Esto hace que un ICP de "legal services" NO traiga fintech.
    sourcing = seg.get("sourcing") or {}
    keywords = sourcing.get("industry_keywords", [])
    if keywords:
        params["q_organization_keyword_tags"] = list(keywords)
    # Títulos específicos del contacto (ej. 'Operating Partner') → filtro de persona.
    titles = sourcing.get("person_titles", [])
    if titles:
        params["person_titles"] = list(titles)

    for c in seg.get("account_criteria", []):
        if c.get("field") == "employee_count" and c.get("op") == "between":
            lo, hi = c["value"]
            params["organization_num_employees_ranges"] = [f"{lo},{hi}"]
        if c.get("field") == "region" and c.get("op") == "in":
            locs = []
            if "NA" in c["value"]:
                locs += ["United States", "Canada"]
            if "LATAM" in c["value"]:
                locs += ["Mexico", "Brazil", "Argentina", "Chile", "Colombia"]
            if locs:
                params["organization_locations"] = locs

    for c in seg.get("contact_criteria", []):
        if c.get("field") == "seniority" and c.get("op") == "in":
            inv = {"c_level": "c_suite", "vp": "vp", "director": "director"}
            params["person_seniorities"] = [inv.get(v, v) for v in c["value"]]

    return params


def org_search_query(data: dict[str, Any], per_page: int = 10) -> dict[str, Any]:
    """Query para búsqueda de EMPRESAS: igual que la de personas pero sin filtros
    de persona (Organization Search no los acepta)."""
    full = build_query_from_icp(data, per_page=per_page)
    return {k: v for k, v in full.items() if not k.startswith("person_")}


def tier_from_score(score: float, data: dict[str, Any], disqualified: bool) -> str:
    """Tier a partir de un score (para el fit de EMPRESA, que no tiene contacto)."""
    if disqualified:
        return "D"
    tiers = sorted(data.get("scoring", {}).get("tiers", []),
                   key=lambda t: t["min"], reverse=True)
    for t in tiers:
        if score >= t["min"]:
            return t["tier"]
    return "D"


_KNOWN_COLS = {"email", "first_name", "last_name", "name", "company",
               "organization", "organization_name", "domain", "website",
               "linkedin", "linkedin_url"}


def parse_list(text: str) -> list[dict[str, str]]:
    """Parsea una lista pegada → filas dict.

    Soporta: CSV con header (email, name, first_name, last_name, company, domain…),
    o sin header (un email por línea, o 'Nombre, Empresa' por línea).
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip().lower() for h in lines[0].split(",")]
    if any(h in _KNOWN_COLS for h in header):
        rows = []
        for ln in lines[1:]:
            vals = [v.strip() for v in ln.split(",")]
            rows.append({header[i]: vals[i] for i in range(min(len(header), len(vals)))})
        return rows
    rows = []
    for ln in lines:
        parts = [p.strip() for p in ln.split(",")]
        if "@" in parts[0]:
            rows.append({"email": parts[0]})
        elif len(parts) >= 2:
            rows.append({"name": parts[0], "company": parts[1]})
        else:
            rows.append({"name": parts[0]})
    return rows


def row_to_identifiers(row: dict[str, Any]) -> dict[str, str]:
    """De una fila de la lista → identificadores para Apollo people/match."""
    r = {k.strip().lower(): (str(v).strip() if v is not None else "") for k, v in row.items()}
    ident: dict[str, str] = {}
    if r.get("email"):
        ident["email"] = r["email"]
    if r.get("linkedin_url") or r.get("linkedin"):
        ident["linkedin_url"] = r.get("linkedin_url") or r.get("linkedin")
    if r.get("first_name"):
        ident["first_name"] = r["first_name"]
    if r.get("last_name"):
        ident["last_name"] = r["last_name"]
    if r.get("name") and not (r.get("first_name") or r.get("last_name")):
        ident["name"] = r["name"]
    dom = r.get("domain") or r.get("website")
    if dom:
        ident["domain"] = dom
    org = r.get("company") or r.get("organization") or r.get("organization_name")
    if org:
        ident["organization_name"] = org
    return ident


def _build_judge():
    """JudgeModel real si hay ANTHROPIC_API_KEY; si no, stub (con aviso)."""
    if os.getenv("ANTHROPIC_API_KEY"):
        from icp_engine.adapters.anthropic_judge import build_judge_from_env
        return build_judge_from_env(), "Claude (real)"
    from icp_engine.adapters.stub import StubJudgeModel
    return StubJudgeModel(default_score=0.5), "simulado (sin ANTHROPIC_API_KEY)"


async def build_and_score(data: dict[str, Any], pool: int = 12,
                           top: int | None = None) -> dict[str, Any]:
    """Arma y califica la lista. Devuelve {query, judge_label, leads:[...]}.

    OJO: hace llamadas reales — Apollo (créditos al enriquecer) + Claude.
    """
    from icp_engine.adapters.apollo import ApolloIngestionSource
    from icp_engine.registry.schema import ICPDefinition
    from icp_engine.scoring.pipeline import score_async

    icp = ICPDefinition(**data)  # valida de paso
    query = build_query_from_icp(data, per_page=max(pool, 5))
    source = ApolloIngestionSource()
    judge, judge_label = _build_judge()

    pairs = await source.build_leads(limit=pool, **query)
    leads: list[dict[str, Any]] = []
    for acc, ct in pairs:
        r = await score_async(acc, ct, icp, judge=judge)
        leads.append({
            "empresa": acc.name,
            "industria": acc.industry.value if acc.industry else None,
            "empleados": acc.employee_count,
            "region": acc.region,
            "contacto": ct.full_name,
            "titulo": ct.title,
            "seniority": ct.seniority.value,
            "fit": r.fit_score,
            "tier": r.tier,
            "descalificado": r.disqualified,
            "explicacion": r.explanation,
            "fuzzy": [
                {"id": f.id, "score": f.score_0_1, "rationale": f.rationale}
                for f in r.fuzzy
            ],
        })
    leads.sort(key=lambda x: x["fit"], reverse=True)
    if top:
        leads = leads[:top]
    return {"query": query, "judge_label": judge_label, "leads": leads}


async def score_list(data: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Califica una LISTA dada (no busca): enriquece cada persona con Apollo y la
    puntúa contra el ICP. Los que Apollo no encuentra quedan marcados, no se pierden.

    OJO: cada fila enriquecida consume créditos de Apollo + tokens de Claude.
    """
    from icp_engine.adapters.apollo import ApolloIngestionSource
    from icp_engine.registry.schema import ICPDefinition
    from icp_engine.scoring.pipeline import score_async

    icp = ICPDefinition(**data)
    source = ApolloIngestionSource()
    judge, judge_label = _build_judge()

    leads: list[dict[str, Any]] = []
    for row in rows:
        ident = row_to_identifiers(row)
        label = row.get("email") or row.get("name") or " ".join(
            x for x in [row.get("first_name"), row.get("last_name")] if x) or "(fila)"
        pair = None
        if ident:
            try:
                pair = await source.match_lead(**ident)
            except Exception:  # noqa: BLE001 - una fila que falla no corta el resto
                pair = None
        if pair is None:
            leads.append({"empresa": row.get("company") or "—", "contacto": str(label),
                          "fit": 0, "tier": "?", "descalificado": False,
                          "unmatched": True, "fuzzy": []})
            continue
        acc, ct = pair
        r = await score_async(acc, ct, icp, judge=judge)
        leads.append({
            "empresa": acc.name, "industria": acc.industry.value if acc.industry else None,
            "empleados": acc.employee_count, "region": acc.region,
            "contacto": ct.full_name, "titulo": ct.title, "seniority": ct.seniority.value,
            "fit": r.fit_score, "tier": r.tier, "descalificado": r.disqualified,
            "explicacion": r.explanation,
            "fuzzy": [{"id": f.id, "score": f.score_0_1, "rationale": f.rationale}
                      for f in r.fuzzy],
        })
    leads.sort(key=lambda x: (not x.get("unmatched"), x.get("fit", 0)), reverse=True)
    return {"query": {"lista": f"{len(rows)} filas"}, "judge_label": judge_label, "leads": leads}


async def build_and_score_companies(data: dict[str, Any], pool: int = 12,
                                    top: int | None = None) -> dict[str, Any]:
    """Arma y califica EMPRESAS (sin contacto): Org Search → enrich → score de cuenta.

    El 'fit' es el score de EMPRESA (account_score) y el tier sale de ese score.
    Califica `pool` candidatos y, si se pasa `top`, devuelve solo los mejores N.
    OJO: hace llamadas reales — Apollo (créditos al enriquecer) + Claude.
    """
    from icp_engine.adapters.apollo import ApolloIngestionSource
    from icp_engine.canonical.models import Contact
    from icp_engine.registry.schema import ICPDefinition
    from icp_engine.scoring.pipeline import score_async

    icp = ICPDefinition(**data)
    query = org_search_query(data, per_page=max(pool, 5))
    source = ApolloIngestionSource()
    judge, judge_label = _build_judge()

    accounts = await source.build_companies(limit=pool, **query)
    neutral = Contact(contact_id="-", account_id="-", full_name="—", source="apollo")
    leads: list[dict[str, Any]] = []
    for acc in accounts:
        r = await score_async(acc, neutral, icp, judge=judge)
        leads.append({
            "empresa": acc.name,
            "industria": acc.industry.value if acc.industry else None,
            "empleados": acc.employee_count, "region": acc.region,
            "contacto": "—", "titulo": acc.domain or "", "seniority": "",
            "fit": r.account_score, "tier": tier_from_score(r.account_score, data, r.disqualified),
            "descalificado": r.disqualified,
            "fuzzy": [{"id": f.id, "score": f.score_0_1, "rationale": f.rationale}
                      for f in r.fuzzy],
        })
    leads.sort(key=lambda x: x["fit"], reverse=True)
    if top:
        leads = leads[:top]
    return {"query": query, "judge_label": judge_label, "leads": leads}

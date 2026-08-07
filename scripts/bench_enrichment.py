#!/usr/bin/env python
"""Benchmark descartable: Apollo vs Exa sobre las MISMAS empresas, mismos 4 campos.

Genera datos para DECIDIR (no migra nada, no concluye nada). Corre los dos proveedores,
cachea las respuestas crudas y produce métricas + tabla lado a lado.

Uso:
  .venv/bin/python scripts/bench_enrichment.py --campaign <slug> --limit 30
  .venv/bin/python scripts/bench_enrichment.py --csv path/to/companies.csv --limit 30
  (--refresh vuelve a llamar a las APIs; --yes saltea la confirmación de presupuesto)

NO toca ui/enrich.py ni ningún adapter; reusa el camino de Apollo existente
(ApolloIngestionSource.enrich_account_by_domain) y un cliente httpx mínimo de Exa.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT / "ui", _ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bench import exa_client, metrics, normalize  # noqa: E402

OUT = _ROOT / "out"
RAW = OUT / "raw"
HARD_CAP = 50
BUDGET_ABORT_USD = 10.0


# ---------------------------------------------------------------------------
# .env (mismo criterio que la app: setdefault, no pisa el entorno real)
# ---------------------------------------------------------------------------
def load_dotenv() -> None:
    import os
    env = _ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _safe_domain(domain: str) -> str:
    return re.sub(r"[^a-z0-9.\-]+", "_", (domain or "").strip().lower()) or "unknown"


def _host(url: str) -> str:
    h = re.sub(r"^https?://", "", (url or "").strip().lower())
    h = h.split("/")[0]
    return h[4:] if h.startswith("www.") else h


# ---------------------------------------------------------------------------
# Selección de empresas
# ---------------------------------------------------------------------------
def companies_from_campaign(slug: str, limit: int) -> list[dict[str, str]]:
    import leads_store
    store = leads_store.get_store()
    leads = store.list_leads(campaign_slug=slug)
    out, seen = [], set()
    for ld in leads:
        if (ld.get("tier") or "").upper() not in {"A", "B"}:
            continue
        dom = (ld.get("domain") or "").strip().lower()
        if not dom or dom in seen:
            continue
        seen.add(dom)
        out.append({"company": ld.get("company") or ld.get("name") or "", "domain": dom})
        if len(out) >= limit:
            break
    return out


def companies_from_csv(path: str, limit: int) -> list[dict[str, str]]:
    rows = list(csv.DictReader(Path(path).read_text(encoding="utf-8").splitlines()))
    if not rows:
        return []
    cols = {c.lower().strip(): c for c in rows[0].keys()}
    if "company" not in cols or "domain" not in cols:
        raise SystemExit("El CSV necesita columnas 'company' y 'domain'.")
    out, seen = [], set()
    for r in rows:
        dom = (r.get(cols["domain"]) or "").strip().lower()
        if not dom or dom in seen:
            continue
        seen.add(dom)
        out.append({"company": (r.get(cols["company"]) or "").strip(), "domain": dom})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Apollo (reusa el adapter existente) → record normalizado
# ---------------------------------------------------------------------------
def apollo_org_to_fields(org: dict[str, Any] | None) -> dict[str, Any]:
    if not org:
        return {"matched": False, "employee_count": None, "industry": None,
                "hq_country": None, "last_funding": None}
    funding = normalize.norm_funding({
        "stage": org.get("latest_funding_stage"),
        # Apollo no expone el monto de la ÚLTIMA ronda de forma confiable → null (honesto).
        "amount_usd": org.get("latest_funding_round_amount"),
        "date": org.get("latest_funding_round_date"),
    })
    return {
        "matched": True,
        "employee_count": normalize.norm_employee_count(org.get("estimated_num_employees")),
        "industry": org.get("industry") or None,
        "hq_country": normalize.norm_country(org.get("country")),
        "last_funding": funding,
    }


def fetch_apollo(domain: str, refresh: bool) -> tuple[dict[str, Any], float | None, bool]:
    """Devuelve (raw_cache, elapsed_s, called_live). Cachea acc.raw en out/raw/apollo/."""
    import os
    cache = RAW / "apollo" / f"{_safe_domain(domain)}.json"
    if cache.exists() and not refresh:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return data, data.get("_meta", {}).get("elapsed_s"), False
    if not os.getenv("APOLLO_API_KEY"):
        raise SystemExit("Falta APOLLO_API_KEY para llamar a Apollo (o usá caché existente).")
    from icp_engine.adapters.apollo import ApolloIngestionSource
    src = ApolloIngestionSource()
    t0 = time.monotonic()
    acc = asyncio.run(src.enrich_account_by_domain(domain))
    elapsed = time.monotonic() - t0
    data = {"raw": getattr(acc, "raw", None) if acc else None, "matched": acc is not None,
            "_meta": {"elapsed_s": round(elapsed, 3), "fetched_at": datetime.now().isoformat()}}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data, round(elapsed, 3), True


# ---------------------------------------------------------------------------
# Exa (Company Search + Agent) → record normalizado
# ---------------------------------------------------------------------------
def _exa_search_fields(search: dict[str, Any], domain: str) -> tuple[dict[str, Any], bool]:
    """Matchea el resultado por dominio; extrae los 3 atributos de entities[0].properties."""
    results = search.get("results") or search.get("data") or []
    match = None
    for r in results:
        if _host(r.get("url") or r.get("domain") or "") == _host(domain):
            match = r
            break
    if match is None:
        return {"employee_count": None, "industry": None, "hq_country": None}, False
    ents = match.get("entities") or []
    props = (ents[0].get("properties") if ents else None) or match.get("properties") or {}
    workforce = props.get("workforce") or {}
    hq = props.get("headquarters") or {}
    ec = workforce.get("total") if isinstance(workforce, dict) else None
    ec = ec if ec is not None else props.get("employeeCount") or props.get("numEmployees")
    country = hq.get("country") if isinstance(hq, dict) else None
    country = country or props.get("country")
    return {
        "employee_count": normalize.norm_employee_count(ec),
        "industry": (props.get("industry") or None),
        "hq_country": normalize.norm_country(country),
    }, True


def _exa_agent_fields(agent: dict[str, Any]) -> dict[str, Any]:
    structured = ((agent.get("output") or {}).get("structured")) or {}
    lf = structured.get("last_funding") or {}
    funding = normalize.norm_funding({
        "stage": lf.get("stage"), "amount_usd": lf.get("amount_usd"), "date": lf.get("date"),
    })
    hiring = (structured.get("hiring_signal") or {})
    geo = (structured.get("geo_expansion_signal") or {})
    return {
        "last_funding": funding,
        "hiring_signal": hiring.get("value") or None,
        "geo_expansion_signal": geo.get("value") or None,
        "sources": {
            "last_funding": (lf.get("source_url") or ""),
            "hiring_signal": (hiring.get("source_url") or ""),
            "geo_expansion_signal": (geo.get("source_url") or ""),
        },
    }


def fetch_exa(company: str, domain: str,
              refresh: bool) -> tuple[dict[str, Any], float | None, bool]:
    """Devuelve (raw_cache, elapsed_s, called_live). Cachea search+agent en out/raw/exa/."""
    cache = RAW / "exa" / f"{_safe_domain(domain)}.json"
    if cache.exists() and not refresh:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return data, data.get("_meta", {}).get("elapsed_s"), False
    t0 = time.monotonic()
    with httpx.Client() as client:
        search = exa_client.company_search(company, domain, client)
        agent = exa_client.agent_run(domain, client, effort="medium")
    elapsed = time.monotonic() - t0
    data = {"search": search, "agent": agent,
            "_meta": {"elapsed_s": round(elapsed, 3), "fetched_at": datetime.now().isoformat()}}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data, round(elapsed, 3), True


def exa_cache_to_fields(data: dict[str, Any], domain: str) -> dict[str, Any]:
    attrs, matched = _exa_search_fields(data.get("search") or {}, domain)
    agent = _exa_agent_fields(data.get("agent") or {})
    return {"matched": True, "search_matched": matched, **attrs, **agent}


# ---------------------------------------------------------------------------
# Presupuesto
# ---------------------------------------------------------------------------
def estimate_and_confirm(companies: list[dict[str, str]], refresh: bool, yes: bool) -> None:
    needed = 0
    for c in companies:
        cache = RAW / "exa" / f"{_safe_domain(c['domain'])}.json"
        if refresh or not cache.exists():
            needed += 1
    est = round(needed * (metrics.EXA_SEARCH_COST + metrics.EXA_AGENT_COST), 4)
    print(f"Empresas: {len(companies)} | llamadas Exa a hacer ahora: {needed} "
          f"({len(companies) - needed} desde caché)")
    print(f"Gasto Exa estimado de este corrido: ${est:.2f} "
          f"(cap de aborto: ${BUDGET_ABORT_USD:.2f})")
    if est > BUDGET_ABORT_USD:
        raise SystemExit(f"ABORTO: el estimado ${est:.2f} supera el cap ${BUDGET_ABORT_USD:.2f}.")
    if needed and not yes:
        resp = input("¿Seguir? [y/N] ").strip().lower()
        if resp not in {"y", "yes", "s", "si", "sí"}:
            raise SystemExit("Cancelado por el usuario.")


# ---------------------------------------------------------------------------
# Salidas
# ---------------------------------------------------------------------------
def _lf(rec: dict[str, Any] | None, key: str) -> Any:
    lf = (rec or {}).get("last_funding") or {}
    return lf.get(key)


def write_side_by_side(records: list[dict[str, Any]]) -> None:
    cols = ["domain", "company",
            "apollo_employee_count", "exa_employee_count",
            "apollo_industry", "exa_industry",
            "apollo_hq_country", "exa_hq_country",
            "apollo_funding_stage", "exa_funding_stage",
            "apollo_funding_amount", "exa_funding_amount",
            "apollo_funding_date", "exa_funding_date",
            "exa_hiring_signal", "exa_geo_expansion_signal",
            "apollo_matched", "exa_search_matched",
            "exa_src_funding", "exa_src_hiring", "exa_src_geo"]
    with (OUT / "bench_side_by_side.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in records:
            a, e = r.get("apollo") or {}, r.get("exa") or {}
            src = e.get("sources") or {}
            w.writerow([
                r["domain"], r["company"],
                a.get("employee_count"), e.get("employee_count"),
                a.get("industry"), e.get("industry"),
                a.get("hq_country"), e.get("hq_country"),
                _lf(a, "stage"), _lf(e, "stage"),
                _lf(a, "amount_usd"), _lf(e, "amount_usd"),
                _lf(a, "date"), _lf(e, "date"),
                e.get("hiring_signal"), e.get("geo_expansion_signal"),
                a.get("matched"), e.get("search_matched"),
                src.get("last_funding"), src.get("hiring_signal"), src.get("geo_expansion_signal"),
            ])


def write_spotcheck(records: list[dict[str, Any]]) -> None:
    import random
    pool = []
    for r in records:
        e = r.get("exa") or {}
        src = e.get("sources") or {}
        for field in metrics.GROUNDED_FIELDS:
            val = e.get(field)
            if val is not None:
                display = val if not isinstance(val, dict) else json.dumps(val, ensure_ascii=False)
                pool.append((r["domain"], field, display, src.get(field, "")))
    sample = random.Random(1234).sample(pool, min(10, len(pool)))
    lines = ["# Spotcheck de grounding de Exa (10 al azar, seed=1234)", "",
             "Abrí cada URL a mano para verificar el valor.", ""]
    for dom, field, val, url in sample:
        lines.append(f"- **{dom}** · `{field}` = {val}\n  - {url or '(sin source_url)'}")
    (OUT / "spotcheck.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pct(x: Any) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def write_report(m: dict[str, Any], records: list[dict[str, Any]]) -> None:
    fa, fe = m["fill_rate"]["apollo"], m["fill_rate"]["exa"]
    ag, st = m["agreement"], m["apollo_funding_staleness"]
    gr, co, wc = m["exa_grounding"], m["cost"], m["wall_clock"]
    lines = []
    lines += ["# Benchmark Apollo vs Exa — enrichment de señales de negocio", "",
          f"Empresas: {len(records)} · generado {m['generated_at']}", "",
          "> Solo números. Sin conclusiones ni recomendación (por diseño).", ""]
    lines += ["## 1. Fill rate (% no-null; matched:false = null)", "",
          "| Campo | Apollo | Exa |", "|---|---|---|"]
    for field in metrics.HEAD_TO_HEAD:
        lines.append(f"| {field} | {_pct(fa[field])} | {_pct(fe[field])} |")
    lines += ["", "## 2. Agreement (donde ambos tienen valor)", "",
          "| Campo | Métrica | Valor | n |", "|---|---|---|---|",
          f"| employee_count | dentro ±20% | {_pct(ag['employee_count']['within_20pct'])} "
          f"| {ag['employee_count']['n']} |",
          f"| employee_count | misma banda | {_pct(ag['employee_count']['same_band'])} "
          f"| {ag['employee_count']['n']} |",
          f"| hq_country | exacto | {_pct(ag['hq_country']['exact'])} | {ag['hq_country']['n']} |",
          f"| last_funding.stage | exacto | {_pct(ag['last_funding_stage']['exact'])} "
          f"| {ag['last_funding_stage']['n']} |",
          f"| last_funding.date | dentro 90d | {_pct(ag['last_funding_date']['within_90d'])} "
          f"| {ag['last_funding_date']['n']} |",
          "", "_industry: no scoreado (taxonomías no comparables) — ver §7._", ""]
    lines += ["## 3. Apollo funding staleness (la métrica que decide)", "",
          "| Métrica | Valor |", "|---|---|",
          f"| n (registros con fecha) | {st['n']} |",
          f"| mediana (días) | {st['median_days']} |",
          f"| p25 / p75 (días) | {st['p25_days']} / {st['p75_days']} |",
          f"| % > 365 días | {_pct(st['pct_over_365d'])} |",
          f"| % > 730 días | {_pct(st['pct_over_730d'])} |", ""]
    lines += ["## 4. Exa grounding (% de campos no-null con source_url)", "",
          f"Global: **{_pct(gr['overall_pct'])}** "
          f"({gr['with_source']}/{gr['non_null_fields']} campos)", "",
          "| Campo | no-null | con source_url |", "|---|---|---|"]
    for field, d in gr["by_field"].items():
        lines.append(f"| {field} | {d['non_null']} | {d['with_source']} |")
    lines += ["", "## 5. Costo", "",
          f"- Exa dataset: **${co['exa_usd']['dataset']:.2f}** · gastado este corrido: "
          f"${co['exa_usd']['spent_this_run']:.2f}",
          f"- Apollo: {co['apollo_credits']['dataset']} créditos (dataset) · "
          f"{co['apollo_credits']['spent_this_run']} este corrido", ""]
    lines += ["## 6. Wall-clock por lead (segundos)", "",
          "| Proveedor | p50 | p95 | n |", "|---|---|---|---|",
          f"| Apollo | {wc['apollo']['p50_s']} | {wc['apollo']['p95_s']} | {wc['apollo']['n']} |",
          f"| Exa | {wc['exa']['p50_s']} | {wc['exa']['p95_s']} | {wc['exa']['n']} |", ""]
    # 7. Exploratorios de Exa (Apollo no los tiene — es un hallazgo, no un "gana Exa").
    lines += ["## 7. Campos exploratorios de Exa (Apollo NO los provee)", "",
          "Apollo estructuralmente no devuelve estos campos. Solo Exa, sin comparación.", "",
          "| Dominio | hiring_signal | geo_expansion_signal |", "|---|---|---|"]
    for r in records:
        e = r.get("exa") or {}
        lines.append(f"| {r['domain']} | {e.get('hiring_signal') or '—'} "
                 f"| {e.get('geo_expansion_signal') or '—'} |")
    # Industria lado a lado para revisión manual.
    lines += ["", "## 8. Industria (revisión manual — taxonomías no comparables)", "",
          "| Dominio | Apollo | Exa |", "|---|---|---|"]
    for r in records:
        a, e = r.get("apollo") or {}, r.get("exa") or {}
        lines.append(f"| {r['domain']} | {a.get('industry') or '—'} | {e.get('industry') or '—'} |")
    (OUT / "bench_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_records(companies: list[dict[str, str]], refresh: bool) -> tuple[list, dict, dict]:
    timings: dict[str, list[float]] = {"apollo": [], "exa": []}
    exec_counts = {"exa_search": 0, "exa_agent": 0, "apollo_credits": 0}

    # Apollo: secuencial (async por dominio).
    apollo_by_dom: dict[str, dict[str, Any]] = {}
    for c in companies:
        data, elapsed, live = fetch_apollo(c["domain"], refresh)
        apollo_by_dom[c["domain"]] = apollo_org_to_fields(data.get("raw"))
        if elapsed is not None:
            timings["apollo"].append(elapsed)
        if live:
            exec_counts["apollo_credits"] += 1

    # Exa: pool de 2 (respeta el límite de 2 runs simultáneos del Agent API).
    def _one_exa(c: dict[str, str]) -> tuple[str, dict[str, Any], float | None, bool]:
        data, elapsed, live = fetch_exa(c["company"], c["domain"], refresh)
        return c["domain"], data, elapsed, live

    exa_by_dom: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for dom, data, elapsed, live in pool.map(_one_exa, companies):
            exa_by_dom[dom] = exa_cache_to_fields(data, dom)
            if elapsed is not None:
                timings["exa"].append(elapsed)
            if live:
                exec_counts["exa_search"] += 1
                exec_counts["exa_agent"] += 1

    records = [{"domain": c["domain"], "company": c["company"],
                "apollo": apollo_by_dom[c["domain"]], "exa": exa_by_dom[c["domain"]]}
               for c in companies]
    return records, timings, exec_counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark Apollo vs Exa (enrichment).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--campaign", help="slug de campaña (lee de Supabase, tier A/B)")
    g.add_argument("--csv", help="CSV con columnas company,domain")
    ap.add_argument("--limit", type=int, default=30, help="máx empresas (hard cap 50)")
    ap.add_argument("--refresh", action="store_true", help="ignora caché y vuelve a llamar")
    ap.add_argument("--yes", action="store_true", help="saltea la confirmación de presupuesto")
    args = ap.parse_args()

    if args.limit > HARD_CAP:
        raise SystemExit(f"--limit {args.limit} supera el hard cap de {HARD_CAP}.")

    load_dotenv()
    OUT.mkdir(parents=True, exist_ok=True)

    if args.campaign:
        companies = companies_from_campaign(args.campaign, args.limit)
    else:
        companies = companies_from_csv(args.csv, args.limit)
    if not companies:
        raise SystemExit("No se encontraron empresas (tier A/B con dominio) para el input dado.")

    estimate_and_confirm(companies, args.refresh, args.yes)

    records, timings, exec_counts = build_records(companies, args.refresh)

    today = date.today()
    m = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_companies": len(records),
        "fill_rate": {"apollo": metrics.fill_rate(records, "apollo"),
                      "exa": metrics.fill_rate(records, "exa")},
        "agreement": metrics.agreement(records),
        "apollo_funding_staleness": metrics.apollo_funding_staleness(records, today),
        "exa_grounding": metrics.exa_grounding(records),
        "cost": metrics.cost(records, exec_counts),
        "wall_clock": metrics.wall_clock(timings),
    }
    (OUT / "bench_metrics.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    write_side_by_side(records)
    write_spotcheck(records)
    write_report(m, records)
    print(f"Listo. Salidas en {OUT}/: bench_side_by_side.csv, bench_metrics.json, "
          "bench_report.md, spotcheck.md")


if __name__ == "__main__":
    main()

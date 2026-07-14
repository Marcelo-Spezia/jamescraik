"""Demo end-to-end con Apollo como fuente de datos (Epic 2, tajada fina).

Flujo: ICP → query de Apollo → ingestión → normalización a canónico → scoring.

Por defecto usa un FIXTURE (respuesta grabada de Apollo) y un juez simulado, así
corre sin ninguna credencial. Con --live usa Apollo real (APOLLO_API_KEY) y, si
hay ANTHROPIC_API_KEY, el JudgeModel real (Claude).

Correr:
  python -m examples.demo_apollo            # fixture, sin credenciales
  python -m examples.demo_apollo --live     # Apollo + Claude reales (.env)
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from icp_engine.adapters.apollo import ApolloIngestionSource
from icp_engine.adapters.stub import StubJudgeModel
from icp_engine.registry.loader import load_icp
from icp_engine.registry.schema import ICPDefinition
from icp_engine.scoring.pipeline import score_async

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ICP_PATH = PROJECT_ROOT / "icp" / "tech-enabled-services.yaml"
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "apollo" / "people_search.json"


def _load_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def apollo_query_from_icp(icp: ICPDefinition) -> dict:
    """Traduce los criterios del ICP a parámetros de búsqueda de Apollo.

    Muestra el round-trip: el ICP (dato versionable) determina a quién buscar.
    """
    seg = icp.segments[0]
    params: dict = {"per_page": 5}  # demo: pocas cuentas, para no quemar créditos

    for c in seg.account_criteria:
        if c.field == "employee_count" and c.op.value == "between":
            lo, hi = c.value
            params["organization_num_employees_ranges"] = [f"{lo},{hi}"]
        if c.field == "region" and c.op.value == "in":
            locs = []
            if "NA" in c.value:
                locs += ["United States", "Canada"]
            if "LATAM" in c.value:
                locs += ["Mexico", "Brazil", "Argentina", "Chile", "Colombia"]
            if locs:
                params["organization_locations"] = locs

    for c in seg.contact_criteria:
        if c.field == "seniority" and c.op.value == "in":
            # mapeo inverso simple a las seniorities de Apollo
            inv = {"c_level": "c_suite", "vp": "vp", "director": "director"}
            params["person_seniorities"] = [inv.get(v, v) for v in c.value]
        # Nota: NO filtramos por departamento en la búsqueda — Apollo usa su propia
        # taxonomía de departamentos y nuestros valores devuelven 0. El departamento
        # se evalúa al scorear el contacto ya enriquecido (contact_criteria del ICP).

    return params


# --- Cliente httpx falso para el modo fixture (sin red) ---
class _FixtureResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FixtureClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def post(self, url, headers=None, json=None):
        return _FixtureResponse(self._payload)


async def _run(live: bool):
    icp = load_icp(ICP_PATH)
    query = apollo_query_from_icp(icp)

    if live:
        _load_dotenv()
        source = ApolloIngestionSource()  # APOLLO_API_KEY del entorno
        if os.getenv("ANTHROPIC_API_KEY"):
            from icp_engine.adapters.anthropic_judge import build_judge_from_env
            judge = build_judge_from_env()
            judge_label = "Claude (real)"
        else:
            judge = StubJudgeModel(default_score=0.5)
            judge_label = "simulado (sin ANTHROPIC_API_KEY)"

        print(f"\nFuente: Apollo (LIVE: People Search → enrich)  ·  juez: {judge_label}")
        print(f"ICP: {icp.meta.id} v{icp.meta.version}")
        print("Query Apollo derivada del ICP:")
        print("  " + json.dumps(query, ensure_ascii=False))
        print("=" * 96)

        # Armado de listas real: descubrir contactos net-new → enriquecer → pares.
        pairs = await source.build_leads(limit=6, **query)
        print(f"Apollo armó {len(pairs)} leads (empresa + contacto reales). Scoreados:\n")
        print(f"{'empresa':<24}{'contacto':<26}{'fit':>5} {'tier':>4} {'dq':>4}  tech-enabled")
        print("-" * 96)
        for acc, ct in pairs:
            r = await score_async(acc, ct, icp, judge=judge)
            te = next((f for f in r.fuzzy if f.id == "tech_enabled"), None)
            te_txt = f"{te.score_0_1:.2f}" if te else "—"
            dq = "sí" if r.disqualified else "no"
            who = f"{(ct.full_name or '?')[:16]} ({ct.seniority.value})"[:25]
            print(f"{acc.name[:23]:<24}{who:<26}{r.fit_score:>5.0f} "
                  f"{r.tier:>4} {dq:>4}  {te_txt}")
        print()
        return

    # --- Modo fixture (sin credenciales): pares (Account, Contact) completos ---
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = ApolloIngestionSource(api_key="fixture", client=_FixtureClient(payload))
    judge = StubJudgeModel(default_score=0.5)

    print("\nFuente: Apollo (fixture)  ·  juez: simulado")
    print(f"ICP: {icp.meta.id} v{icp.meta.version}")
    print("Query Apollo derivada del ICP:")
    print("  " + json.dumps(query, ensure_ascii=False))
    print("=" * 88)

    pairs = await source.fetch_leads(**query)
    print(f"Apollo devolvió {len(pairs)} leads. Normalizados a canónico y scoreados:\n")
    print(f"{'empresa':<30}{'contacto':<24}{'fit':>5} {'tier':>4} {'dq':>4}")
    print("-" * 88)
    for acc, ct in pairs:
        r = await score_async(acc, ct, icp, judge=judge)
        dq = "sí" if r.disqualified else "no"
        name, who = acc.name[:29], (ct.full_name or "")[:23]
        print(f"{name:<30}{who:<24}{r.fit_score:>5.0f} {r.tier:>4} {dq:>4}")
    print()


def main():
    import sys
    asyncio.run(_run(live="--live" in sys.argv))


if __name__ == "__main__":
    main()

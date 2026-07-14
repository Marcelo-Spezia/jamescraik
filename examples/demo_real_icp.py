"""Demo del ICP real v0.1.1 — tech-enabled business services.

Califica cuentas contra `icp/tech-enabled-services.yaml`. Para simular el LLM
sin proveedor real, cada cuenta trae su "veredicto difuso esperado" (lo que un
JudgeModel real devolvería) y construimos un StubJudgeModel por cuenta.

Correr:  python -m examples.demo_real_icp
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from icp_engine.adapters.base import FuzzyResult
from icp_engine.adapters.stub import StubJudgeModel
from icp_engine.canonical.enums import Department, Industry, Seniority, SignalStrength
from icp_engine.canonical.models import Account, Contact, Signal
from icp_engine.registry.loader import load_icp
from icp_engine.scoring.pipeline import score

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ICP_PATH = PROJECT_ROOT / "icp" / "tech-enabled-services.yaml"


def _load_dotenv() -> None:
    """Carga variables de un .env en la raíz del proyecto (formato KEY=valor).

    Mínimo y sin dependencias: solo setea las que no estén ya en el entorno.
    """
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

# Substring único de cada prompt difuso → para mapear el veredicto simulado.
FUZZY_KEYS = {
    "tech_enabled": "parte central de cómo",
    "business_services_fit": "servicios profesionales",
    "build_intent": "desarrollo de software a medida",
}


def judge_for(verdicts: dict[str, tuple[float, str]]) -> StubJudgeModel:
    """Construye un JudgeModel stub a partir de {criterio_id: (score, rationale)}."""
    overrides = {
        FUZZY_KEYS[cid]: FuzzyResult(score_0_1=s, rationale=r)
        for cid, (s, r) in verdicts.items()
    }
    return StubJudgeModel(default_score=0.0, overrides=overrides)


def build_cases():
    """(label, Account, Contact, veredicto_difuso_simulado)."""
    cases = []

    # 1) Esquire-style: servicios legales tech-enabled. Caso ideal.
    cases.append((
        "legal tech-enabled", Account(
            account_id="a1", name="Esquire-style Legal Services", domain="esq.example",
            industry=Industry.OTHER, employee_count=900, region="NA", country="US",
            tech_stack=["aws", "react", "python"],
            intent_signals=[Signal(type="job_post_engineering", strength=SignalStrength.STRONG,
                                   observed_at=date(2026, 5, 1), source="demo",
                                   detail="Hiring 5 software engineers.")],
            source="demo"),
        Contact(contact_id="c1", account_id="a1", full_name="Dana Cruz",
                title="VP of Engineering", seniority=Seniority.VP,
                department=Department.ENGINEERING, source="demo"),
        {"tech_enabled": (0.9, "Plataforma propia de gestión de casos + equipo de ingeniería."),
         "business_services_fit": (0.95, "Servicios legales B2B."),
         "build_intent": (0.8, "Contrata ingenieros activamente.")},
    ))

    # 2) Servicios financieros tech-enabled.
    cases.append((
        "fintech services", Account(
            account_id="a2", name="LedgerWorks", domain="ledgerworks.example",
            industry=Industry.FINTECH, employee_count=600, region="NA", country="CA",
            tech_stack=["aws", "snowflake"], source="demo"),
        Contact(contact_id="c2", account_id="a2", full_name="Sam Ortiz",
                title="CTO", seniority=Seniority.C_LEVEL,
                department=Department.ENGINEERING, source="demo"),
        {"tech_enabled": (0.85, "Automatización de back-office financiero con data pipelines."),
         "business_services_fit": (0.6, "Servicios financieros, algo de producto."),
         "build_intent": (0.75, "Equipo de data/eng interno.")},
    ))

    # 3) Aseguradora tradicional, poco tech. Buen contacto, mala empresa.
    cases.append((
        "servicios NO-tech", Account(
            account_id="a3", name="Heritage Insurance Brokers", domain="heritage.example",
            industry=Industry.INSURANCE, employee_count=800, region="NA", country="US",
            tech_stack=[], source="demo"),
        Contact(contact_id="c3", account_id="a3", full_name="Pat Nolan",
                title="Director of Operations", seniority=Seniority.DIRECTOR,
                department=Department.OPS, source="demo"),
        {"tech_enabled": (0.15, "Corretaje tradicional; sin plataforma propia."),
         "business_services_fit": (0.9, "Servicios de seguros B2B."),
         "build_intent": (0.2, "Sin señales de desarrollo in-house.")},
    ))

    # 4) Muy chica → knockout.
    cases.append((
        "muy chica", Account(
            account_id="a4", name="TinyDevShop", domain="tinydev.example",
            industry=Industry.OTHER, employee_count=20, region="NA", country="US",
            tech_stack=["aws", "react"], source="demo"),
        Contact(contact_id="c4", account_id="a4", full_name="Lee Park",
                title="Founder & CEO", seniority=Seniority.C_LEVEL,
                department=Department.EXEC, source="demo"),
        {"tech_enabled": (0.9, "Producto digital."), "business_services_fit": (0.5, "Mixto."),
         "build_intent": (0.9, "Build-first.")},
    ))

    # 5) Fuera de geografía → disqualifier.
    cases.append((
        "fuera de NA/LATAM", Account(
            account_id="a5", name="EuroServ GmbH", domain="euroserv.example",
            industry=Industry.LOGISTICS, employee_count=700, region="EMEA", country="DE",
            tech_stack=["azure", "kubernetes"], source="demo"),
        Contact(contact_id="c5", account_id="a5", full_name="Max Bauer",
                title="VP Product", seniority=Seniority.VP,
                department=Department.PRODUCT, source="demo"),
        {"tech_enabled": (0.8, "Plataforma logística."),
         "business_services_fit": (0.85, "Servicios logísticos."),
         "build_intent": (0.7, "Equipo de producto.")},
    ))

    # 6) Empresa tech-enabled ideal, pero persona equivocada (IC en ventas).
    cases.append((
        "persona equivocada", Account(
            account_id="a6", name="StaffPro Solutions", domain="staffpro.example",
            industry=Industry.OTHER, employee_count=500, region="LATAM", country="AR",
            tech_stack=["gcp", "node", "python"], source="demo"),
        Contact(contact_id="c6", account_id="a6", full_name="Jordan Diaz",
                title="Sales Development Rep", seniority=Seniority.IC,
                department=Department.SALES, source="demo"),
        {"tech_enabled": (0.85, "Plataforma de staffing con matching algorítmico."),
         "business_services_fit": (0.9, "Staffing / RRHH B2B."),
         "build_intent": (0.8, "Equipo de ingeniería propio.")},
    ))

    return cases


def main(emit_json: bool = False, live: bool = False):
    icp = load_icp(ICP_PATH)
    out = {"icp": {"id": icp.meta.id, "version": icp.meta.version,
                   "status": str(icp.meta.status), "name": icp.meta.name}, "results": []}

    # En modo --live usamos el JudgeModel real (Claude). Sin el flag, un juez
    # simulado por cuenta (determinístico) para demostrar el motor sin costo/API.
    live_judge = None
    if live:
        _load_dotenv()  # toma ANTHROPIC_API_KEY de un .env si existe
        from icp_engine.adapters.anthropic_judge import build_judge_from_env
        live_judge = build_judge_from_env()

    if not emit_json:
        mode = "LIVE (Claude)" if live else "simulado"
        print(f"\nICP: {icp.meta.id} v{icp.meta.version} ({icp.meta.status})  ·  juez: {mode}")
        print("=" * 84)
        print(f"{'caso':<20}{'empresa':<28}{'fit':>5} {'tier':>4} {'dq':>4}  emp/cont")
        print("-" * 84)

    for label, acc, ct, verdicts in build_cases():
        judge = live_judge if live else judge_for(verdicts)
        r = score(acc, ct, icp, judge=judge)
        out["results"].append({
            "label": label, "account": acc.name, "contact": f"{ct.full_name} — {ct.title}",
            "fit_score": r.fit_score, "tier": r.tier, "disqualified": r.disqualified,
            "account_score": r.account_score, "contact_score": r.contact_score,
            "intent_points": r.intent_points,
            "knockouts": [k.model_dump() for k in r.knockouts],
            "disqualifiers": [d.model_dump() for d in r.disqualifiers if d.matched],
            "contributions": [c.model_dump() for c in r.contributions],
            "fuzzy": [f.model_dump() for f in r.fuzzy],
            "intent": [i.model_dump() for i in r.intent],
            "explanation": r.explanation,
        })
        if not emit_json:
            dq = "sí" if r.disqualified else "no"
            print(f"{label:<20}{acc.name:<28}{r.fit_score:>5.0f} {r.tier:>4} {dq:>4}  "
                  f"{r.account_score:.0f}/{r.contact_score:.0f}")

    if emit_json:
        print(json.dumps(out, default=str, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    main(emit_json="--json" in sys.argv, live="--live" in sys.argv)

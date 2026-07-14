"""Demo end-to-end del ICP Engine (DoD §14.7).

Califica un batch sintético de cuentas+contactos contra el ICP de ejemplo
(`docs/icp.example.yaml`) usando el StubJudgeModel (LLM detrás de interfaz, sin
proveedor real), imprime una tabla con tier + explicación, muestra un
`ScoreResult` completo (§7) y cierra con el ICP-fit rate por versión (§11).

Correr:  python -m examples.demo_batch
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from icp_engine.adapters.base import FuzzyResult
from icp_engine.adapters.stub import StubJudgeModel
from icp_engine.canonical.enums import (
    Department,
    FundingStage,
    Industry,
    Seniority,
    SignalStrength,
)
from icp_engine.canonical.models import Account, Contact, Signal
from icp_engine.feedback.fit_rate import calculate_fit_rate, calculate_tier_correlation
from icp_engine.feedback.models import FeedbackRecord, ReasonCode, Verdict
from icp_engine.registry.loader import load_icp
from icp_engine.scoring.pipeline import score

ICP_PATH = Path(__file__).resolve().parent.parent / "docs" / "icp.example.yaml"


def build_batch() -> list[tuple[str, Account, Contact]]:
    """Un set chico que cubre los casos clave: ideal, parcial, knockout,
    disqualifier y persona equivocada."""
    batch: list[tuple[str, Account, Contact]] = []

    # 1) Match ideal — debería salir tier A
    batch.append((
        "ideal",
        Account(
            account_id="acc_001", name="Acme SaaS Inc.", domain="acmesaas.com",
            industry=Industry.SOFTWARE, employee_count=800, revenue_usd=50_000_000,
            country="US", region="NA", founded_year=2015,
            funding_stage=FundingStage.SERIES_B,
            tech_stack=["salesforce", "snowflake"],
            intent_signals=[
                Signal(type="funding_round", strength=SignalStrength.STRONG,
                       observed_at=date(2026, 5, 1), source="fixture",
                       detail="Serie C levantada."),
                Signal(type="leadership_change", strength=SignalStrength.MODERATE,
                       observed_at=date(2026, 4, 15), source="fixture",
                       detail="Nuevo VP Eng."),
            ],
            source="demo",
        ),
        Contact(
            contact_id="ct_001", account_id="acc_001", full_name="María García",
            title="VP of Engineering", seniority=Seniority.VP,
            department=Department.ENGINEERING, country="US", source="demo",
        ),
    ))

    # 2) Match parcial — empresa fintech ok pero contacto en marketing
    batch.append((
        "parcial",
        Account(
            account_id="acc_002", name="MediumCorp", domain="mediumcorp.com",
            industry=Industry.FINTECH, employee_count=400, revenue_usd=20_000_000,
            country="US", region="NA", founded_year=2018,
            funding_stage=FundingStage.GROWTH, tech_stack=["hubspot"],
            source="demo",
        ),
        Contact(
            contact_id="ct_002", account_id="acc_002", full_name="Ana López",
            title="Director of Marketing", seniority=Seniority.DIRECTOR,
            department=Department.MARKETING, country="US", source="demo",
        ),
    ))

    # 3) Knockout — empresa demasiado chica (employee_count < 50) → tier D
    batch.append((
        "knockout",
        Account(
            account_id="acc_003", name="TinyStartup LLC", domain="tinystartup.io",
            industry=Industry.SOFTWARE, employee_count=30, revenue_usd=1_000_000,
            country="US", region="NA", founded_year=2023,
            funding_stage=FundingStage.SEED, tech_stack=["salesforce"],
            source="demo",
        ),
        Contact(
            contact_id="ct_003", account_id="acc_003", full_name="Sam Lee",
            title="CTO", seniority=Seniority.C_LEVEL,
            department=Department.ENGINEERING, country="US", source="demo",
        ),
    ))

    # 4) Disqualifier — government → tier D
    batch.append((
        "disqualifier",
        Account(
            account_id="acc_004", name="Federal Agency X", domain="agency-x.gov",
            industry=Industry.GOVERNMENT, employee_count=5000, revenue_usd=0,
            country="US", region="NA", founded_year=1950,
            funding_stage=FundingStage.UNKNOWN, tech_stack=[], source="demo",
        ),
        Contact(
            contact_id="ct_004", account_id="acc_004", full_name="Pat Doe",
            title="Director of IT", seniority=Seniority.DIRECTOR,
            department=Department.ENGINEERING, country="US", source="demo",
        ),
    ))

    # 5) Persona equivocada — empresa buena, contacto IC en ventas
    batch.append((
        "persona-mala",
        Account(
            account_id="acc_005", name="GoodCo", domain="goodco.com",
            industry=Industry.SOFTWARE, employee_count=600, revenue_usd=40_000_000,
            country="US", region="NA", founded_year=2014,
            funding_stage=FundingStage.SERIES_B, tech_stack=["salesforce"],
            source="demo",
        ),
        Contact(
            contact_id="ct_005", account_id="acc_005", full_name="John Smith",
            title="Sales Representative", seniority=Seniority.IC,
            department=Department.SALES, country="US", source="demo",
        ),
    ))

    return batch


def build_judge() -> StubJudgeModel:
    """Stub que simula el LLM para los fuzzy_criteria del ICP de ejemplo.
    Matchea por substring del prompt (contrato §12: solo recibe el prompt)."""
    return StubJudgeModel(
        default_score=0.4,
        default_rationale="Señales mixtas (stub).",
        overrides={
            "madurez digital": FuzzyResult(
                score_0_1=0.8, rationale="Stack moderno + equipo de producto visible."
            ),
            "in-house": FuzzyResult(
                score_0_1=0.6, rationale="Vacantes de ingeniería de plataforma."
            ),
        },
    )


def main() -> None:
    icp = load_icp(ICP_PATH)
    judge = build_judge()
    batch = build_batch()

    print(f"\nICP: {icp.meta.id} v{icp.meta.version} ({icp.meta.status})")
    print("=" * 78)
    print(f"{'caso':<14}{'cuenta':<18}{'fit':>5} {'tier':>4} {'dq':>4}  explicación")
    print("-" * 78)

    results = []
    for label, account, contact in batch:
        r = score(account, contact, icp, judge=judge)
        results.append((label, account, r))
        dq = "sí" if r.disqualified else "no"
        expl = r.explanation if len(r.explanation) <= 70 else r.explanation[:67] + "..."
        print(f"{label:<14}{account.name:<18}{r.fit_score:>5.0f} {r.tier:>4} {dq:>4}  {expl}")

    # --- ScoreResult completo de la muestra ideal (§7, auditable) ---
    sample = results[0][2]
    print("\n" + "=" * 78)
    print("ScoreResult completo (muestra 'ideal') — fuente auditable §7:")
    print("=" * 78)
    print(sample.model_dump_json(indent=2))

    # --- Feedback loop + ICP-fit rate (§10, §11, DoD §14.6) ---
    # Mock: sales valida los tier A/B como fit y el resto como no_fit.
    feedbacks: list[FeedbackRecord] = []
    for _, _, r in results:
        verdict = Verdict.FIT if r.tier in ("A", "B") else Verdict.NO_FIT
        reason = ReasonCode.GOOD_FIT if verdict == Verdict.FIT else ReasonCode.OTHER
        feedbacks.append(FeedbackRecord(
            account_id=r.account_id, contact_id=r.contact_id,
            icp_id=r.icp_id, icp_version=r.icp_version,
            predicted_tier=r.tier, predicted_fit_score=r.fit_score,
            verdict=verdict, reason_code=reason, marked_by="demo",
        ))

    print("\n" + "=" * 78)
    print("ICP-fit rate por versión (§11):")
    print("=" * 78)
    for fr in calculate_fit_rate(feedbacks):
        print(f"  {fr.icp_id} v{fr.icp_version}: "
              f"{fr.fit_rate_pct}% ({fr.fit_count} fit / {fr.total} marcados)")

    print("\nCorrelación tier ↔ verdict (§11 secundaria):")
    for tc in calculate_tier_correlation(feedbacks):
        print(f"  tier {tc.tier}: {round(tc.fit_rate * 100)}% fit "
              f"({tc.fit_count}/{tc.total})")
    print()


if __name__ == "__main__":
    main()

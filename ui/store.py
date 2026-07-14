"""Persistencia en archivos de búsquedas guardadas (runs) y métricas por ICP.

Cada búsqueda corrida se guarda como JSON en  runs/<icp_id>/<run_id>.json
con la query, los leads calificados y el feedback de sales (👍/👎). El fit-rate
por ICP se calcula agregando ese feedback con el módulo feedback del motor (§11).

OJO: los runs contienen datos reales de contactos (PII) → runs/ va en .gitignore.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from icp_engine.feedback.fit_rate import calculate_fit_rate
from icp_engine.feedback.models import FeedbackRecord, Verdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = PROJECT_ROOT / "runs"


def _runs_dir(icp_id: str) -> Path:
    d = RUNS_DIR / icp_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(
    icp_id: str,
    icp_version: str,
    query: dict[str, Any],
    leads: list[dict[str, Any]],
    mode: str = "leads",
    now: datetime | None = None,
) -> str:
    """Guarda una búsqueda. Devuelve el run_id. A cada lead le asigna un id estable.

    mode: "leads" (personas) o "companies" (empresas).
    """
    now = now or datetime.now(UTC)
    run_id = now.strftime("%Y%m%d-%H%M%S")
    for i, lead in enumerate(leads):
        lead.setdefault("lead_id", f"{run_id}-{i}")
    run = {
        "run_id": run_id,
        "icp_id": icp_id,
        "icp_version": icp_version,
        "mode": mode,
        "created_at": now.isoformat(),
        "query": query,
        "leads": leads,
        "feedback": {},  # lead_id -> "fit" | "no_fit"
    }
    (_runs_dir(icp_id) / f"{run_id}.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_id


def load_run(icp_id: str, run_id: str) -> dict[str, Any]:
    return json.loads((_runs_dir(icp_id) / f"{run_id}.json").read_text(encoding="utf-8"))


def _tier_counts(leads: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lead in leads:
        t = lead.get("tier", "?")
        counts[t] = counts.get(t, 0) + 1
    return counts


def list_runs(icp_id: str) -> list[dict[str, Any]]:
    """Metadata de las búsquedas de un ICP, más nuevas primero."""
    d = RUNS_DIR / icp_id
    if not d.exists():
        return []
    out = []
    for path in sorted(d.glob("*.json"), reverse=True):
        run = json.loads(path.read_text(encoding="utf-8"))
        out.append({
            "run_id": run["run_id"],
            "created_at": run["created_at"],
            "mode": run.get("mode", "leads"),
            "n_leads": len(run.get("leads", [])),
            "tier_counts": _tier_counts(run.get("leads", [])),
            "n_feedback": len(run.get("feedback", {})),
        })
    return out


def set_feedback(icp_id: str, run_id: str, lead_id: str, verdict: str | None) -> None:
    """Marca un lead como fit/no_fit (o lo limpia con verdict=None)."""
    path = _runs_dir(icp_id) / f"{run_id}.json"
    run = json.loads(path.read_text(encoding="utf-8"))
    fb = run.setdefault("feedback", {})
    if verdict is None:
        fb.pop(lead_id, None)
    else:
        fb[lead_id] = verdict
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")


def _feedback_records(icp_id: str) -> list[FeedbackRecord]:
    """Junta el feedback de todas las búsquedas de un ICP como FeedbackRecords."""
    records: list[FeedbackRecord] = []
    d = RUNS_DIR / icp_id
    if not d.exists():
        return records
    for path in d.glob("*.json"):
        run = json.loads(path.read_text(encoding="utf-8"))
        leads_by_id = {lead.get("lead_id"): lead for lead in run.get("leads", [])}
        for lead_id, verdict in run.get("feedback", {}).items():
            lead = leads_by_id.get(lead_id, {})
            records.append(FeedbackRecord(
                account_id=lead_id, contact_id=lead_id,
                icp_id=run["icp_id"], icp_version=run.get("icp_version", "?"),
                predicted_tier=lead.get("tier", "D"),
                predicted_fit_score=float(lead.get("fit", 0)),
                verdict=Verdict.FIT if verdict == "fit" else Verdict.NO_FIT,
            ))
    return records


def icp_fit_rate(icp_id: str) -> float | None:
    """Fit-rate agregado (0-100) del ICP según el feedback marcado; None si no hay."""
    records = _feedback_records(icp_id)
    if not records:
        return None
    results = calculate_fit_rate(records, icp_id=icp_id)
    total = sum(r.total for r in results)
    if total == 0:
        return None
    fit = sum(r.fit_count for r in results)
    return round(fit / total * 100, 1)


def icp_stats(icp_id: str) -> dict[str, Any]:
    """Resumen para la biblioteca: nº de búsquedas + fit-rate."""
    return {"n_runs": len(list_runs(icp_id)), "fit_rate": icp_fit_rate(icp_id)}

"""Persistencia de campañas (el 'ICP' redefinido).

Una campaña = {name, sales_nav_filters, rubric, value_prop, enrichment_signals}. Se guarda
como JSON en campaigns/ (sin PII → se versiona en git) y se reutiliza en el calificador.
enrichment_signals = qué señales de negocio enriquecer para el mensaje (varía por campaña).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAMPAIGNS_DIR = PROJECT_ROOT / "campaigns"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "campana"


def save_campaign(camp: dict[str, Any]) -> str:
    """Guarda/actualiza una campaña. Devuelve el slug (id de archivo)."""
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    slug = camp.get("slug") or _slug(camp.get("name", ""))
    now = datetime.now(UTC).isoformat()
    data = {
        "slug": slug,
        "name": camp.get("name", "") or slug,
        "sales_nav_filters": list(camp.get("sales_nav_filters", [])),
        "rubric": camp.get("rubric", ""),
        "value_prop": camp.get("value_prop", ""),
        "enrichment_signals": list(camp.get("enrichment_signals", [])),
        "created_at": camp.get("created_at", now),
        "updated_at": now,
    }
    (CAMPAIGNS_DIR / f"{slug}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return slug


def list_campaigns() -> list[dict[str, Any]]:
    """Todas las campañas guardadas, más nuevas primero."""
    if not CAMPAIGNS_DIR.exists():
        return []
    camps = [json.loads(p.read_text(encoding="utf-8")) for p in CAMPAIGNS_DIR.glob("*.json")]
    camps.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return camps


def load_campaign(slug: str) -> dict[str, Any]:
    return json.loads((CAMPAIGNS_DIR / f"{slug}.json").read_text(encoding="utf-8"))

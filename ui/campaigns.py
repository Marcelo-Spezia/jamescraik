"""Persistencia de campañas (el 'ICP' redefinido).

Una campaña = {name, sales_nav_filters, rubric, value_prop, enrichment_signals}.

Persistencia DURABLE en Supabase cuando hay credenciales (tabla `campaigns`); si no,
fallback a archivos JSON en campaigns/ (desarrollo local / tests). Motivo del cambio:
en Streamlit Cloud el disco es efímero → los archivos se pierden en cada redeploy y las
campañas "no quedaban guardadas". Los leads ya viven en Supabase; ahora las campañas
también. Mismo criterio de detección que leads_store.get_store().
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAMPAIGNS_DIR = PROJECT_ROOT / "campaigns"
_TABLE = "campaigns"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "campana"


def _campaign_data(camp: dict[str, Any]) -> dict[str, Any]:
    """Normaliza una campaña al registro persistible (mismo shape en archivo y en Supabase)."""
    slug = camp.get("slug") or _slug(camp.get("name", ""))
    now = datetime.now(UTC).isoformat()
    return {
        "slug": slug,
        "name": camp.get("name", "") or slug,
        "sales_nav_filters": list(camp.get("sales_nav_filters", [])),
        "rubric": camp.get("rubric", ""),
        "value_prop": camp.get("value_prop", ""),
        "enrichment_signals": list(camp.get("enrichment_signals", [])),
        "created_at": camp.get("created_at", now),
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Detección de backend (mismo criterio que leads_store)
# ---------------------------------------------------------------------------
def _use_supabase() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


def _client() -> Any:
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


# ---------------------------------------------------------------------------
# Backend Supabase (client inyectable para tests)
# ---------------------------------------------------------------------------
def _sb_save(data: dict[str, Any], client: Any) -> str:
    client.table(_TABLE).upsert(data, on_conflict="slug").execute()
    return data["slug"]


def _sb_list(client: Any) -> list[dict[str, Any]]:
    res = client.table(_TABLE).select("*").order("updated_at", desc=True).execute()
    return res.data or []


def _sb_load(slug: str, client: Any) -> dict[str, Any]:
    res = client.table(_TABLE).select("*").eq("slug", slug).execute()
    if not res.data:
        raise KeyError(f"campaña no encontrada: {slug}")
    return res.data[0]


def _sb_delete(slug: str, client: Any) -> bool:
    res = client.table(_TABLE).delete().eq("slug", slug).execute()
    return bool(res.data)


# ---------------------------------------------------------------------------
# Backend archivo (fallback local / tests)
# ---------------------------------------------------------------------------
def _file_save(data: dict[str, Any]) -> str:
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    (CAMPAIGNS_DIR / f"{data['slug']}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data["slug"]


def _file_list() -> list[dict[str, Any]]:
    if not CAMPAIGNS_DIR.exists():
        return []
    camps = [json.loads(p.read_text(encoding="utf-8")) for p in CAMPAIGNS_DIR.glob("*.json")]
    camps.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return camps


def _file_load(slug: str) -> dict[str, Any]:
    return json.loads((CAMPAIGNS_DIR / f"{slug}.json").read_text(encoding="utf-8"))


def _file_delete(slug: str) -> bool:
    p = CAMPAIGNS_DIR / f"{slug}.json"
    if p.exists():
        p.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# API pública (enruta al backend; misma firma que antes)
# ---------------------------------------------------------------------------
def save_campaign(camp: dict[str, Any]) -> str:
    """Guarda/actualiza una campaña. Devuelve el slug (id)."""
    data = _campaign_data(camp)
    if _use_supabase():
        return _sb_save(data, _client())
    return _file_save(data)


def list_campaigns() -> list[dict[str, Any]]:
    """Todas las campañas guardadas, más nuevas primero."""
    if _use_supabase():
        return _sb_list(_client())
    return _file_list()


def load_campaign(slug: str) -> dict[str, Any]:
    if _use_supabase():
        return _sb_load(slug, _client())
    return _file_load(slug)


def delete_campaign(slug: str) -> bool:
    """Borra una campaña. Devuelve True si existía."""
    if _use_supabase():
        return _sb_delete(slug, _client())
    return _file_delete(slug)

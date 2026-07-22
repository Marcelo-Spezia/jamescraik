"""Persistencia de leads (pipeline de outreach) detrás de una interfaz.

Principio del proyecto (CLAUDE.md): toda fuente externa vive detrás de un adapter.
La app usa `LeadStore`; el backend real es **Supabase** (Postgres), con un
**stub en memoria** para tests/dev sin credenciales.

Modelo de fila = tabla `leads` (ver migración SQL). Los campos base van como columnas;
las señales de enrichment (dinámicas por campaña) van en la columna `enrichment` jsonb.
El match del webhook de Expandi es por `linkedin_url` normalizada.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

STATUSES = ["qualified", "connection_sent", "accepted",
            "message_ready", "sent", "replied", "discarded"]

# claves que son columnas propias (no van al jsonb de enrichment)
_BASE_KEYS = {"id", "campaign_slug", "campaign_name", "name", "title", "company",
              "domain", "size", "industry", "location", "email", "linkedin",
              "linkedin_url", "tier", "reason", "status", "message", "notes",
              "created_at", "updated_at"}


def norm_linkedin(url: str) -> str | None:
    """Normaliza la URL de LinkedIn (clave de matcheo). Vacío → None."""
    u = (url or "").strip().lower()
    if not u:
        return None
    u = re.sub(r"^https?://", "", u).removeprefix("www.")
    u = u.split("?")[0].rstrip("/")
    return u or None


def lead_to_row(lead: dict[str, Any], campaign_slug: str,
                campaign_name: str = "") -> dict[str, Any]:
    """Dict de lead (salida de qualify/enrich) → fila de la tabla `leads`."""
    enrichment = {k: v for k, v in lead.items()
                  if k not in _BASE_KEYS and v not in (None, "")}
    return {
        "campaign_slug": campaign_slug,
        "campaign_name": campaign_name or None,
        "name": lead.get("name") or None,
        "title": lead.get("title") or None,
        "company": lead.get("company") or None,
        "domain": lead.get("domain") or None,
        "size": lead.get("size") or None,
        "industry": lead.get("industry") or None,
        "location": lead.get("location") or None,
        "email": lead.get("email") or None,
        "linkedin_url": norm_linkedin(lead.get("linkedin") or lead.get("linkedin_url") or ""),
        "tier": lead.get("tier") or None,
        "reason": lead.get("reason") or None,
        "enrichment": enrichment,
    }


def row_to_lead(row: dict[str, Any]) -> dict[str, Any]:
    """Fila de `leads` → dict plano para la UI / generación de mensaje
    (mezcla el enrichment jsonb de vuelta al nivel raíz)."""
    enr = row.get("enrichment") or {}
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "message": row.get("message"),
        "notes": row.get("notes"),
        "campaign_slug": row.get("campaign_slug"),
        "campaign_name": row.get("campaign_name"),
        "name": row.get("name"), "title": row.get("title"), "company": row.get("company"),
        "domain": row.get("domain"), "size": row.get("size"),
        "industry": row.get("industry"), "location": row.get("location"),
        "email": row.get("email"), "linkedin": row.get("linkedin_url"),
        "tier": row.get("tier"), "reason": row.get("reason"),
        "updated_at": row.get("updated_at"),
        **enr,
    }


# ---------------------------------------------------------------------------
# Stub en memoria (tests / dev sin credenciales)
# ---------------------------------------------------------------------------
class InMemoryLeadStore:
    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def upsert_leads(self, leads: list[dict[str, Any]], campaign_slug: str,
                     campaign_name: str = "") -> tuple[int, int]:
        inserted = updated = 0
        for ld in leads:
            row = lead_to_row(ld, campaign_slug, campaign_name)
            lu = row["linkedin_url"]
            existing = next((r for r in self._rows if lu and r["campaign_slug"] == campaign_slug
                             and r["linkedin_url"] == lu), None)
            if existing:  # preserva pipeline (status/message); actualiza calificación
                existing.update({"tier": row["tier"], "reason": row["reason"],
                                 "enrichment": row["enrichment"],
                                 "campaign_name": row["campaign_name"]})
                updated += 1
            else:
                self._rows.append({**row, "id": str(uuid.uuid4()), "status": "qualified",
                                   "message": None, "notes": None})
                inserted += 1
        return inserted, updated

    def list_leads(self, campaign_slug: str | None = None,
                   statuses: list[str] | None = None) -> list[dict[str, Any]]:
        rows = [r for r in self._rows
                if (campaign_slug is None or r["campaign_slug"] == campaign_slug)
                and (statuses is None or r["status"] in statuses)]
        return [row_to_lead(r) for r in rows]

    def update_fields(self, lead_id: str, fields: dict[str, Any]) -> None:
        for r in self._rows:
            if r["id"] == lead_id:
                r.update(fields)
                return

    def set_status_by_linkedin(self, linkedin_url: str, status: str,
                               campaign_slug: str | None = None) -> int:
        lu = norm_linkedin(linkedin_url)
        n = 0
        for r in self._rows:
            if r["linkedin_url"] == lu and (campaign_slug is None
                                            or r["campaign_slug"] == campaign_slug):
                r["status"] = status
                n += 1
        return n


# ---------------------------------------------------------------------------
# Adapter real: Supabase (Postgres)
# ---------------------------------------------------------------------------
class SupabaseLeadStore:
    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            from supabase import create_client
            client = create_client(os.environ["SUPABASE_URL"],
                                   os.environ["SUPABASE_SERVICE_KEY"])
        self.c = client

    def upsert_leads(self, leads: list[dict[str, Any]], campaign_slug: str,
                     campaign_name: str = "") -> tuple[int, int]:
        rows = [lead_to_row(ld, campaign_slug, campaign_name) for ld in leads]
        lis = [r["linkedin_url"] for r in rows if r["linkedin_url"]]
        existing: dict[str, str] = {}
        if lis:
            res = (self.c.table("leads").select("id,linkedin_url")
                   .eq("campaign_slug", campaign_slug).in_("linkedin_url", lis).execute())
            existing = {r["linkedin_url"]: r["id"] for r in res.data}
        to_insert, updated = [], 0
        for r in rows:
            lu = r["linkedin_url"]
            if lu and lu in existing:  # preserva pipeline; actualiza calificación
                (self.c.table("leads").update({
                    "tier": r["tier"], "reason": r["reason"],
                    "enrichment": r["enrichment"], "campaign_name": r["campaign_name"],
                }).eq("id", existing[lu]).execute())
                updated += 1
            else:
                to_insert.append(r)
        if to_insert:
            self.c.table("leads").insert(to_insert).execute()
        return len(to_insert), updated

    def list_leads(self, campaign_slug: str | None = None,
                   statuses: list[str] | None = None) -> list[dict[str, Any]]:
        q = self.c.table("leads").select("*")
        if campaign_slug:
            q = q.eq("campaign_slug", campaign_slug)
        if statuses:
            q = q.in_("status", statuses)
        res = q.order("updated_at", desc=True).execute()
        return [row_to_lead(r) for r in res.data]

    def update_fields(self, lead_id: str, fields: dict[str, Any]) -> None:
        self.c.table("leads").update(fields).eq("id", lead_id).execute()

    def set_status_by_linkedin(self, linkedin_url: str, status: str,
                               campaign_slug: str | None = None) -> int:
        lu = norm_linkedin(linkedin_url)
        if not lu:
            return 0
        q = self.c.table("leads").update({"status": status}).eq("linkedin_url", lu)
        if campaign_slug:
            q = q.eq("campaign_slug", campaign_slug)
        res = q.execute()
        return len(res.data)


def get_store() -> Any:
    """Devuelve el store real (Supabase) si hay credenciales; si no, el stub en memoria."""
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"):
        return SupabaseLeadStore()
    return InMemoryLeadStore()

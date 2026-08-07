"""Enrichment de company + persona vía Exa (web-research grounded), detrás de interfaz.

Complementa Apollo (hard-data de company) y Clay (posteos de LinkedIn). Un solo `agent/run`
por lead cubre company (funding/hiring/geo) + persona (actividad pública, contenido,
movimientos de carrera, prensa), cada dato con su fuente.

Async fire→poll (Exa no manda webhook, poleamos nosotros):
- request_enrichment(lead) → crea el run, devuelve run_id (o None si no hay con qué anclar).
- poll(run_id)            → None si sigue corriendo; dict parseado si terminó.

Sin EXA_API_KEY → StubExaSource (el flujo sigue sin Exa). La key se lee del entorno y
NUNCA se loguea. Ver EXA-ENRICH-DESIGN.md.
"""

from __future__ import annotations

import os
from typing import Any

_BASE = "https://api.exa.ai"
_TERMINAL = {"completed", "failed", "cancelled"}

# Cada dato pide su source_url → todo campo es auditable.
_FIELD = {"type": "object", "properties": {
    "value": {"type": ["string", "null"]},
    "source_url": {"type": ["string", "null"], "format": "uri"}}}

AGENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "company": {"type": "object", "properties": {
            "funding": {"type": "object", "properties": {
                "stage": {"type": ["string", "null"]},
                "amount_usd": {"type": ["number", "null"]},
                "date": {"type": ["string", "null"]},
                "source_url": {"type": ["string", "null"], "format": "uri"}}},
            "hiring": _FIELD,
            "geo_expansion": _FIELD}},
        "person": {"type": "object", "properties": {
            "public_activity": _FIELD,
            "content": _FIELD,
            "career_moves": _FIELD,
            "press": _FIELD}},
    },
}


def _query(lead: dict[str, Any]) -> str:
    domain = (lead.get("domain") or "").strip()
    name = (lead.get("name") or "").strip()
    title = (lead.get("title") or "").strip()
    company = (lead.get("company") or "").strip()
    linkedin = (lead.get("linkedin") or lead.get("linkedin_url") or "").strip()
    who = f"the person {name}" + (f", {title}" if title else "")
    who += f" at {company}" if company else ""
    who += f" (LinkedIn: {linkedin})" if linkedin else ""
    where = f"the company at {domain}" if domain else "the company"
    return (
        f"For {where} and {who}: find (A) about the company — its most recent funding "
        "round, whether it is actively hiring technical roles, and any recent geographic "
        "expansion; and (B) about that specific person — recent public activity (talks, "
        "podcasts, interviews), content they authored, career moves, and press mentions. "
        "Anchor the person by the LinkedIn URL. Return null for anything you cannot ground "
        "in a source."
    )


def _field(node: Any) -> dict[str, str] | None:
    """{value, source_url} → {'v','src'} o None si no hay valor."""
    if not isinstance(node, dict):
        return None
    val = (node.get("value") or "").strip() if isinstance(node.get("value"), str) else None
    if not val:
        return None
    return {"v": val, "src": (node.get("source_url") or "").strip()}


def _funding(node: Any) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    stage = node.get("stage") or None
    amount = node.get("amount_usd")
    date = node.get("date") or None
    if not (stage or amount or date):
        return None
    return {"stage": stage, "amount_usd": amount, "date": date,
            "src": (node.get("source_url") or "").strip()}


def _parse(data: dict[str, Any]) -> dict[str, Any]:
    """Respuesta cruda del run → shape guardable. Tolerante: si algo falta, queda None."""
    structured = ((data.get("output") or {}).get("structured")) or {}
    comp = structured.get("company") or {}
    pers = structured.get("person") or {}
    return {
        "run_id": data.get("id"),
        "status": data.get("status"),
        "company": {"funding": _funding(comp.get("funding")),
                    "hiring": _field(comp.get("hiring")),
                    "geo": _field(comp.get("geo_expansion"))},
        "person": {"public_activity": _field(pers.get("public_activity")),
                   "content": _field(pers.get("content")),
                   "career_moves": _field(pers.get("career_moves")),
                   "press": _field(pers.get("press"))},
    }


class StubExaSource:
    """Sin EXA_API_KEY: no hace nada (el enrichment sigue sin Exa)."""

    configured = False

    def request_enrichment(self, lead: dict[str, Any]) -> str | None:
        return None

    def poll(self, run_id: str) -> dict[str, Any] | None:
        return None


class ExaEnrichmentSource:
    """Adapter real: un agent/run (company + persona) por lead, effort medium FIJO."""

    configured = True

    def __init__(self, api_key: str | None = None, client: Any | None = None) -> None:
        self.api_key = api_key or os.environ["EXA_API_KEY"]
        self._client = client  # inyectable para tests

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "content-type": "application/json"}

    def _cl(self) -> tuple[Any, bool]:
        if self._client is not None:
            return self._client, False
        import httpx
        return httpx.Client(timeout=60), True

    def request_enrichment(self, lead: dict[str, Any]) -> str | None:
        """Dispara el run. Devuelve run_id, o None si no hay dominio ni LinkedIn con qué anclar."""
        if not ((lead.get("domain") or "").strip()
                or (lead.get("linkedin") or lead.get("linkedin_url") or "").strip()):
            return None
        body = {"query": _query(lead), "effort": "medium", "outputSchema": AGENT_OUTPUT_SCHEMA}
        client, owns = self._cl()
        try:
            resp = client.post(f"{_BASE}/agent/runs", headers=self._headers(), json=body)
            resp.raise_for_status()
            return resp.json().get("id")
        finally:
            if owns:
                client.close()

    def poll(self, run_id: str) -> dict[str, Any] | None:
        """None si el run sigue corriendo; dict parseado si llegó a estado terminal."""
        client, owns = self._cl()
        try:
            resp = client.get(f"{_BASE}/agent/runs/{run_id}", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns:
                client.close()
        if data.get("status") not in _TERMINAL:
            return None
        return _parse(data)


def get_source() -> Any:
    """Exa real si hay EXA_API_KEY; si no, el stub."""
    if os.getenv("EXA_API_KEY"):
        return ExaEnrichmentSource()
    return StubExaSource()

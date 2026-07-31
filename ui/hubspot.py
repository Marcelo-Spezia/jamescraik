"""Métricas de HubSpot (reuniones agendadas, oportunidades) detrás de una interfaz — adapter.

HubSpot es una fuente externa: vive detrás de un adapter (principio del proyecto).
El motor/UI nunca importa el SDK ni arma requests de HubSpot fuera de acá.

Cómo se atribuye una reunión/oportunidad a una campaña (decidido con datos reales del portal):
- **Match por LinkedIn URL**: los contactos ya traen la URL vía el sync LinkedIn↔HubSpot
  (`exp_contact_profile_url` / `hs_linkedin_url`). La normalizamos igual que en leads_store y la
  cruzamos contra los leads de cada campaña (que viven en Supabase). Fallback: email.
- **Reunión agendada** = el contacto tiene `engagements_last_meeting_booked` seteado.
- **Oportunidad** = el contacto tiene `num_associated_deals > 0` (un Deal en el pipeline).

En vez de empujar todas las URLs de la campaña a HubSpot, traemos SOLO los contactos que ya
convirtieron (tienen reunión o deal) — que son poquísimos — y los bucketeamos por campaña del
lado nuestro. Escala con los convertidos, no con el total de contactos.

Config: HUBSPOT_TOKEN (Private App con scope crm.objects.contacts.read). Sin token → stub,
la vista de Métricas muestra "—".
"""

from __future__ import annotations

import os
from typing import Any

import leads_store  # para norm_linkedin (modelo canónico)

HUBSPOT_BASE = "https://api.hubapi.com"
_SEARCH_URL = f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search"
_PROPS = ["hs_linkedin_url", "exp_contact_profile_url", "email",
          "engagements_last_meeting_booked", "num_associated_deals"]

# Contrato de conversions(): dos mapas de identificador → {"meeting": bool, "deals": int}.
Conversions = dict[str, dict[str, dict[str, Any]]]


def _empty() -> Conversions:
    return {"by_linkedin": {}, "by_email": {}}


def _merge(index: dict[str, dict[str, Any]], key: str, rec: dict[str, Any]) -> None:
    """Suma un contacto al índice; si el id se repite, combina (OR reunión, max deals)."""
    cur = index.get(key)
    if cur is None:
        index[key] = dict(rec)
    else:
        cur["meeting"] = cur["meeting"] or rec["meeting"]
        cur["deals"] = max(cur["deals"], rec["deals"])


def _index_contacts(contacts: list[dict[str, Any]]) -> Conversions:
    """Arma los mapas by_linkedin / by_email a partir de las properties de cada contacto."""
    conv = _empty()
    for props in contacts:
        rec = {"meeting": bool(props.get("engagements_last_meeting_booked")),
               "deals": int(props.get("num_associated_deals") or 0)}
        raw_url = props.get("hs_linkedin_url") or props.get("exp_contact_profile_url") or ""
        lk = leads_store.norm_linkedin(raw_url)
        if lk:
            _merge(conv["by_linkedin"], lk, rec)
        em = (props.get("email") or "").strip().lower()
        if em:
            _merge(conv["by_email"], em, rec)
    return conv


class StubHubSpotSource:
    """Sin token: no hay datos → la UI muestra "—"."""

    configured = False

    def conversions(self) -> Conversions:
        return _empty()


class HubSpotSource:
    """Adapter real: consulta la Search API de contactos por reuniones/deals."""

    configured = True

    def __init__(self, token: str | None = None, client: Any | None = None) -> None:
        self.token = token or os.environ["HUBSPOT_TOKEN"]
        self._client = client  # inyectable para tests

    def conversions(self) -> Conversions:
        return _index_contacts(self._fetch_converted())

    def _fetch_converted(self) -> list[dict[str, Any]]:
        """Contactos con reunión agendada O con ≥1 deal (los dos filterGroups van en OR)."""
        body = {
            "filterGroups": [
                {"filters": [
                    {"propertyName": "exp_contact_profile_url", "operator": "HAS_PROPERTY"},
                    {"propertyName": "engagements_last_meeting_booked", "operator": "HAS_PROPERTY"},
                ]},
                {"filters": [
                    {"propertyName": "exp_contact_profile_url", "operator": "HAS_PROPERTY"},
                    {"propertyName": "num_associated_deals", "operator": "GT", "value": "0"},
                ]},
            ],
            "properties": _PROPS,
            "limit": 100,
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        client, owns = self._client, False
        if client is None:
            import httpx
            client, owns = httpx.Client(timeout=30), True
        out: list[dict[str, Any]] = []
        try:
            after = None
            for _ in range(50):  # tope de páginas: es un set chico
                if after:
                    body["after"] = after
                resp = client.post(_SEARCH_URL, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                out.extend(x.get("properties", {}) for x in data.get("results", []))
                after = (data.get("paging", {}).get("next", {}) or {}).get("after")
                if not after:
                    break
        finally:
            if owns:
                client.close()
        return out


def get_source() -> Any:
    """HubSpot real si hay token; si no, el stub."""
    if os.getenv("HUBSPOT_TOKEN"):
        return HubSpotSource()
    return StubHubSpotSource()

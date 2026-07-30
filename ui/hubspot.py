"""Métricas de HubSpot (reuniones agendadas, oportunidades) detrás de una interfaz — seam.

HubSpot es una fuente externa: vive detrás de un adapter (principio del proyecto).
Hoy: stub que devuelve None → la vista de Métricas muestra "—". El adapter real se
enchufa cuando haya token (private app) + se defina el match (por email del lead o por
una propiedad de campaña en HubSpot).
"""

from __future__ import annotations

import os
from typing import Any


class StubHubSpotSource:
    configured = False

    def metrics(self, campaign_slug: str, emails: list[str] | None = None) -> dict | None:
        return None  # no conectado → la UI muestra "—"


def get_source() -> Any:
    """HubSpot real si hay token; si no, el stub. (Adapter real pendiente.)"""
    if os.getenv("HUBSPOT_TOKEN"):
        # adapter real pendiente: match por email del lead o propiedad de campaña
        raise NotImplementedError(
            "Adapter de HubSpot pendiente: definí el match (email del lead o propiedad de "
            "campaña) y conectalo en hubspot.py.")
    return StubHubSpotSource()

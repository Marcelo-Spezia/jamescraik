"""Actividad de LinkedIn (posteos recientes) detrás de una interfaz — Fase 2.

Restricción dura: LinkedIn NO tiene API pública para esto y scrapearlo va contra sus
ToS. Por eso la actividad viene de un PROVEEDOR externo compatible (Clay), detrás de
este adapter — el motor nunca habla directo con LinkedIn.

Dos modos de proveedor:
- sync  (StubActivitySource): devuelve la actividad en el momento. Para dev/demo.
- async (ClayActivitySource): Clay no responde al instante. Le DISPARAMOS el pedido
  (POST a la webhook de entrada de la tabla de Clay) y el resultado vuelve más tarde a
  nuestra Edge Function `clay-webhook`, que guarda leads.activity (match por lead_id).
"""

from __future__ import annotations

import os
from typing import Any


def _demo_sample(linkedin_url: str) -> dict[str, Any]:
    return {
        "summary": "[DEMO] Viene posteando sobre expansión regional y sumó un VP de "
                   "Ingeniería; reaccionó a contenido sobre modernización de plataformas.",
        "items": [
            {"type": "post", "text": "[DEMO] Anunciamos apertura de oficina en México…"},
        ],
        "source": "demo",
    }


class StubActivitySource:
    """Sin proveedor: None (degradación elegante). En modo demo, una muestra [DEMO]."""

    mode = "sync"

    def fetch_activity(self, linkedin_url: str) -> dict[str, Any] | None:
        if os.getenv("ICP_ACTIVITY_DEMO") == "1" and (linkedin_url or "").strip():
            return _demo_sample(linkedin_url)
        return None


class ClayActivitySource:
    """Dispara el enriquecimiento en Clay. El resultado NO vuelve acá: llega asíncrono
    a la Edge Function `clay-webhook`. `request_activity` solo manda el pedido."""

    mode = "async"

    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ["CLAY_WEBHOOK_URL"]

    def request_activity(self, lead_id: str, linkedin_url: str, poster: Any | None = None) -> bool:
        """POST {lead_id, linkedin_url} a la webhook de entrada de la tabla de Clay.
        Devuelve True si se envió. `poster` inyectable para tests."""
        if not (linkedin_url or "").strip():
            return False
        if poster is None:
            import httpx
            poster = lambda u, j: httpx.post(u, json=j, timeout=30)  # noqa: E731
        resp = poster(self.url, {"lead_id": lead_id, "linkedin_url": linkedin_url})
        resp.raise_for_status()
        return True


def get_source() -> Any:
    """Clay si hay CLAY_WEBHOOK_URL; si no, el stub (demo/None)."""
    if os.getenv("CLAY_WEBHOOK_URL"):
        return ClayActivitySource()
    return StubActivitySource()

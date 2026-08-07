"""Cliente httpx MÍNIMO de Exa: dos endpoints, sin SDK (por diseño).

- Company Search  (POST /search)      → barato, para los 3 atributos.
- Agent API       (POST /agent/runs)  → async, para last_funding + exploratorios.

Auth: header `x-api-key`. La key se lee de EXA_API_KEY de forma perezosa (recién al
llamar), para que importar este módulo no requiera credenciales (tests offline).
NUNCA se imprime/loguea el valor de la key.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

_BASE = "https://api.exa.ai"
_TERMINAL = {"completed", "failed", "cancelled"}

# El schema pide, junto a cada valor, su source_url → todo campo es auditable.
AGENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "last_funding": {
            "type": ["object", "null"],
            "properties": {
                "stage": {"type": ["string", "null"]},
                "amount_usd": {"type": ["number", "null"]},
                "date": {"type": ["string", "null"]},
                "source_url": {"type": ["string", "null"], "format": "uri"},
            },
        },
        "hiring_signal": {
            "type": "object",
            "properties": {
                "value": {"type": ["string", "null"]},
                "source_url": {"type": ["string", "null"], "format": "uri"},
            },
        },
        "geo_expansion_signal": {
            "type": "object",
            "properties": {
                "value": {"type": ["string", "null"]},
                "source_url": {"type": ["string", "null"], "format": "uri"},
            },
        },
    },
}


def _api_key() -> str:
    key = os.getenv("EXA_API_KEY")
    if not key:
        raise RuntimeError("Falta la variable de entorno EXA_API_KEY (agregala al .env).")
    return key


def _headers() -> dict[str, str]:
    return {"x-api-key": _api_key(), "content-type": "application/json"}


def company_search(name: str, domain: str, client: httpx.Client) -> dict[str, Any]:
    """POST /search (category=company). Devuelve el JSON crudo."""
    body = {
        "query": f"{name} {domain}".strip(),
        "category": "company",
        "type": "auto",
        "numResults": 3,
    }
    resp = client.post(f"{_BASE}/search", headers=_headers(), json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()


def agent_run(domain: str, client: httpx.Client, effort: str = "medium",
              timeout_s: int = 180) -> dict[str, Any]:
    """Crea un run del Agent API y polea hasta estado terminal. Devuelve el JSON crudo final.

    effort FIJO (nunca 'auto': factura por consumo). Poll con backoff, tope `timeout_s`.
    """
    query = (
        f"For the company at {domain}, find its most recent funding round, whether it is "
        "actively hiring technical roles, and any recent geographic expansion. Return null "
        "for anything you cannot ground in a source."
    )
    body = {"query": query, "effort": effort, "outputSchema": AGENT_OUTPUT_SCHEMA}
    created = client.post(f"{_BASE}/agent/runs", headers=_headers(), json=body, timeout=60)
    created.raise_for_status()
    run_id = created.json().get("id")
    if not run_id:
        raise RuntimeError(f"Exa no devolvió id de run para {domain}: {created.text[:200]}")

    deadline = time.monotonic() + timeout_s
    delay = 2.0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        got = client.get(f"{_BASE}/agent/runs/{run_id}", headers=_headers(), timeout=60)
        got.raise_for_status()
        last = got.json()
        if last.get("status") in _TERMINAL:
            return last
        time.sleep(delay)
        delay = min(delay * 1.5, 15.0)
    raise TimeoutError(f"Exa agent run {run_id} ({domain}) no terminó en {timeout_s}s")

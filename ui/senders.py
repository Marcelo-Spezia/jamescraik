"""Perfiles de remitente (SDRs) — la 'voz' con la que se escribe cada respuesta.

Nicolás tiene un chat por SDR con su forma de escribir; acá ese perfil es dato editable:
nombre, rol, base de credibilidad, descripción de voz y 2-3 mensajes de ejemplo (few-shot).
Persistencia durable en Supabase (tabla `senders`) con fallback a archivos (dev/tests),
mismo patrón que campaigns.py. Se siembra con los 3 del contexto de ventas (§5 de
making_sense.md) si todavía no hay ninguno.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SENDERS_DIR = PROJECT_ROOT / "senders"
_TABLE = "senders"

# Sembrado desde la calibración de tono por sender del contexto de ventas.
DEFAULT_SENDERS: list[dict[str, Any]] = [
    {"slug": "cesar-ceo", "name": "Cesar", "role": "CEO",
     "credibility": "Fundador/CEO; puede hablar con autoridad de tendencias de la industria "
                    "y referir informalmente a 'las empresas con las que trabajamos'.",
     "voice": "Peer-to-peer, energía founder-to-founder. Nunca sobre-vende. Curiosidad de "
              "operador, no pitch.",
     "examples": []},
    {"slug": "fernando-cro", "name": "Fernando", "role": "CRO",
     "credibility": "Líder senior de revenue/partnerships; puede referir patrones del "
                    "portfolio de clientes.",
     "voice": "Tono de líder senior de revenue. Un poco más directo sobre el problema de "
              "negocio que Cesar, sin ser agresivo.",
     "examples": []},
    {"slug": "rodrigo-bdr", "name": "Rodrigo", "role": "BDR",
     "credibility": "Fluidez de sector + credibilidad por clientes nombrados (ej. en fintech: "
                    "OnDeck, Credit Sesame, LendKey, Chatham Financial — como red propia).",
     "voice": "NO escribe como par de un CTO/VP: se apoya en fluidez de sector y clientes "
              "nombrados como prueba social. Humilde, directo, embebido en el rubro; nunca "
              "corporativo ni genérico.",
     "examples": []},
]


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "remitente"


def _sender_data(sender: dict[str, Any]) -> dict[str, Any]:
    slug = sender.get("slug") or _slug(sender.get("name", ""))
    now = datetime.now(UTC).isoformat()
    return {
        "slug": slug,
        "name": sender.get("name", "") or slug,
        "role": sender.get("role", ""),
        "credibility": sender.get("credibility", ""),
        "voice": sender.get("voice", ""),
        "examples": list(sender.get("examples", [])),
        "created_at": sender.get("created_at", now),
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
def _use_supabase() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


def _client() -> Any:
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _sb_save(data: dict[str, Any], client: Any) -> str:
    client.table(_TABLE).upsert(data, on_conflict="slug").execute()
    return data["slug"]


def _sb_list(client: Any) -> list[dict[str, Any]]:
    return (client.table(_TABLE).select("*").order("created_at", desc=False).execute().data) or []


def _sb_delete(slug: str, client: Any) -> bool:
    return bool(client.table(_TABLE).delete().eq("slug", slug).execute().data)


def _file_save(data: dict[str, Any]) -> str:
    SENDERS_DIR.mkdir(parents=True, exist_ok=True)
    (SENDERS_DIR / f"{data['slug']}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data["slug"]


def _file_list() -> list[dict[str, Any]]:
    if not SENDERS_DIR.exists():
        return []
    out = [json.loads(p.read_text(encoding="utf-8")) for p in SENDERS_DIR.glob("*.json")]
    out.sort(key=lambda s: s.get("created_at", ""))
    return out


def _file_delete(slug: str) -> bool:
    p = SENDERS_DIR / f"{slug}.json"
    if p.exists():
        p.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def save_sender(sender: dict[str, Any]) -> str:
    data = _sender_data(sender)
    if _use_supabase():
        return _sb_save(data, _client())
    return _file_save(data)


def list_senders() -> list[dict[str, Any]]:
    """Todos los remitentes. Si no hay ninguno, siembra los 3 del contexto y los devuelve."""
    existing = _sb_list(_client()) if _use_supabase() else _file_list()
    if existing:
        return existing
    for s in DEFAULT_SENDERS:
        save_sender(s)
    return _sb_list(_client()) if _use_supabase() else _file_list()


def load_sender(slug: str) -> dict[str, Any] | None:
    return next((s for s in list_senders() if s.get("slug") == slug), None)


def delete_sender(slug: str) -> bool:
    if _use_supabase():
        return _sb_delete(slug, _client())
    return _file_delete(slug)

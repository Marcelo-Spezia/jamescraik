"""Base de contexto de Making Sense (Fase 1).

Un documento vivo (markdown) con servicios, propuesta de valor, diferenciadores,
casos de éxito, aprendizajes y verticales foco. El agente lo inyecta en sus prompts
(chat de campaña y match de propuesta de valor) para groundear y recomendar mejor.

Persistencia DURABLE en Supabase cuando hay credenciales (tabla `app_context`, una fila
key='making_sense'); si no, fallback a archivo local (context/making_sense.md). Motivo:
en Streamlit Cloud el disco es efímero → el contexto editado se perdía en cada redeploy.
Se siembra desde el contexto de ventas de MS (context/making_sense.md) si todavía no hay
contexto guardado — NO desde la documentación del proyecto.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTEXT_FILE = PROJECT_ROOT / "context" / "making_sense.md"
# El seed ES el contexto de ventas de Making Sense (mismo archivo). En el deploy, con
# Supabase vacío, se cae acá → hay que sembrar el KB de VENTAS, no los docs del proyecto.
SEED_SOURCE = CONTEXT_FILE
_TABLE = "app_context"
_KEY = "making_sense"

_TEMPLATE = """\
# Contexto de Making Sense

## Qué hacemos / propuesta de valor
(describí los servicios y qué problema resolvés)

## Diferenciadores
(qué los hace distintos)

## Casos de éxito / clientes
(ejemplos que sirven de prueba social y para inferir fit)

## Aprendizajes de campañas
(qué segmentos/rubros convirtieron, qué no)

## Verticales / segmentos foco
"""


def _use_supabase() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


def _client() -> Any:
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _seed() -> str:
    """Contexto inicial cuando no hay nada guardado (semilla del proyecto o template)."""
    if SEED_SOURCE.exists():
        return SEED_SOURCE.read_text(encoding="utf-8")
    return _TEMPLATE


# ---------------------------------------------------------------------------
# Backend Supabase (client inyectable para tests)
# ---------------------------------------------------------------------------
def _sb_saved_text(client: Any) -> str | None:
    res = client.table(_TABLE).select("content").eq("key", _KEY).execute()
    return res.data[0]["content"] if res.data else None


def _sb_save(text: str, client: Any) -> None:
    client.table(_TABLE).upsert({"key": _KEY, "content": text}, on_conflict="key").execute()


# ---------------------------------------------------------------------------
# API pública (enruta al backend; misma firma que antes)
# ---------------------------------------------------------------------------
def load_context() -> str:
    """Devuelve el contexto guardado; si no hay, siembra (no escribe hasta guardar)."""
    if _use_supabase():
        saved = _sb_saved_text(_client())
        return saved if saved is not None else _seed()
    if CONTEXT_FILE.exists():
        return CONTEXT_FILE.read_text(encoding="utf-8")
    return _seed()


def save_context(text: str) -> None:
    if _use_supabase():
        _sb_save(text, _client())
        return
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(text, encoding="utf-8")


def has_saved_context() -> bool:
    if _use_supabase():
        return _sb_saved_text(_client()) is not None
    return CONTEXT_FILE.exists()

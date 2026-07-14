"""Base de contexto de Making Sense (Fase 1).

Un documento vivo (markdown) con servicios, propuesta de valor, diferenciadores,
casos de éxito, aprendizajes y verticales foco. El agente lo inyecta en sus prompts
(chat de campaña y match de propuesta de valor) para groundear y recomendar mejor.

Se siembra desde Project_Knowledge_Contexto.md si todavía no hay contexto guardado.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTEXT_FILE = PROJECT_ROOT / "context" / "making_sense.md"
SEED_SOURCE = PROJECT_ROOT / "Project_Knowledge_Contexto.md"

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


def load_context() -> str:
    """Devuelve el contexto guardado; si no hay, siembra desde el doc del proyecto
    o un template. (No escribe hasta que el usuario guarde.)"""
    if CONTEXT_FILE.exists():
        return CONTEXT_FILE.read_text(encoding="utf-8")
    if SEED_SOURCE.exists():
        return SEED_SOURCE.read_text(encoding="utf-8")
    return _TEMPLATE


def save_context(text: str) -> None:
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(text, encoding="utf-8")


def has_saved_context() -> bool:
    return CONTEXT_FILE.exists()

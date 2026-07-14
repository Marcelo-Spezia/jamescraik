"""Asistente con IA para crear un ICP desde una descripción en texto libre.

El usuario describe a su cliente ideal en palabras; Claude propone el modelo
SIMPLE (el mismo que usa el builder): importancia de cada característica, tamaño,
regiones, persona y deal-breakers. Salida estructurada (JSON schema) garantiza
un resultado válido que se puede cargar directo en el formulario.

Claude vive detrás de la interfaz (provider configurable por env, igual que el
JudgeModel). NO se llama a la API hasta invocar `propose_icp`.
"""

from __future__ import annotations

import json
import os
from typing import Any

import icp_translate as tr

MODEL = os.getenv("ICP_JUDGE_MODEL", "claude-opus-4-8")

_REGIONS = list(tr.REGION_LABELS)          # NA, LATAM, EMEA, APAC
_SENIORITY = list(tr.SENIORITY_LABELS)     # c_level, vp, director, manager
_DEPARTMENTS = list(tr.DEPARTMENT_LABELS)  # engineering, product, data, ops, marketing, sales
_TRAITS = list(tr.FUZZY_CATALOG)           # tech_enabled, business_services_fit, build_intent
_DEALBREAKERS = ["too_small", "gov_edu", "outside_region"]
_IMPORTANCE = ["suma", "importante", "imprescindible"]

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "size": {"type": "array", "items": {"type": "integer"}},
        "regions": {"type": "array", "items": {"type": "string", "enum": _REGIONS}},
        "seniority": {"type": "array", "items": {"type": "string", "enum": _SENIORITY}},
        "departments": {"type": "array", "items": {"type": "string", "enum": _DEPARTMENTS}},
        "ideal": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "enum": _TRAITS},
                    "importance": {"type": "string", "enum": _IMPORTANCE},
                },
                "required": ["id", "importance"],
                "additionalProperties": False,
            },
        },
        "dealbreakers": {"type": "array", "items": {"type": "string", "enum": _DEALBREAKERS}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "titles": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": ["name", "size", "regions", "seniority", "departments",
                 "ideal", "dealbreakers", "keywords", "titles", "reasoning"],
    "additionalProperties": False,
}

_SYSTEM = f"""\
Sos un experto en definir Ideal Customer Profiles (ICP) para ventas B2B.
A partir de la descripción del cliente ideal que te da el usuario, completá un
modelo estructurado. Mapeá SIEMPRE a las opciones disponibles; no inventes valores.

Características (campo `ideal`): asigná importancia (suma / importante / imprescindible)
SOLO a las que apliquen según la descripción (omití las que no correspondan):
- tech_enabled: usa software/tecnología como parte central de cómo entrega su servicio.
- business_services_fit: es una empresa de servicios profesionales (legal, financiero,
  seguros, logística, staffing, salud…), no un producto físico ni un SaaS de consumo masivo.
- build_intent: invierte en desarrollo de software a medida o tiene equipos de producto/ingeniería.

`size`: rango [min, max] de empleados (inferí algo razonable; ej. mid-market = [200, 2000]).
`regions`: subconjunto de {_REGIONS}.
`seniority` y `departments`: a quién se le vende, subconjunto de las opciones.
`dealbreakers` (descartes): too_small (muy chicas <50), gov_edu (gobierno/educación),
outside_region (fuera de las regiones elegidas).
`keywords`: palabras clave de SECTOR/vertical para filtrar la búsqueda en la fuente
de datos (ej. para servicios legales → ["legal services", "law firms", "litigation"];
para staffing → ["staffing", "recruiting"]). Inferilas del rubro que describe el usuario.
Si el ICP es agnóstico al sector, dejá la lista vacía. Son en inglés (la fuente es Apollo).
`titles`: títulos ESPECÍFICOS del contacto a buscar que no entran en los buckets de
seniority/área (ej. ["Operating Partner", "Chief Digital Officer", "Head of RevOps"]).
Solo si el usuario menciona títulos puntuales; si no, dejá la lista vacía. En inglés.
`reasoning`: 1-2 frases explicando tu propuesta, para mostrarle al usuario.

Si la descripción no aclara algo, elegí un default sensato para servicios B2B."""


def _build_client():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise ImportError('Requiere el SDK de Anthropic: pip install -e ".[ui]"') from exc
    return anthropic.Anthropic()


def propose_icp(description: str, client: Any | None = None) -> dict[str, Any]:
    """Llama a Claude y devuelve un modelo SIMPLE listo para el builder.

    `client` inyectable para tests (sin API real).
    """
    client = client or _build_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": description}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return normalize(json.loads(text))


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Lleva la salida del modelo al modelo SIMPLE completo del builder."""
    size = data.get("size") or [200, 2000]
    if len(size) < 2:
        size = [size[0], size[0]] if size else [200, 2000]
    size = [int(size[0]), int(size[1])]
    if size[0] > size[1]:
        size = [size[1], size[0]]

    imp_by_id = {i["id"]: i["importance"] for i in data.get("ideal", []) if i.get("id") in _TRAITS}
    ideal = [
        {"id": tid, "label": tr.FUZZY_CATALOG[tid]["label"],
         "hint": tr.FUZZY_CATALOG[tid]["hint"], "importance": imp_by_id.get(tid)}
        for tid in _TRAITS
    ]

    return {
        "name": data.get("name", "").strip() or "Nuevo ICP",
        "status": "draft",
        "size": size,
        "regions": [r for r in data.get("regions", []) if r in _REGIONS] or ["NA"],
        "seniority": [s for s in data.get("seniority", []) if s in _SENIORITY] or ["c_level"],
        "departments": [d for d in data.get("departments", []) if d in _DEPARTMENTS],
        "ideal": ideal,
        "dealbreakers": [d for d in data.get("dealbreakers", []) if d in _DEALBREAKERS],
        "keywords": [str(k).strip() for k in data.get("keywords", []) if str(k).strip()],
        "titles": [str(t).strip() for t in data.get("titles", []) if str(t).strip()],
        "reasoning": data.get("reasoning", ""),
    }

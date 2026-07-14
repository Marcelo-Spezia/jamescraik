"""Builder multi-turno de campañas: chateás con Claude para definir la campaña.

- chat_reply: la respuesta conversacional (ida y vuelta) que ayuda a Nico a pensar.
- extract_campaign: al final, extrae la campaña estructurada de la charla
  (sales_nav_filters + rubric + value_prop + name) con salida estructurada.

Claude detrás de interfaz, configurable por env (igual que el resto).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any

MODEL = os.getenv("ICP_JUDGE_MODEL", "claude-opus-4-8")

INTRO = (
    "¡Hola! Te ayudo a definir la campaña. Contame:\n\n"
    "- ¿Qué estás ofreciendo y a quién querés llegar?\n"
    "- ¿Qué hace que un lead sea ideal vs. uno que no te sirve?\n\n"
    "Con eso vamos puliendo juntos los **filtros para Sales Navigator** (los más "
    "excluyentes) y la **rúbrica de calificación** (qué hace a un lead A/B/C/D)."
)

_SYSTEM_CHAT = """\
Sos un consultor de demand generation que ayuda al equipo de Making Sense (desarrollo
de software a medida y producto digital para empresas tech-enabled) a definir una
campaña de prospección outbound.

Tu objetivo es, conversando con ida y vuelta, ayudar a definir TRES cosas:
1. Filtros para Sales Navigator: los MÁS EXCLUYENTES (geo, tamaño de empresa, rol/seniority,
   industria si aplica). Pocos y gruesos — la calificación fina la hace la rúbrica después.
2. La rúbrica de calificación: qué hace a un lead tier A (ideal), B (bueno), C (marginal),
   D (no fit), en lenguaje natural.
3. La propuesta de valor de Making Sense para esta campaña (qué le resolvés a ese lead).

Guía la charla: hacé 1-2 preguntas por turno, proponé borradores concretos, y refiná
según lo que responda. Sé concreto y breve. Cuando sientas que hay suficiente, decile que
puede apretar 'Generar campaña' para guardar lo que definieron.
"""

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "sales_nav_filters": {"type": "array", "items": {"type": "string"}},
        "rubric": {"type": "string"},
        "value_prop": {"type": "string"},
        "enrichment_signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["label", "question"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["name", "sales_nav_filters", "rubric", "value_prop", "enrichment_signals"],
    "additionalProperties": False,
}

_SYSTEM_EXTRACT = """\
A partir de la conversación entre el usuario y el consultor, extraé la campaña definida.
- name: nombre corto de la campaña.
- sales_nav_filters: lista de filtros concretos para Sales Navigator (geo, tamaño, rol,
  industria…), los más excluyentes acordados.
- rubric: la rúbrica de calificación en lenguaje natural (qué hace a un lead A/B/C/D).
- value_prop: la propuesta de valor de Making Sense para esta campaña.
- enrichment_signals: qué señales de NEGOCIO conviene averiguar de cada lead calificado para
  armar el mensaje, SEGÚN esta campaña. Cada una con {label (corto), question (qué averiguar)}.
  Ej. fintech → inversión reciente, presión regulatoria; manufactura → sistemas legacy,
  transformación digital. NO incluyas tech stack como argumento (a Making Sense no le vende el
  stack). NO incluyas 'match de propuesta de valor' ni 'hook' (esos van siempre por defecto).
  Proponé 2-4 señales relevantes al rubro/objetivo de la campaña.
Si algo no quedó definido, completá un default sensato a partir del contexto.
"""


def _client(client: Any | None):
    if client is not None:
        return client
    import anthropic
    return anthropic.Anthropic()


def _api_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Saca turnos 'assistant' iniciales (la API exige que arranque con 'user')."""
    msgs = list(history)
    while msgs and msgs[0]["role"] != "user":
        msgs = msgs[1:]
    return msgs


def _with_context(system: str, context: str, lang: str = "es") -> str:
    directive = ("\n\nRespondé en español." if lang == "es"
                 else "\n\nRespond entirely in English.")
    system = system + directive
    if context and context.strip():
        header = "=== CONTEXTO DE MAKING SENSE (usalo para groundear y recomendar) ==="
        return f"{system}\n\n{header}\n{context}"
    return system


def chat_reply(history: list[dict[str, str]], client: Any | None = None, context: str = "",
               lang: str = "es") -> str:
    """Respuesta conversacional del consultor dada la historia del chat."""
    client = _client(client)
    resp = client.messages.create(
        model=MODEL, max_tokens=1024, system=_with_context(_SYSTEM_CHAT, context, lang),
        messages=_api_messages(history),
    )
    return next((b.text for b in resp.content if b.type == "text"), "")


def extract_campaign(history: list[dict[str, str]], client: Any | None = None,
                     context: str = "", lang: str = "es") -> dict[str, Any]:
    """Extrae la campaña estructurada de la conversación."""
    client = _client(client)
    transcript = "\n\n".join(f"{m['role']}: {m['content']}" for m in history)
    resp = client.messages.create(
        model=MODEL, max_tokens=1500, system=_with_context(_SYSTEM_EXTRACT, context, lang),
        messages=[{"role": "user", "content": transcript}],
        output_config={"format": {"type": "json_schema", "schema": _EXTRACT_SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = json.loads(text)
    import enrich
    signals = enrich.resolve_signals(data.get("enrichment_signals", []))
    return {
        "name": data.get("name", "").strip(),
        "sales_nav_filters": [str(f).strip() for f in data.get("sales_nav_filters", [])
                              if str(f).strip()],
        "rubric": data.get("rubric", ""),
        "value_prop": data.get("value_prop", ""),
        "enrichment_signals": signals,
    }


_SYSTEM_SUGGEST = """\
Sos un consultor de demand generation de Making Sense. Te paso una campaña (filtros de
Sales Navigator, rúbrica de calificación, propuesta de valor) y, si hay, los resultados
de la última calificación (distribución de tiers + motivos de los C/D).

Sugerí MEJORAS concretas y accionables, apoyándote en el contexto de Making Sense (dónde
gana, casos, aprendizajes). Agrupá por:
- Rúbrica (qué ajustar para separar mejor A/B/C/D)
- Filtros de Sales Navigator (qué sumar/sacar para traer menos ruido)
- Propuesta de valor (cómo afilarla para este segmento)
- Segmentos / rubros a priorizar o descartar
Priorizá lo de mayor impacto. Sé breve y concreto (viñetas). Si los resultados muestran
un patrón (ej. muchos D por un mismo motivo), señalalo y proponé el fix.
"""


def suggest_improvements(campaign: dict[str, Any], context: str = "",
                         results: list[dict[str, Any]] | None = None,
                         client: Any | None = None, lang: str = "es") -> str:
    """Recomendaciones proactivas para mejorar una campaña (Fase 2 del contexto)."""
    client = _client(client)
    filters = ", ".join(campaign.get("sales_nav_filters", [])) or "(ninguno)"
    parts = [
        f"Campaña: {campaign.get('name', '(sin nombre)')}",
        f"Filtros Sales Navigator: {filters}",
        f"Rúbrica:\n{campaign.get('rubric', '')}",
        f"Propuesta de valor:\n{campaign.get('value_prop', '')}",
    ]
    if results:
        counts = Counter(r.get("tier", "?") for r in results)
        parts.append("Resultados de la última calificación: "
                     + ", ".join(f"{t}:{counts.get(t, 0)}" for t in ["A", "B", "C", "D"]))
        low = [r for r in results if r.get("tier") in ("C", "D")][:8]
        if low:
            motivos = "\n".join(f"- {r.get('company', '')}: {r.get('reason', '')}" for r in low)
            parts.append("Motivos de C/D (muestra):\n" + motivos)
    user = "\n\n".join(parts) + "\n\nSugerí mejoras concretas y accionables para esta campaña."
    resp = client.messages.create(
        model=MODEL, max_tokens=1200, system=_with_context(_SYSTEM_SUGGEST, context, lang),
        messages=[{"role": "user", "content": user}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "")

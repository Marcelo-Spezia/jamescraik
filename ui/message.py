"""Generación del mensaje de outreach (LinkedIn post-conexión) para un lead.

Toma un lead ya calificado y enriquecido (con hook, value_prop_match, señales de
negocio) + la propuesta de valor + el contexto de Making Sense, y arma UN borrador
editable, en el idioma elegido. Claude detrás de interfaz, como el resto.
"""

from __future__ import annotations

import json
import os
from typing import Any

MODEL = os.getenv("ICP_JUDGE_MODEL", "claude-opus-4-8")

# campos del lead relevantes para el mensaje (los insights se suman aparte).
_LEAD_FIELDS = ["name", "title", "company", "industry", "location", "tier", "reason"]
# insights de enrichment que dan munición al mensaje (si están presentes).
_INSIGHT_KEYS = ["hook", "value_prop_match", "business_momentum", "role_focus",
                 "tech_maturity", "funding", "growth", "maturity"]


def _lang_directive(lang: str) -> str:
    return ("Escribí el mensaje en español rioplatense (vos)." if lang == "es"
            else "Write the message in English (address them as 'you').")


def _system(value_prop: str, context: str = "", lang: str = "es") -> str:
    vp = f"\n\nPropuesta de valor de Making Sense:\n{value_prop}" if value_prop else ""
    ctx = (f"\n\nContexto de Making Sense (para groundear, no para copiar):\n{context}"
           if context and context.strip() else "")
    return (
        "Sos parte del equipo de Making Sense y escribís el PRIMER mensaje de LinkedIn a un "
        "prospecto que YA aceptó la conexión. Objetivo: abrir conversación, NO vender ni "
        "pitchear.\n\n"
        "Reglas:\n"
        "- Breve: 2 a 4 oraciones (~400-600 caracteres). Cálido, humano y directo.\n"
        "- Personalizalo con el 'hook' y la situación del prospecto (su rol, su empresa, su "
        "momento de negocio). Que se note que NO es un mensaje masivo.\n"
        "- Conectá su contexto con lo que hace Making Sense de forma sutil (media frase), sin "
        "pitch agresivo ni lista de servicios.\n"
        "- Cerrá con una pregunta abierta o un CTA suave (ej. proponer una charla corta).\n"
        "- Primera persona plural (nosotros/Making Sense); tratá al prospecto de 'vos/tú'.\n"
        "- Sin emoji. Sin asunto ni firma. NO inventes datos que no estén en la info del lead.\n"
        f"{vp}{ctx}\n\n{_lang_directive(lang)}"
    )


def generate_message(lead: dict[str, Any], value_prop: str = "", context: str = "",
                     client: Any | None = None, lang: str = "es") -> str:
    """Genera un borrador de mensaje para un lead. Devuelve texto plano (editable)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    info = {k: lead.get(k, "") for k in _LEAD_FIELDS if lead.get(k)}
    insights = {k: lead[k] for k in _INSIGHT_KEYS if lead.get(k)}
    user = ("Datos del lead:\n" + json.dumps(info, ensure_ascii=False)
            + ("\n\nInsights del enrichment (usalos como munición):\n"
               + json.dumps(insights, ensure_ascii=False) if insights else "")
            + "\n\nEscribí el borrador del primer mensaje.")
    resp = client.messages.create(
        model=MODEL, max_tokens=600, system=_system(value_prop, context, lang),
        messages=[{"role": "user", "content": user}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "").strip()

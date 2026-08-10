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


def _exa_ammo(lead: dict[str, Any]) -> dict[str, str]:
    """Facts de Exa (company + persona) aplanados a {clave: valor} para el prompt.

    Solo valores (sin URLs de fuente, que no van en el mensaje). Complementa a Clay:
    Clay = posteos de LinkedIn (activity); Exa = presencia web más amplia.
    """
    exa = lead.get("exa") or {}
    comp = exa.get("company") or {}
    pers = exa.get("person") or {}
    ammo: dict[str, str] = {}
    f = comp.get("funding")
    if f:
        parts = [str(x) for x in (f.get("stage"), f.get("amount_usd"), f.get("date")) if x]
        if parts:
            ammo["company_funding"] = " · ".join(parts)
    for src_key, out_key in (("hiring", "company_hiring"), ("geo", "company_geo")):
        node = comp.get(src_key)
        if node and node.get("v"):
            ammo[out_key] = node["v"]
    for k in ("public_activity", "content", "career_moves", "press"):
        node = pers.get(k)
        if node and node.get("v"):
            ammo[f"person_{k}"] = node["v"]
    return ammo


def _lang_directive(lang: str) -> str:
    return ("Escribí el mensaje en español rioplatense (vos)." if lang == "es"
            else "Write the message in English (address them as 'you').")


def _system(value_prop: str, context: str = "", lang: str = "es",
            hypothesis: str = "") -> str:
    """Arma el system en tres bloques etiquetados: Making Sense, esta campaña, y las reglas.

    El mensaje se groundea en QUIÉN es Making Sense (context) + la TESIS de la campaña
    (hipótesis + propuesta de valor). Sin esos bloques, el mensaje sale genérico.
    """
    rules = (
        "Sos parte del equipo de Making Sense y escribís el PRIMER mensaje de LinkedIn a un "
        "prospecto que YA aceptó la conexión. Objetivo: abrir conversación, NO vender ni "
        "pitchear.\n\n"
        "Reglas:\n"
        "- Breve: 2 a 4 oraciones (~400-600 caracteres). Cálido, humano y directo.\n"
        "- Personalizalo con el 'hook' y la situación del prospecto (su rol, su empresa, su "
        "momento de negocio), ANCLADO en la hipótesis de la campaña. Que no parezca masivo.\n"
        "- Conectá su contexto con lo que hace Making Sense de forma sutil (media frase), sin "
        "pitch agresivo ni lista de servicios.\n"
        "- Cerrá con una pregunta abierta o un CTA suave (ej. proponer una charla corta).\n"
        "- Primera persona plural (nosotros/Making Sense); tratá al prospecto de 'vos/tú'.\n"
        "- Sin emoji. Sin asunto ni firma. NO inventes datos que no estén en la info provista.\n"
        "- Respetá el tono y las reglas del contexto de Making Sense (abajo)."
    )
    ms = (f"\n\n## Making Sense (quiénes somos, propuesta de valor, tono — ground truth)\n{context}"
          if context and context.strip() else "")
    camp_parts = []
    if hypothesis and hypothesis.strip():
        camp_parts.append("Hipótesis / a quién apuntamos y por qué:\n" + hypothesis.strip())
    if value_prop and value_prop.strip():
        camp_parts.append("Propuesta de valor de esta campaña:\n" + value_prop.strip())
    camp = ("\n\n## Esta campaña (la tesis del outreach)\n" + "\n\n".join(camp_parts)
            if camp_parts else "")
    return f"{rules}{ms}{camp}\n\n{_lang_directive(lang)}"


def generate_message(lead: dict[str, Any], value_prop: str = "", context: str = "",
                     client: Any | None = None, lang: str = "es",
                     hypothesis: str = "") -> str:
    """Genera un borrador de mensaje para un lead. Devuelve texto plano (editable).

    context = KB de ventas de Making Sense · value_prop + hypothesis = definición de la campaña.
    """
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    info = {k: lead.get(k, "") for k in _LEAD_FIELDS if lead.get(k)}
    insights = {k: lead[k] for k in _INSIGHT_KEYS if lead.get(k)}
    # Actividad de LinkedIn (Fase 2): si está, es el mejor hook — algo reciente y real.
    act = lead.get("activity") or {}
    act_summary = act.get("summary") if isinstance(act, dict) else None
    exa_ammo = _exa_ammo(lead)
    user = ("Datos del lead:\n" + json.dumps(info, ensure_ascii=False)
            + ("\n\nInsights del enrichment (usalos como munición):\n"
               + json.dumps(insights, ensure_ascii=False) if insights else "")
            + ("\n\nActividad reciente en LinkedIn (usala como HOOK principal si es "
               "relevante y específica):\n" + act_summary if act_summary else "")
            + ("\n\nDatos web verificados de Exa (company + persona, con fuente). Usalos como "
               "munición grounded; NO repitas lo que ya aparece en la actividad de LinkedIn:\n"
               + json.dumps(exa_ammo, ensure_ascii=False) if exa_ammo else "")
            + "\n\nEscribí el borrador del primer mensaje.")
    resp = client.messages.create(
        model=MODEL, max_tokens=600,
        system=_system(value_prop, context, lang, hypothesis),
        messages=[{"role": "user", "content": user}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "").strip()

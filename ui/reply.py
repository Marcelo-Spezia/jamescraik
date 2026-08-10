"""Generación de la RESPUESTA a un lead que ya contestó (recrea el proceso de Nicolás).

Distinto del primer mensaje: acá hay un hilo (nuestro 1er mensaje + la respuesta del lead)
y se genera un follow-up en la VOZ de un remitente (SDR) concreto. Incluye un gate de fit:
si al leer el contexto el lead no es buen fit / no vale una reunión, NO genera mensaje y
devuelve el motivo.

Contexto del lead: sale del enrichment que ya tenemos (insights + Clay + Exa), no de pegar
el perfil. Salida estructurada: {fit, reason, reply}.
"""

from __future__ import annotations

import json
import os
from typing import Any

from message import _exa_ammo  # reutiliza el aplanado de facts de Exa

MODEL = os.getenv("ICP_JUDGE_MODEL", "claude-opus-4-8")

_LEAD_FIELDS = ["name", "title", "company", "industry", "location", "tier", "reason"]
_INSIGHT_KEYS = ["hook", "value_prop_match", "business_momentum", "role_focus",
                 "tech_maturity", "funding", "growth", "maturity"]

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fit": {"type": "boolean"},
        "reason": {"type": "string"},
        "reply": {"type": ["string", "null"]},
    },
    "required": ["fit", "reason", "reply"],
    "additionalProperties": False,
}


def _lang_directive(lang: str) -> str:
    return ("Escribí la respuesta en español rioplatense (vos)." if lang == "es"
            else "Write the reply in English (address them as 'you').")


def lead_context(lead: dict[str, Any]) -> dict[str, Any]:
    """Contexto del lead para la respuesta, armado desde el enrichment ya existente."""
    ctx: dict[str, Any] = {k: lead.get(k) for k in _LEAD_FIELDS if lead.get(k)}
    insights = {k: lead[k] for k in _INSIGHT_KEYS if lead.get(k)}
    if insights:
        ctx["insights"] = insights
    act = lead.get("activity") or {}
    if isinstance(act, dict) and act.get("summary"):
        ctx["linkedin_activity"] = act["summary"]
    exa = _exa_ammo(lead)
    if exa:
        ctx["web_facts"] = exa
    return ctx


def _system(sender: dict[str, Any], context: str, lang: str) -> str:
    examples = sender.get("examples") or []
    ex = ("\n\nEjemplos de cómo escribe (imitá el estilo, no copies literal):\n"
          + "\n---\n".join(examples)) if examples else ""
    voice = (f"\n\nVoz de {sender.get('name', '')} ({sender.get('role', '')}):\n"
             f"{sender.get('voice', '')}"
             + (f"\nBase de credibilidad: {sender.get('credibility', '')}"
                if sender.get("credibility") else "") + ex)
    ms = (f"\n\n## Contexto de Making Sense (ground truth: tono, manejo de respuestas, "
          f"criterios de descalificación)\n{context}" if context and context.strip() else "")
    return (
        f"Sos {sender.get('name', 'el remitente')}, {sender.get('role', '')} de Making Sense. "
        "Un lead que YA aceptó la conexión respondió a nuestro primer mensaje; escribís vos el "
        "follow-up. Objetivo: mover hacia una charla corta, sin vender ni pitchear.\n\n"
        "PRIMERO evaluá el fit: leé el contexto del lead y su respuesta. Si NO es un buen fit "
        "o no valdría la pena una reunión (según los criterios de descalificación del contexto), "
        "devolvé fit=false, reply=null y en reason explicá por qué en una frase. NO generes "
        "mensaje en ese caso.\n\n"
        "Si es fit: fit=true, reason breve (por qué sí), y reply = UNA respuesta natural, humana "
        "y consistente con la voz del remitente. Corta (2-4 oraciones), directa, sin emoji, sin "
        "firma. Respondé a lo que dijo el lead; no inventes datos que no estén en el contexto."
        f"{voice}{ms}\n\n{_lang_directive(lang)}"
    )


def generate_reply(lead: dict[str, Any], sender: dict[str, Any], lead_reply: str,
                   context: str = "", first_message: str = "", lang: str = "es",
                   client: Any | None = None) -> dict[str, Any]:
    """Devuelve {fit: bool, reason: str, reply: str|None}. reply es None si no es fit."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    convo = []
    if first_message and first_message.strip():
        convo.append("Nuestro primer mensaje:\n" + first_message.strip())
    convo.append("Respuesta del lead:\n" + (lead_reply or "").strip())
    user = ("Contexto del lead (del enrichment):\n"
            + json.dumps(lead_context(lead), ensure_ascii=False)
            + "\n\nConversación hasta ahora:\n" + "\n\n".join(convo)
            + "\n\nEvaluá el fit y, si corresponde, generá UNA respuesta.")
    resp = client.messages.create(
        model=MODEL, max_tokens=800, system=_system(sender, context, lang),
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = json.loads(text)
    return {"fit": bool(data.get("fit")), "reason": data.get("reason", ""),
            "reply": data.get("reply")}

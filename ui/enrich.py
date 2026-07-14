"""Enrichment cualitativo de los leads calificados (A/B): señales de NEGOCIO para el mensaje.

Making Sense NO vende por tech stack (ver memoria). Este enrichment NO muestra el stack:
enriquece por **estado del negocio**. Las señales son **configurables por campaña** — cada
campaña pide lo que le sirve (funding, legacy, regulatorio, expansión…), no un set fijo.

Modelo:
- Una SEÑAL = {key, label, question, source}. `source` = de dónde sale la respuesta:
  "apollo" (dato duro) o "llm" (inferencia/hipótesis) — para no esperar precisión donde no la hay.
- Catálogo de señales comunes (SIGNAL_CATALOG) + señales a medida (texto libre).
- NÚCLEO (CORE_SIGNALS): match de propuesta de valor + hook. Siempre presentes, no configurables.

Flujo:
  1. dedup por dominio → Apollo org-enrich por empresa única (1 crédito c/u; reusa el adapter
     canónico, que trae el org crudo en `.raw` con funding/revenue/crecimiento).
  2. LLM en lote (system cacheable) responde UNA cosa por señal elegida + el núcleo.

Degradación elegante: sin dominio o sin Apollo, el LLM sintetiza con lo que hay; los datos
duros que falten quedan honestos ("sin datos"), nunca inventados.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

MODEL = os.getenv("ICP_JUDGE_MODEL", "claude-opus-4-8")


# ---------------------------------------------------------------------------
# Catálogo de señales (configurable por campaña) + núcleo (siempre)
# ---------------------------------------------------------------------------
# source: "apollo" = dato duro de Apollo | "llm" = inferencia/hipótesis del modelo.
SIGNAL_CATALOG: list[dict[str, str]] = [
    {"key": "funding", "label": "Inversión / funding", "source": "apollo",
     "question": "¿Recibieron inversión? Etapa, monto y fecha si hay dato. Si no hay, decilo."},
    {"key": "growth", "label": "Crecimiento", "source": "apollo",
     "question": "Señales de crecimiento: headcount, contrataciones, tamaño, expansión."},
    {"key": "maturity", "label": "Madurez / legacy", "source": "llm",
     "question": "HIPÓTESIS de madurez tecnológica: ¿legacy, modernizando, greenfield? "
                 "Inferila del stack (evidencia), antigüedad, industria y tamaño."},
    {"key": "geo_expansion", "label": "Expansión geográfica", "source": "llm",
     "question": "¿Se están expandiendo a nuevos mercados o regiones?"},
    {"key": "platform", "label": "Stack / plataforma", "source": "apollo",
     "question": "Qué plataforma/stack usan, SOLO como evidencia de contexto (no como argumento)."},
    {"key": "regulatory", "label": "Presión regulatoria", "source": "llm",
     "question": "¿Qué presión regulatoria / compliance enfrentan por su rubro?"},
    {"key": "hiring_tech", "label": "Contrataciones en tech", "source": "llm",
     "question": "¿Hay indicios de que contratan en producto/tecnología?"},
    {"key": "role_focus", "label": "Foco del rol", "source": "llm",
     "question": "Qué le importa/preocupa a ese rol en esa empresa."},
]

CORE_SIGNALS: list[dict[str, str]] = [
    {"key": "value_prop_match", "label": "Match propuesta de valor", "source": "llm",
     "question": "Cómo lo de Making Sense resuelve una necesidad probable DADO el estado del "
                 "negocio (no la tecnología en sí)."},
    {"key": "hook", "label": "Hook / ángulo", "source": "llm",
     "question": "Un ÁNGULO de apertura para el mensaje (una idea, NO una línea redactada)."},
]

# Selección por defecto (si la campaña no define señales).
DEFAULT_SIGNAL_KEYS = ["funding", "growth", "maturity", "role_focus"]

_CATALOG_BY_KEY = {s["key"]: s for s in SIGNAL_CATALOG}
_CATALOG_BY_LABEL = {s["label"].lower(): s for s in SIGNAL_CATALOG}


def catalog_labels() -> list[str]:
    return [s["label"] for s in SIGNAL_CATALOG]


def default_signals() -> list[dict[str, str]]:
    return [dict(_CATALOG_BY_KEY[k]) for k in DEFAULT_SIGNAL_KEYS if k in _CATALOG_BY_KEY]


def _slugify(text: str) -> str:
    import unicodedata
    norm = unicodedata.normalize("NFKD", (text or "").strip().lower())
    norm = "".join(c for c in norm if not unicodedata.combining(c))  # saca tildes
    s = re.sub(r"[^a-z0-9]+", "_", norm).strip("_")
    return s or "senal"


def signal_from_label(label: str) -> dict[str, str] | None:
    """Una etiqueta del catálogo → la señal completa."""
    return dict(_CATALOG_BY_LABEL[label.lower()]) if label.lower() in _CATALOG_BY_LABEL else None


def parse_custom_signals(text: str) -> list[dict[str, str]]:
    """Texto libre → señales a medida. Cada línea: 'etiqueta' o 'etiqueta: pregunta'."""
    out: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip().lstrip("-*• ").strip()
        if not line:
            continue
        label, _, question = line.partition(":")
        label = label.strip()
        out.append({"key": _slugify(label), "label": label,
                    "question": (question.strip() or label), "source": "llm"})
    return out


def resolve_signals(raw: list[Any] | None) -> list[dict[str, str]]:
    """Normaliza una lista mixta (dicts del catálogo, dicts a medida o strings) →
    señales {key,label,question,source}, deduplicadas por key, sin el núcleo."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw or []:
        if isinstance(item, str):
            sig = signal_from_label(item) or {"key": _slugify(item), "label": item,
                                              "question": item, "source": "llm"}
        elif isinstance(item, dict):
            label = str(item.get("label") or item.get("key") or "").strip()
            if not label:
                continue
            base = signal_from_label(label)
            sig = base or {
                "key": item.get("key") or _slugify(label), "label": label,
                "question": str(item.get("question") or label), "source": item.get("source", "llm"),
            }
        else:
            continue
        if sig["key"] in seen or sig["key"] in {c["key"] for c in CORE_SIGNALS}:
            continue
        seen.add(sig["key"])
        out.append(sig)
    return out


def active_signals(signals: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """Señales elegidas (o default) + el núcleo, en orden de salida."""
    chosen = resolve_signals(signals) if signals else default_signals()
    return chosen + [dict(c) for c in CORE_SIGNALS]


# ---------------------------------------------------------------------------
# Señales de negocio desde Apollo (deduplicado por dominio)
# ---------------------------------------------------------------------------
def _extract_signals(acc: Any) -> dict[str, Any]:
    """Del Account canónico enriquecido → datos duros de NEGOCIO (no de tecnología).
    El tech_stack se incluye solo como evidencia para inferir madurez/legacy."""
    raw = getattr(acc, "raw", None) or {}
    return {
        "employees": getattr(acc, "employee_count", None),
        "founded_year": getattr(acc, "founded_year", None),
        "revenue": raw.get("annual_revenue") or raw.get("organization_revenue"),
        "total_funding": raw.get("total_funding_printed") or raw.get("total_funding"),
        "latest_funding_stage": raw.get("latest_funding_stage"),
        "latest_funding_date": raw.get("latest_funding_round_date"),
        "industry": raw.get("industry"),
        "description": raw.get("short_description") or raw.get("seo_description"),
        # evidencia (no se muestra): pistas de madurez/legacy
        "tech_stack_evidence": getattr(acc, "tech_stack", None) or [],
    }


def _run_async(coro: Any) -> Any:
    """Corre una corutina desde código sync (Streamlit). Si ya hay un loop corriendo,
    la ejecuta en un hilo aparte."""
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


def company_signals(domains: list[str], source: Any | None = None) -> dict[str, dict]:
    """Enriquece cada dominio ÚNICO con Apollo → {domain: signals}. Deduplicado:
    varios leads de la misma empresa = 1 sola llamada (1 crédito). Falla parcial no corta."""
    uniq = sorted({(d or "").strip().lower() for d in domains if (d or "").strip()})
    if not uniq:
        return {}
    if source is None:
        if not os.getenv("APOLLO_API_KEY"):
            return {}  # sin Apollo: seguimos solo con el LLM
        from icp_engine.adapters.apollo import ApolloIngestionSource
        source = ApolloIngestionSource()

    async def _gather() -> dict[str, dict]:
        out: dict[str, dict] = {}
        for d in uniq:
            try:
                acc = await source.enrich_account_by_domain(d)
                out[d] = _extract_signals(acc) if acc else {}
            except Exception:  # noqa: BLE001 - un dominio que falla no corta el resto
                out[d] = {}
        return out

    return _run_async(_gather())


# ---------------------------------------------------------------------------
# Síntesis de insights (LLM, en lote + caching, schema dinámico según señales)
# ---------------------------------------------------------------------------
# Campos del lead que se le pasan al LLM (sin PII de contacto: email/linkedin no aportan).
_LEAD_FIELDS = ["name", "title", "company", "domain", "size", "industry", "location"]


def _schema(signals: list[dict[str, str]]) -> dict[str, Any]:
    keys = [s["key"] for s in signals]
    props: dict[str, Any] = {"index": {"type": "integer"}}
    for k in keys:
        props[k] = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": props,
                    "required": ["index", *keys],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    }


def _system(signals: list[dict[str, str]], value_prop: str, context: str = "") -> str:
    vp = f"\n\nPropuesta de valor de Making Sense:\n{value_prop}" if value_prop else ""
    ctx = (f"\n\nContexto de Making Sense (dónde gana, casos, aprendizajes):\n{context}"
           if context and context.strip() else "")
    lines = []
    for s in signals:
        tag = "dato duro de Apollo" if s.get("source") == "apollo" else "inferencia/hipótesis"
        lines.append(f"- {s['key']} ({tag}): {s['question']}")
    fields = "\n".join(lines)
    return (
        "Sos un analista de demand generation de Making Sense (desarrollo y modernización "
        "de software / servicios tech-enabled). Para cada lead ya calificado, generás "
        "munición CUALITATIVA para el primer mensaje.\n\n"
        "IMPORTANTE sobre cómo vende Making Sense: el tech stack del prospecto NO es un "
        "argumento de venta; no lo menciones como valor. Lo que importa es el ESTADO DEL "
        "NEGOCIO (crecimiento, inversión, madurez, legacy). Usá el stack solo como evidencia.\n\n"
        "Para cada lead devolvé EXACTAMENTE estos campos (uno por cada uno), breves y concretos. "
        "Si un campo es 'dato duro de Apollo' y no viene el dato en company_signals, decilo "
        "honestamente (ej. 'sin datos públicos'); NO inventes cifras. Los de 'inferencia' son "
        "hipótesis, marcalas como tales.\n\n"
        f"CAMPOS A DEVOLVER:\n{fields}\n\n"
        f"Devolvé exactamente un resultado por lead, con su mismo 'index'.{vp}{ctx}"
    )


# Techo de tokens de salida (Opus admite hasta 8192 por defecto).
_MAX_OUTPUT_TOKENS = 8000


def _budget(keys: list[str], batch: list) -> int:
    """Presupuesto de salida: ~180 tokens por señal por lead + overhead, con techo.
    Cada señal produce una o dos oraciones; subestimarlo trunca el JSON."""
    return min(_MAX_OUTPUT_TOKENS, 500 + 180 * len(keys) * len(batch))


def _call_batch(batch: list[dict[str, Any]], value_prop: str, context: str,
                client: Any, signals_map: dict[str, dict],
                signals: list[dict[str, str]]) -> list[dict[str, Any]]:
    """UNA llamada + parseo. Lanza json.JSONDecodeError si la salida vino truncada."""
    keys = [s["key"] for s in signals]
    items = []
    for i, ld in enumerate(batch):
        sig = signals_map.get((ld.get("domain") or "").strip().lower(), {})
        items.append({"index": i,
                      "lead": {k: ld.get(k, "") for k in _LEAD_FIELDS},
                      "company_signals": sig})
    user = ("Enriquecé TODOS estos leads con señales de negocio para el mensaje.\n\n"
            + json.dumps(items, ensure_ascii=False))
    resp = client.messages.create(
        model=MODEL,
        max_tokens=_budget(keys, batch),
        system=[{"type": "text", "text": _system(signals, value_prop, context),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": _schema(signals)}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    results = json.loads(text).get("results", [])  # truncado → JSONDecodeError
    by_index = {r.get("index"): r for r in results}
    out = []
    for i, ld in enumerate(batch):
        r = by_index.get(i) or (results[i] if i < len(results) else {})
        out.append({**ld, **{k: r.get(k, "") for k in keys}})
    return out


def enrich_batch(batch: list[dict[str, Any]], value_prop: str, context: str,
                 client: Any, signals_map: dict[str, dict],
                 signals: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Enriquece una tanda. Si la salida se trunca (JSON incompleto), parte la tanda en
    dos y reintenta — así una tanda grande no tumba todo el proceso. Un lead que aun
    solo sigue fallando queda con los insights vacíos (no se pierde el lead)."""
    if not batch:
        return []
    try:
        return _call_batch(batch, value_prop, context, client, signals_map, signals)
    except json.JSONDecodeError:
        if len(batch) == 1:
            keys = [s["key"] for s in signals]
            return [{**batch[0], **{k: "" for k in keys}}]
        mid = len(batch) // 2
        return (enrich_batch(batch[:mid], value_prop, context, client, signals_map, signals)
                + enrich_batch(batch[mid:], value_prop, context, client, signals_map, signals))


DEFAULT_BATCH = int(os.getenv("ICP_ENRICH_BATCH", "5"))


def enrich_leads(leads: list[dict[str, Any]], value_prop: str = "", context: str = "",
                 client: Any | None = None, source: Any | None = None,
                 signals: list[dict[str, str]] | None = None,
                 batch_size: int = DEFAULT_BATCH) -> list[dict[str, Any]]:
    """Enriquece una lista de leads (idealmente A/B) con las señales elegidas + el núcleo.

    OJO: cada empresa única consume 1 crédito de Apollo; cada tanda, 1 llamada a Claude.
    """
    if not leads:
        return []
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    active = active_signals(signals)
    signals_map = company_signals([ld.get("domain", "") for ld in leads], source)
    out: list[dict[str, Any]] = []
    for i in range(0, len(leads), max(batch_size, 1)):
        out += enrich_batch(leads[i:i + batch_size], value_prop, context,
                            client, signals_map, active)
    return out

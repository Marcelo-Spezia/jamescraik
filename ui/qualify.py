"""Núcleo del approach redefinido: calificar una lista (CSV de Sales Nav) contra
una RÚBRICA en lenguaje natural, con el LLM. Sin criterios/pesos, sin Apollo.

- parse_sales_nav_csv: parsea el export (CSV real, con campos entre comillas) → leads.
- qualify_lead / qualify_leads: el LLM asigna tier (A/B/C/D) + el por qué contra la rúbrica.

El enrichment (Apollo en A/B, actividad LinkedIn) se suma después, solo sobre los calificados.
"""

from __future__ import annotations

import ast
import csv
import io
import json
import os
import re
from typing import Any

MODEL = os.getenv("ICP_JUDGE_MODEL", "claude-opus-4-8")


def _domain(url: str) -> str:
    if not url:
        return ""
    d = url.strip().lower()
    for p in ("https://", "http://", "www."):
        if d.startswith(p):
            d = d[len(p):]
    return d.rstrip("/").split("/")[0]


def _size(row: dict[str, Any]) -> str:
    a, b = row.get("employee_count_start", ""), row.get("employee_count_end", "")
    def _i(x):
        try:
            return str(int(float(x)))
        except (ValueError, TypeError):
            return ""
    a, b = _i(a), _i(b)
    if a and b:
        return f"{a}-{b}"
    return a or b or ""


def _industry(s: str) -> str:
    if not s:
        return ""
    try:
        v = ast.literal_eval(s)
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
    except (ValueError, SyntaxError):
        pass
    return str(s)


# --- Detección de campos: mapea las columnas de CUALQUIER CSV a nuestro modelo ---
# Campos destino del modelo de lead (first_name/last_name solo alimentan 'name').
TARGET_FIELDS = ["name", "first_name", "last_name", "title", "company", "domain",
                 "size", "industry", "location", "email", "linkedin"]
TARGET_LABELS = {
    "name": "Nombre", "first_name": "Nombre (pila)", "last_name": "Apellido",
    "title": "Título / Cargo", "company": "Empresa", "domain": "Dominio / Web",
    "size": "Tamaño / Empleados", "industry": "Industria", "location": "Ubicación",
    "email": "Email", "linkedin": "LinkedIn",
}

# Sinónimos EN/ES de headers para cada campo (auto-detección).
_SYNONYMS: dict[str, list[str]] = {
    "name": ["name", "full name", "contact name", "lead name", "person name",
             "nombre", "nombre completo", "persona", "contacto"],
    "first_name": ["first", "first name", "firstname", "given name", "primer nombre",
                   "nombre de pila"],
    "last_name": ["last", "last name", "lastname", "surname", "family name", "apellido",
                  "apellidos"],
    "title": ["title", "job title", "position", "role", "headline", "current title",
              "current position", "titulo", "puesto", "cargo", "rol"],
    "company": ["company", "company name", "organization", "organisation", "account",
                "account name", "employer", "current company", "company for emails",
                "empresa", "compania", "organizacion", "cuenta", "empleador"],
    "domain": ["domain", "website", "company website", "web", "url", "site", "website url",
               "company domain", "company url", "dominio", "sitio web", "pagina web"],
    "size": ["size", "company size", "headcount", "employees", "employee count",
             "num employees", "number of employees", "company headcount", "staff count",
             "employee count start", "tamano", "tamano de empresa", "empleados",
             "dotacion", "cantidad de empleados"],
    "industry": ["industry", "industries", "sector", "vertical", "company industry",
                 "industria", "rubro", "sector industrial"],
    "location": ["location", "company location", "city", "country", "region", "geo",
                 "person location", "contact location", "ubicacion", "localidad",
                 "ciudad", "pais", "region", "zona"],
    "email": ["email", "email address", "e mail", "work email", "correo",
              "correo electronico", "mail"],
    "linkedin": ["linkedin", "linkedin url", "profile url", "profile link",
                 "linkedin profile", "li profile", "person linkedin url",
                 "perfil linkedin", "perfil de linkedin", "url de linkedin"],
}


def _norm_header(h: str) -> str:
    """Normaliza un header para comparar: minúsculas, sin puntuación ni acentos."""
    import unicodedata
    s = unicodedata.normalize("NFKD", (h or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


_SYNONYMS_NORM = {t: {_norm_header(s) for s in syns} for t, syns in _SYNONYMS.items()}


def read_csv(text: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Lee un CSV → (headers, filas). Agnóstico al origen."""
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader]
    return headers, rows


# Tokens distintivos para un 2º paso (solo campos clave): matchea headers compuestos
# como "Company Name for Emails" que no calzan exacto pero contienen la palabra clave.
_FALLBACK_TOKENS: dict[str, list[str]] = {
    "company": ["company", "organization", "organisation", "account", "empresa",
                "compania", "employer", "empleador"],
    "domain": ["website", "domain", "url", "web"],
}


def detect_mapping(headers: list[str]) -> dict[str, str]:
    """Autodetecta qué header corresponde a cada campo destino.
    Paso 1: match exacto por sinónimos. Paso 2 (empresa/dominio): match por token
    distintivo dentro de headers compuestos. Devuelve {campo: header} ('' si no
    se reconoció). No repite un header."""
    norm = {h: _norm_header(h) for h in headers}
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for t in TARGET_FIELDS:
        match = ""
        for h in headers:
            if h not in used and norm[h] in _SYNONYMS_NORM[t]:
                match = h
                used.add(h)
                break
        mapping[t] = match
    for t, tokens in _FALLBACK_TOKENS.items():
        if mapping[t]:
            continue
        for h in headers:
            if h not in used and any(tok in norm[h].split() for tok in tokens):
                mapping[t] = h
                used.add(h)
                break
    return mapping


def leads_from_rows(rows: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    """Construye los leads normalizados a partir de las filas + el mapeo de columnas."""
    leads: list[dict[str, Any]] = []
    for r in rows:
        def g(t: str) -> str:
            h = mapping.get(t)
            return str(r.get(h, "") or "").strip() if h else ""
        name = g("name") or f"{g('first_name')} {g('last_name')}".strip()
        # tamaño: si el CSV trae el par start/end (tipo Sales Nav) se combina; si no,
        # se usa la columna única mapeada.
        if r.get("employee_count_start") or r.get("employee_count_end"):
            size = _size(r)
        else:
            size = g("size")
        leads.append({
            "name": name,
            "title": g("title"),
            "company": g("company"),
            "domain": _domain(g("domain")),
            "size": size,
            "industry": _industry(g("industry")),
            "location": g("location"),
            "email": g("email"),
            "linkedin": g("linkedin"),
        })
    return leads


def parse_sales_nav_csv(text: str) -> list[dict[str, Any]]:
    """Parsea CUALQUIER CSV → leads: lee, autodetecta las columnas y normaliza.
    (El nombre queda por compatibilidad; ya no asume el formato de Sales Nav.)"""
    headers, rows = read_csv(text)
    return leads_from_rows(rows, detect_mapping(headers))


_SCHEMA = {
    "type": "object",
    "properties": {
        "tier": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "reason": {"type": "string"},
    },
    "required": ["tier", "reason"],
    "additionalProperties": False,
}


def _lang_directive(lang: str) -> str:
    return ("\n\nEscribí el 'reason' en español." if lang == "es"
            else "\n\nWrite the 'reason' in English.")


def _system(rubric: str, value_prop: str, context: str = "", lang: str = "es") -> str:
    vp = (f"\n\nPropuesta de valor de Making Sense (para evaluar el fit):\n{value_prop}"
          if value_prop else "")
    ctx = (f"\n\nContexto de Making Sense (para juzgar el match):\n{context}"
           if context and context.strip() else "")
    return (
        "Sos un analista de calificación de leads B2B. Calificás cada contacto contra "
        "la RÚBRICA del cliente ideal, en tiers A (ideal), B (bueno), C (marginal), D (no fit). "
        "Basate en el rol del contacto y en lo que sabés de la empresa (nombre, dominio, "
        "industria, tamaño). Si la empresa o el rol claramente no encajan (rol equivocado, "
        "empresa de otro rubro, gobierno/educación, demasiado chica, perfil personal/ruido), "
        "es D. Devolvés tier + un 'por qué' breve y concreto.\n\n"
        f"RÚBRICA:\n{rubric}{vp}{ctx}{_lang_directive(lang)}"
    )


def qualify_lead(lead: dict[str, Any], rubric: str, value_prop: str, client: Any,
                 context: str = "", lang: str = "es") -> dict[str, Any]:
    resp = client.messages.create(
        model=MODEL, max_tokens=400, system=_system(rubric, value_prop, context, lang),
        messages=[{"role": "user", "content": json.dumps(lead, ensure_ascii=False)}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = json.loads(text)
    return {**lead, "tier": data.get("tier", "D"), "reason": data.get("reason", "")}


DEFAULT_BATCH = int(os.getenv("ICP_QUALIFY_BATCH", "10"))

# Salida en lote: un resultado por lead (mapeado por index).
_BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "tier": {"type": "string", "enum": ["A", "B", "C", "D"]},
                    "reason": {"type": "string"},
                },
                "required": ["index", "tier", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

_LEAD_FIELDS = ["name", "title", "company", "domain", "size", "industry", "location"]


def qualify_batch(batch: list[dict[str, Any]], rubric: str, value_prop: str, client: Any,
                  context: str = "", lang: str = "es") -> list[dict[str, Any]]:
    """Califica una tanda de leads en UNA sola llamada. El system (instrucciones +
    rúbrica + contexto) va como bloque cacheable → se cuenta 1 vez por tanda y se
    lee cacheado en las siguientes (prompt caching)."""
    items = [{"index": i, **{k: ld.get(k, "") for k in _LEAD_FIELDS}}
             for i, ld in enumerate(batch)]
    user = ("Calificá TODOS estos leads. Devolvé exactamente un resultado por cada uno, "
            "con su mismo 'index'.\n\n" + json.dumps(items, ensure_ascii=False))
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max(600, 120 * len(batch)),
        system=[{"type": "text", "text": _system(rubric, value_prop, context, lang),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": _BATCH_SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    results = json.loads(text).get("results", [])
    by_index = {r.get("index"): r for r in results}
    out = []
    for i, ld in enumerate(batch):
        r = by_index.get(i) or (results[i] if i < len(results) else {})
        out.append({**ld, "tier": r.get("tier", "D"), "reason": r.get("reason", "")})
    return out


def qualify_leads(leads: list[dict[str, Any]], rubric: str, value_prop: str = "",
                  client: Any | None = None, context: str = "",
                  batch_size: int = DEFAULT_BATCH, lang: str = "es") -> list[dict[str, Any]]:
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    out: list[dict[str, Any]] = []
    for i in range(0, len(leads), max(batch_size, 1)):
        out += qualify_batch(leads[i:i + batch_size], rubric, value_prop, client, context, lang)
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    out.sort(key=lambda x: order.get(x["tier"], 9))
    return out


_EXPORT_FIELDS = ["tier", "name", "title", "company", "domain", "size",
                  "industry", "location", "email", "linkedin", "reason"]


def leads_to_csv(leads: list[dict[str, Any]]) -> str:
    """Serializa los leads calificados a CSV. Las columnas de enrichment son dinámicas:
    se agregan las señales presentes en los leads (varían por campaña)."""
    extra: list[str] = []
    for ld in leads:
        for k in ld:
            if k not in _EXPORT_FIELDS and k not in extra:
                extra.append(k)
    fields = _EXPORT_FIELDS + extra
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for ld in leads:
        w.writerow({k: ld.get(k, "") for k in fields})
    return out.getvalue()

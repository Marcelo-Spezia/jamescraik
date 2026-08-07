"""Reglas de normalización para comparar los dos proveedores en los mismos 4 campos.

Todo acá es PURO (sin red, sin reloj): las funciones que necesitan "hoy" lo reciben
como parámetro. Objetivo: dejar los valores de Apollo y Exa en la misma forma para que
`metrics.py` los compare sin ambigüedad.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# employee_count
# ---------------------------------------------------------------------------
# Bandas de headcount (una empresa "coincide" si cae en la misma banda).
_BANDS: list[tuple[int, int, str]] = [
    (1, 10, "1-10"),
    (11, 50, "11-50"),
    (51, 200, "51-200"),
    (201, 500, "201-500"),
    (501, 1000, "501-1000"),
    (1001, 5000, "1001-5000"),
    (5001, 10**12, "5000+"),
]


def norm_employee_count(value: Any) -> int | None:
    """A int no-negativo, o None. Acepta int, float, o string con separadores."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = int(value)
        return n if n > 0 else None
    s = re.sub(r"[,\s]", "", str(value))
    m = re.search(r"\d+", s)
    if not m:
        return None
    n = int(m.group(0))
    return n if n > 0 else None


def employee_band(n: int | None) -> str | None:
    if n is None:
        return None
    for lo, hi, label in _BANDS:
        if lo <= n <= hi:
            return label
    return None


def within_pct(a: int, b: int, pct: float) -> bool:
    """True si a y b están dentro de ±pct uno del otro (referencia = el mayor)."""
    if a is None or b is None:
        return False
    hi = max(abs(a), abs(b))
    if hi == 0:
        return True
    return abs(a - b) / hi <= pct


# ---------------------------------------------------------------------------
# hq_country → ISO-3166 alpha-2
# ---------------------------------------------------------------------------
_COUNTRY_MAP: dict[str, str] = {
    # variantes de nombre / alpha-3 → alpha-2. Foco en el ICP (US + LATAM + EU comunes).
    "us": "US", "usa": "US", "u.s.": "US", "u.s.a.": "US", "united states": "US",
    "united states of america": "US", "america": "US",
    "uk": "GB", "u.k.": "GB", "gb": "GB", "gbr": "GB", "united kingdom": "GB",
    "great britain": "GB", "britain": "GB", "england": "GB",
    "ca": "CA", "can": "CA", "canada": "CA",
    "mx": "MX", "mex": "MX", "mexico": "MX", "méxico": "MX",
    "ar": "AR", "arg": "AR", "argentina": "AR",
    "br": "BR", "bra": "BR", "brazil": "BR", "brasil": "BR",
    "cl": "CL", "chl": "CL", "chile": "CL",
    "co": "CO", "col": "CO", "colombia": "CO",
    "uy": "UY", "ury": "UY", "uruguay": "UY",
    "pe": "PE", "per": "PE", "peru": "PE", "perú": "PE",
    "es": "ES", "esp": "ES", "spain": "ES", "españa": "ES",
    "de": "DE", "deu": "DE", "germany": "DE", "deutschland": "DE",
    "fr": "FR", "fra": "FR", "france": "FR",
    "ie": "IE", "irl": "IE", "ireland": "IE",
    "nl": "NL", "nld": "NL", "netherlands": "NL",
    "pt": "PT", "prt": "PT", "portugal": "PT",
    "in": "IN", "ind": "IN", "india": "IN",
    "au": "AU", "aus": "AU", "australia": "AU",
}


def norm_country(value: Any) -> str | None:
    """A ISO alpha-2 (mayúsculas). Usa el mapa de variantes; si no, alpha-2 pasa derecho."""
    if not value:
        return None
    key = re.sub(r"\.", "", str(value).strip().lower())  # "u.s." → "us"
    key = re.sub(r"\s+", " ", key).strip()
    if key in _COUNTRY_MAP:
        return _COUNTRY_MAP[key]
    # ya viene como alpha-2 válido
    up = str(value).strip().upper()
    if re.fullmatch(r"[A-Z]{2}", up):
        return up
    return None


# ---------------------------------------------------------------------------
# last_funding.stage
# ---------------------------------------------------------------------------
_EARLY = {"preseed", "seed", "angel", "preseedround"}


def norm_stage(value: Any) -> str | None:
    """lowercase, saca 'series ', agrupa pre-seed/seed/angel como 'early'. Match exacto luego."""
    if not value:
        return None
    s = str(value).strip().lower()
    s = re.sub(r"^series\s+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    compact = re.sub(r"[^a-z0-9]", "", s)
    if compact in _EARLY:
        return "early"
    return s or None


# ---------------------------------------------------------------------------
# last_funding.date → ISO YYYY-MM-DD + precisión
# ---------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def norm_date(value: Any) -> tuple[str | None, str | None]:
    """Devuelve (iso YYYY-MM-DD, precision 'day'|'month'|'year') o (None, None).

    Si solo hay mes o año, normaliza al primer día del período y marca la precisión.
    """
    if not value:
        return None, None
    s = str(value).strip()
    # ISO date o datetime (toma la parte de fecha) → día
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "day"
    # YYYY-MM → mes
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01", "month"
    # "Month YYYY" → mes
    m = re.match(r"^([A-Za-z]+)\s+(\d{4})$", s)
    if m and m.group(1).lower() in _MONTHS:
        return f"{m.group(2)}-{_MONTHS[m.group(1).lower()]:02d}-01", "month"
    # YYYY → año
    m = re.match(r"^(\d{4})$", s)
    if m:
        return f"{m.group(1)}-01-01", "year"
    return None, None


def norm_funding(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normaliza {stage, amount_usd, date} → {stage, amount_usd, date, date_precision} o None."""
    if not raw:
        return None
    stage = norm_stage(raw.get("stage"))
    iso, precision = norm_date(raw.get("date"))
    amount = raw.get("amount_usd")
    if isinstance(amount, bool):
        amount = None
    if isinstance(amount, str):
        digits = re.sub(r"[,\s$]", "", amount)
        amount = int(float(digits)) if re.fullmatch(r"\d+(\.\d+)?", digits) else None
    if stage is None and iso is None and amount is None:
        return None
    return {"stage": stage, "amount_usd": amount, "date": iso, "date_precision": precision}


def days_since(iso_date: str, today: date) -> int:
    """Días desde iso_date (YYYY-MM-DD) hasta `today` (inyectado, testeable)."""
    y, m, d = (int(x) for x in iso_date.split("-"))
    return (today - date(y, m, d)).days

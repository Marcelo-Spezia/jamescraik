"""Tests de i18n: cobertura ES/EN, formato, directiva de idioma para la IA."""

from __future__ import annotations

import i18n


def test_every_key_has_both_languages():
    faltan = [k for k, v in i18n.T.items() if not v.get("es") or not v.get("en")]
    assert faltan == [], f"claves sin traducción completa: {faltan}"


def test_t_switches_language_and_formats():
    assert i18n.t("nav_qualify", "es") == "🎯 Calificar"
    assert i18n.t("nav_qualify", "en") == "🎯 Qualify"
    # con placeholders
    assert "5" in i18n.t("leads_read", "en", n=5)
    assert i18n.t("qualify_cost", "es", n=3).count("3") == 1


def test_t_fallback_to_spanish_then_key():
    assert i18n.t("nav_qualify", "xx") == "🎯 Calificar"   # idioma desconocido → es
    assert i18n.t("clave_inexistente", "en") == "clave_inexistente"


def test_ai_directive_language():
    assert "español" in i18n.ai_directive("es")
    assert "English" in i18n.ai_directive("en")


def test_signal_and_field_labels_localized():
    assert i18n.t("signal_funding", "en") == "Funding / investment"
    assert i18n.t("field_company", "en") == "Company"
    assert i18n.t("field_company", "es") == "Empresa"

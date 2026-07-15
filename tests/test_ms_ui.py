"""Tests del design system (ui/ms_ui.py): inyección segura + lectura de assets."""

from __future__ import annotations

from pathlib import Path

import ms_ui


def test_css_has_no_premature_style_close():
    """Un '</style>' en el CSS cerraría el bloque antes de tiempo y rompería la
    pantalla (todo el CSS se vería como texto). No debe haber ninguno."""
    css = ms_ui._CSS.read_text(encoding="utf-8")
    assert "</style>" not in css.lower()


def test_assets_exist():
    assert ms_ui._CSS.exists()
    assert (ms_ui._ICONS / "ArtificialIntelligence.svg").exists()
    assert (ms_ui._LOGO / "MakingSense-Logotype.svg").exists()


def test_icon_svg_forces_width():
    svg = ms_ui.icon_svg("ArtificialIntelligence", 48)
    assert "width:48px" in svg and "height:auto" in svg


def test_static_dir_is_next_to_entrypoint():
    # Streamlit sirve static/ relativo al script de entrada (ui/), no a la raíz.
    assert ms_ui._ICONS == Path(ms_ui.__file__).parent / "static" / "icons"

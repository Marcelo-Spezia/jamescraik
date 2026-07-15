"""
ms_ui.py — Helpers de UI para aplicar el Making Sense Design System en Streamlit.
Copiar a tu proyecto (p.ej. ui/ms_ui.py) y llamar apply_theme() una vez, al
inicio de la app, justo después de st.set_page_config().

Requisitos:
  - Carpeta ./static/ con los assets (ver README §4):
        static/fonts/*.ttf        (Red Hat Display)
        static/icons/*.svg        (set de 104 iconos)
        static/logo/*.svg
  - .streamlit/config.toml con enableStaticServing = true  (ver config.toml.example)
"""
from pathlib import Path

import streamlit as st

# static/ vive junto a este archivo (ui/static): Streamlit lo sirve en app/static/…
# (relativo al script de entrada) y acá lo leemos de disco para inlinear SVGs.
_HERE = Path(__file__).parent
_CSS = _HERE / "streamlit_styles.css"
_ICONS = _HERE / "static" / "icons"
_LOGO = _HERE / "static" / "logo"


def apply_theme() -> None:
    """Inyecta la hoja de estilos de la marca. Llamar una sola vez por página."""
    css = _CSS.read_text(encoding="utf-8")
    # Defensa: un '</style>' dentro del CSS (p.ej. en un comentario) cerraría el
    # bloque antes de tiempo y volcaría el resto como texto en pantalla.
    css = css.replace("</style>", "").replace("</STYLE>", "")
    st.html(f"<style>{css}</style>")


def logo(variant: str = "dark", width: int = 180) -> None:
    """Renderiza el logotipo. variant: 'dark' | 'white' | 'grey'."""
    name = {
        "dark":  "MakingSense-Logotype.svg",
        "white": "MakingSense-Logotype-White.svg",
        "grey":  "MakingSense-Logotype-Grey.svg",
    }[variant]
    svg = (_LOGO / name).read_text(encoding="utf-8")
    st.markdown(
        f'<div style="width:{width}px">{svg}</div>', unsafe_allow_html=True
    )


def icon_svg(name: str, size: int = 48) -> str:
    """Devuelve el markup <svg> de un icono de marca (gradiente intacto).
    `name` sin extensión, p.ej. 'ArtificialIntelligence'. Escalá SIEMPRE
    proporcional: fijá solo el ancho."""
    raw = (_ICONS / f"{name}.svg").read_text(encoding="utf-8")
    # forzamos ancho y dejamos alto automático para no romper la proporción
    return raw.replace(
        "<svg ", f'<svg style="width:{size}px;height:auto" ', 1
    )


def card(title: str, body: str = "", icon: str | None = None,
         tags: list[str] | None = None) -> None:
    """Card de servicio de la marca (blanca, radius 16, shadow, hover lift)."""
    parts = ['<div class="ms-card">']
    if icon:
        parts.append(icon_svg(icon, 48))
    parts.append(f"<h4>{title}</h4>")
    if body:
        parts.append(f"<p>{body}</p>")
    if tags:
        chips = "".join(f'<span class="ms-tag">{t}</span>' for t in tags)
        parts.append(f'<div style="display:flex;flex-wrap:wrap;gap:6px">{chips}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    """Etiqueta pequeña en mayúsculas verde sobre un título (patrón de marca)."""
    st.markdown(f'<div class="ms-eyebrow">{text}</div>', unsafe_allow_html=True)


# --- Botones -----------------------------------------------------------------
# No hace falta un wrapper: usá el botón nativo de Streamlit y el CSS ya lo
# convierte al estilo de marca.
#   st.button("Empezar", type="primary")   -> botón GRADIENTE (texto #102532)
#   st.button("Cancelar")                   -> botón secundario (ghost)
# Regla: el texto del botón va en MAYÚSCULAS y sin iconos/flechas.

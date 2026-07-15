"""Making Sense Design System para Streamlit.

Reglas de marca aplicadas acá (una sola fuente de verdad de estilos):
- Texto navy #102532 (nunca negro). Fondos blancos; gris-50 #F9F9F9 como zona.
- Gradiente verde→teal (#0ECC7E → #00C6D1) SOLO como acento: CTA primario, barra de
  progreso, eyebrows y números de stats. Nunca como fondo full-bleed.
- Botones pill; primario con relleno gradiente + texto navy ExtraBold; secundario ghost.
- Tipografía Red Hat Display. Sombras neutras (grises), nunca de color.

Uso: llamar inject_ms_theme() UNA vez, después de st.set_page_config y antes de los
widgets (no dentro de sub-páginas ni loops). Helpers: ms_eyebrow, ms_gradient_number, ms_card.
"""

from __future__ import annotations

import streamlit as st

NAVY = "#102532"
TEAL = "#00C6D1"
GREEN = "#0ECC7E"
GRAY_50 = "#F9F9F9"
GRAY_BORDER = "#E6E8EA"
GRADIENT = f"linear-gradient(90deg,{GREEN},{TEAL})"

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@400;500;700;800;900&display=swap');

html, body, .stApp, [class*="css"], button, input, textarea, select,
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] {{
  font-family: 'Red Hat Display', -apple-system, BlinkMacSystemFont, sans-serif !important;
}}
.stApp, body {{ color: {NAVY}; background: #FFFFFF; }}
h1, h2, h3, h4, h5, h6 {{ color: {NAVY} !important; font-weight: 800; letter-spacing: -0.01em; }}
a {{ color: {TEAL}; }}

/* Botones: pill. Base = secundario ghost (borde navy). */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  border-radius: 999px !important;
  font-weight: 700;
  padding: 0.5rem 1.25rem;
  border: 1.5px solid {NAVY};
  background: #FFFFFF;
  color: {NAVY};
  box-shadow: none;
  transition: background .15s ease, color .15s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{
  background: {GRAY_50};
  color: {NAVY};
  border-color: {NAVY};
}}
/* CTA primario = relleno gradiente, texto navy ExtraBold, sin borde. */
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primaryFormSubmit"], .stButton > button[data-testid="baseButton-primary"] {{
  background: {GRADIENT} !important;
  color: {NAVY} !important;
  border: none !important;
  font-weight: 800;
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {{
  filter: brightness(1.03);
  color: {NAVY} !important;
}}

/* Focus teal accesible. */
button:focus-visible, input:focus-visible, textarea:focus-visible, [tabindex]:focus-visible {{
  outline: 2px solid {TEAL} !important;
  outline-offset: 2px;
}}

/* Sidebar tintado gris-50. */
[data-testid="stSidebar"] {{ background: {GRAY_50}; border-right: 1px solid {GRAY_BORDER}; }}

/* Barra de progreso con el gradiente. */
.stProgress > div > div > div > div,
[data-testid="stProgressBar"] > div > div {{ background: {GRADIENT} !important; }}

/* Chat con estilo card + sombra neutra. */
[data-testid="stChatMessage"] {{
  background: #FFFFFF;
  border: 1px solid {GRAY_BORDER};
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(16,37,50,0.06);
}}

/* Contenedores con borde: card look, sombra neutra. */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 14px; }}

/* Métricas en navy. */
[data-testid="stMetricValue"] {{ color: {NAVY}; font-weight: 800; }}
</style>
"""


def inject_ms_theme() -> None:
    """Inyecta el CSS de marca. Llamar una vez, tras st.set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


def ms_eyebrow(text: str) -> None:
    """Rótulo en mayúsculas con el gradiente de marca (sobre una sección)."""
    st.markdown(
        f"<div style=\"font:800 12px/1.3 'Red Hat Display',sans-serif;letter-spacing:.12em;"
        f"text-transform:uppercase;background:{GRADIENT};-webkit-background-clip:text;"
        f"background-clip:text;-webkit-text-fill-color:transparent;color:transparent;"
        f"margin:0 0 .35rem\">{text}</div>",
        unsafe_allow_html=True,
    )


def ms_gradient_number(value: str, label: str) -> None:
    """Stat: número grande con gradiente + label en mayúsculas."""
    st.markdown(
        f"<div style=\"font:900 40px/1 'Red Hat Display',sans-serif;background:{GRADIENT};"
        f"-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;"
        f"color:transparent\">{value}</div>"
        f"<div style=\"font:700 12px/1.3 'Red Hat Display',sans-serif;letter-spacing:.1em;"
        f"text-transform:uppercase;color:{NAVY};opacity:.7;margin-top:.15rem\">{label}</div>",
        unsafe_allow_html=True,
    )


def ms_card(inner_html: str) -> None:
    """Card blanca con borde y sombra neutra (nunca borde-izquierdo de color)."""
    st.markdown(
        f"<div style=\"background:#fff;border:1px solid {GRAY_BORDER};border-radius:16px;"
        f"padding:1.25rem;box-shadow:0 1px 3px rgba(16,37,50,.06)\">{inner_html}</div>",
        unsafe_allow_html=True,
    )

"""Calificador de leads — app interna (Streamlit), approach redefinido.

Dos vistas:
- 🧭 Definir campaña: chat multi-turno con Claude → filtros Sales Nav + rúbrica +
  propuesta de valor, guardado como campaña reutilizable.
- 🎯 Calificar: subís el CSV de Sales Navigator, elegís una campaña (o escribís la
  rúbrica), la IA califica en tiers A/B/C/D con el por qué, filtrás y exportás CSV.

(La búsqueda en Apollo y el ICP de criterios/pesos quedaron en app_legacy.py.)

Correr:  streamlit run ui/app.py   (requiere  pip install -e ".[ui]")
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT / "ui"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import streamlit as st  # noqa: E402

import campaigns  # noqa: E402
import chat_builder  # noqa: E402
import context as ms_context  # noqa: E402
import enrich  # noqa: E402
import qualify  # noqa: E402

try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:  # noqa: BLE001
    pass


def _load_dotenv() -> None:
    env = _ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


DEFAULT_VP = ("Making Sense desarrolla software a medida y producto digital "
              "para empresas tech-enabled.")
DEFAULT_RUBRIC = """\
Describí a quién buscás y qué hace a un lead A / B / C / D. Ejemplo:
- A: CFO / Director Financiero de fintech o empresa de software / tech-enabled, mid-market (50-2000), AR/LATAM.
- B: Finanzas en una empresa de servicios profesionales con algo de tecnología.
- C: Empresa tradicional / no-tech, o tamaño / geografía dudosos.
- D: No fit — rol equivocado, gobierno / educación, otro rubro, o perfil de ruido."""
TIER_COLOR = {"A": "#16a34a", "B": "#2563eb", "C": "#d97706", "D": "#9ca3af"}

# Etiquetas de las señales de enrichment (para mostrar) + qué keys NO son insights.
SIGNAL_LABELS = {s["key"]: s["label"]
                 for s in (enrich.SIGNAL_CATALOG + enrich.CORE_SIGNALS)}
_BASE_LEAD_KEYS = {"tier", "name", "title", "company", "domain", "size", "industry",
                   "location", "email", "linkedin", "reason"}


def _insight_keys(lead: dict) -> list[str]:
    """Keys del lead que son insights de enrichment (no campos base)."""
    return [k for k in lead if k not in _BASE_LEAD_KEYS]


def _require_auth() -> None:
    """Candado de contraseña (la app gasta créditos → no puede quedar abierta).
    Se activa solo si hay APP_PASSWORD configurada; sin ella (dev local) queda abierta."""
    import hmac
    expected = os.getenv("APP_PASSWORD", "")
    if not expected or st.session_state.get("auth_ok"):
        return
    st.title("🔒 Calificador de leads")
    st.caption("Ingresá la contraseña para continuar.")
    pw = st.text_input("Contraseña", type="password")
    if pw:
        if hmac.compare_digest(pw, expected):
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.stop()


st.set_page_config(page_title="Calificador de leads", page_icon="🎯", layout="centered")
_load_dotenv()
_require_auth()
st.session_state.setdefault("view", "qualify")
HAS_CLAUDE = bool(os.getenv("ANTHROPIC_API_KEY"))


# ==========================================================================
# Vista: Definir campaña (chat multi-turno)
# ==========================================================================
def render_chat() -> None:
    st.title("🧭 Definir campaña")
    st.caption("Charlá con la IA sobre tu campaña. Te ayuda a iterar los filtros de "
               "Sales Navigator, la rúbrica de calificación y la propuesta de valor.")
    if not HAS_CLAUDE:
        st.warning("Falta ANTHROPIC_API_KEY.")

    if "chat" not in st.session_state:
        st.session_state["chat"] = [{"role": "assistant", "content": chat_builder.INTRO}]
    if st.button("🗑️ Empezar de nuevo"):
        st.session_state["chat"] = [{"role": "assistant", "content": chat_builder.INTRO}]
        st.session_state.pop("draft_campaign", None)
        st.rerun()

    for m in st.session_state["chat"]:
        st.chat_message(m["role"]).write(m["content"])

    if prompt := st.chat_input("Contale sobre tu campaña…", disabled=not HAS_CLAUDE):
        st.session_state["chat"].append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)
        with st.chat_message("assistant"), st.spinner("Pensando…"):
            try:
                reply = chat_builder.chat_reply(st.session_state["chat"],
                                                context=ms_context.load_context())
            except Exception as exc:  # noqa: BLE001
                reply = f"Error: {exc}"
            st.write(reply)
        st.session_state["chat"].append({"role": "assistant", "content": reply})

    # Generar la campaña estructurada desde la charla
    if len([m for m in st.session_state["chat"] if m["role"] == "user"]) >= 1:
        if st.button("✨ Generar campaña desde la charla", type="primary", disabled=not HAS_CLAUDE):
            with st.spinner("Armando la campaña…"):
                try:
                    st.session_state["draft_campaign"] = chat_builder.extract_campaign(
                        st.session_state["chat"], context=ms_context.load_context())
                except Exception as exc:  # noqa: BLE001
                    st.error(f"No se pudo generar:\n\n{exc}")

    draft = st.session_state.get("draft_campaign")
    if draft:
        st.divider()
        st.subheader("Campaña propuesta — revisá y guardá")
        draft["name"] = st.text_input("Nombre", value=draft.get("name", ""))
        draft["sales_nav_filters"] = [
            f.strip() for f in st.text_area(
                "Filtros para Sales Navigator (uno por línea)",
                value="\n".join(draft.get("sales_nav_filters", [])), height=120).splitlines()
            if f.strip()]
        draft["rubric"] = st.text_area("Rúbrica (A/B/C/D)", value=draft.get("rubric", ""), height=180)
        draft["value_prop"] = st.text_area("Propuesta de valor", value=draft.get("value_prop", ""),
                                           height=70)
        st.caption("✨ Señales de enrichment que Claude sugiere para esta campaña "
                   "(una por línea — `etiqueta: qué averiguar`). Editá libremente.")
        draft["enrichment_signals"] = enrich.resolve_signals(enrich.parse_custom_signals(
            st.text_area("Señales de enrichment",
                         value="\n".join(f"{s['label']}: {s['question']}"
                                         for s in draft.get("enrichment_signals", [])),
                         height=120, label_visibility="collapsed")))
        if st.button("💾 Guardar campaña", type="primary"):
            slug = campaigns.save_campaign(draft)
            st.success(f"Campaña guardada: **{draft['name']}**. Ya podés usarla en 🎯 Calificar.")
            st.session_state["loaded_campaign"] = slug


# ==========================================================================
# Vista: Calificar
# ==========================================================================
def render_qualify() -> None:
    st.title("🎯 Calificar leads")
    st.caption("Subí tu lista de Sales Navigator, elegí una campaña (o escribí la rúbrica), "
               "y la IA califica en tiers A/B/C/D con el por qué. Después filtrás y exportás.")

    # 1. Campaña / rúbrica
    st.subheader("1. Campaña")
    camps = campaigns.list_campaigns()
    rubric_default, vp_default, name_default = DEFAULT_RUBRIC, DEFAULT_VP, ""
    loaded_filters: list[str] = []
    loaded_signals: list[dict] = []
    if camps:
        options = ["(escribir manualmente)"] + [c["name"] for c in camps]
        idx = 0
        loaded = st.session_state.get("loaded_campaign")
        if loaded:
            slugs = [c["slug"] for c in camps]
            if loaded in slugs:
                idx = slugs.index(loaded) + 1
        choice = st.selectbox("Usar campaña guardada", options, index=idx)
        if choice != "(escribir manualmente)":
            c = next(c for c in camps if c["name"] == choice)
            rubric_default, vp_default, name_default = c["rubric"], c["value_prop"], c["name"]
            loaded_filters = c.get("sales_nav_filters", [])
            loaded_signals = c.get("enrichment_signals", [])
            if loaded_filters:
                st.info("**Filtros sugeridos para Sales Navigator:**\n\n- "
                        + "\n- ".join(loaded_filters))
    else:
        st.caption("Tip: podés definir campañas con el chat en 🧭 Definir campaña.")

    name = st.text_input("Nombre de la campaña", value=name_default,
                         placeholder="Ej: CFOs fintech Argentina")
    rubric = st.text_area("Rúbrica — qué hace a un lead A / B / C / D", value=rubric_default,
                          height=180)
    value_prop = st.text_area("Propuesta de valor (para evaluar el fit)", value=vp_default,
                              height=68)

    if st.button("💡 Sugerí mejoras a esta campaña", disabled=not (HAS_CLAUDE and rubric.strip())):
        camp = {"name": name, "rubric": rubric, "value_prop": value_prop,
                "sales_nav_filters": loaded_filters}
        with st.spinner("Analizando la campaña contra el contexto de Making Sense…"):
            try:
                st.session_state["suggestions"] = chat_builder.suggest_improvements(
                    camp, context=ms_context.load_context(),
                    results=st.session_state.get("results"))
            except Exception as exc:  # noqa: BLE001
                st.session_state["suggestions"] = f"Error: {exc}"
    if st.session_state.get("suggestions"):
        with st.expander("💡 Recomendaciones para mejorar la campaña", expanded=True):
            st.markdown(st.session_state["suggestions"])
            if st.button("Ocultar"):
                st.session_state.pop("suggestions", None)
                st.rerun()

    # 2. Lista
    st.subheader("2. Tu lista")
    up = st.file_uploader("Subí un CSV (Sales Navigator, Apollo, Clay, export propio…)",
                          type=["csv"])
    leads: list[dict] = []
    if up is not None:
        headers, rows = qualify.read_csv(up.getvalue().decode("utf-8", errors="replace"))
        if not headers:
            st.error("No pude leer columnas del CSV. ¿Está separado por comas y con encabezados?")
        else:
            auto = qualify.detect_mapping(headers)
            with st.expander("🔗 Columnas detectadas — revisá y corregí",
                             expanded=not auto.get("company")):
                st.caption("Asigná cada campo a una columna de tu CSV. Lo que quede en "
                           "«(ninguno)» se ignora. Sirve para cualquier formato de lista.")
                opts = ["(ninguno)"] + headers
                mapping: dict[str, str] = {}
                mcols = st.columns(2)
                for i, t in enumerate(qualify.TARGET_FIELDS):
                    with mcols[i % 2]:
                        d = auto.get(t) or ""
                        sel = st.selectbox(qualify.TARGET_LABELS[t], opts,
                                           index=opts.index(d) if d in opts else 0,
                                           key=f"map_{t}")
                        mapping[t] = "" if sel == "(ninguno)" else sel
            leads = qualify.leads_from_rows(rows, mapping)
            if not (mapping.get("company") or mapping.get("name")):
                st.warning("Asigná al menos **Empresa** o **Nombre** para poder calificar bien.")
            st.success(f"✅ {len(leads)} leads leídos.")
            with st.expander("Ver los primeros 5"):
                st.dataframe([{k: ld[k] for k in ["name", "title", "company", "domain", "size"]}
                              for ld in leads[:5]], use_container_width=True)

    # 3. Calificar
    st.subheader("3. Calificar")
    if not HAS_CLAUDE:
        st.warning("Falta ANTHROPIC_API_KEY.")
    top = min(len(leads), 100)
    if top >= 2:
        n = st.slider("¿Cuántos calificar?", 1, top, min(top, 20))
    else:
        n = top  # 0 (sin lista aún) o 1 (un solo lead) → sin slider
        if not leads:
            st.caption("Subí un CSV arriba para calificar.")
    if leads:
        st.caption(f"⚠️ Califica los primeros **{n}**. Cada lead = 1 llamada a Claude.")
    if st.button("🎯 Calificar lista", type="primary",
                 disabled=not (leads and HAS_CLAUDE and rubric.strip())):
        err = None
        with st.spinner(f"Calificando {n} leads…"):
            try:
                st.session_state["results"] = qualify.qualify_leads(
                    leads[:n], rubric, value_prop, context=ms_context.load_context())
                st.session_state["camp_name"] = name or "leads"
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
        if err:
            st.error(f"No se pudo calificar:\n\n{err}")

    # 4. Resultados + export
    res = st.session_state.get("results")
    if res:
        st.subheader("4. Resultados")
        counts = Counter(r["tier"] for r in res)
        cols = st.columns(4)
        for i, t in enumerate(["A", "B", "C", "D"]):
            cols[i].metric(f"Tier {t}", counts.get(t, 0))
        pick = st.multiselect("Mostrar tiers", ["A", "B", "C", "D"], default=["A", "B"])
        shown = [r for r in res if r["tier"] in pick]
        st.download_button(
            f"⬇️ Descargar CSV ({len(shown)} leads)", qualify.leads_to_csv(shown),
            file_name=f"{st.session_state.get('camp_name', 'leads')}_calificados.csv",
            mime="text/csv", type="primary")
        for r in shown:
            c = TIER_COLOR.get(r["tier"], "#9ca3af")
            with st.container(border=True):
                st.markdown(
                    f"<span style='background:{c};color:#fff;border-radius:6px;padding:1px 8px;"
                    f"font-weight:800'>{r['tier']}</span> &nbsp;<b>{r['name']}</b> — "
                    f"{r.get('title', '')} · {r.get('company', '')}", unsafe_allow_html=True)
                st.caption(r.get("reason", ""))
                _ins = [(k, r[k]) for k in _insight_keys(r) if r.get(k)]
                if _ins:
                    with st.expander("✨ Insights para el mensaje"):
                        for _k, _v in _ins:
                            _lbl = SIGNAL_LABELS.get(_k, _k.replace("_", " ").capitalize())
                            st.markdown(f"**{_lbl}:** {_v}")

        # 5. Enriquecer (opcional) — señales de NEGOCIO para el mensaje, configurables
        st.subheader("5. Enriquecer (opcional)")
        st.caption("Suma señales de **negocio** para el mensaje. Las señales varían por campaña — "
                   "elegí del catálogo y/o pedí a medida. Enriquece 1 empresa única = 1 crédito Apollo.")
        # Señales pre-cargadas desde la campaña (o defaults).
        base_sig = loaded_signals or [dict(s) for s in enrich.default_signals()]
        cat_keys = {s["key"] for s in enrich.SIGNAL_CATALOG}
        cat_default = [s["label"] for s in enrich.resolve_signals(base_sig) if s["key"] in cat_keys]
        custom_default = "\n".join(f"{s['label']}: {s['question']}"
                                   for s in enrich.resolve_signals(base_sig)
                                   if s["key"] not in cat_keys)
        picked_cat = st.multiselect("Señales del catálogo", enrich.catalog_labels(),
                                    default=cat_default, key="enrich_cat")
        custom_txt = st.text_area("Señales a medida (una por línea — `etiqueta: qué averiguar`)",
                                  value=custom_default, height=90, key="enrich_custom")
        chosen = enrich.resolve_signals(
            [enrich.signal_from_label(lbl) for lbl in picked_cat]
            + enrich.parse_custom_signals(custom_txt))
        st.caption("Siempre se agregan: **Match propuesta de valor** y **Hook**. "
                   + (f"Señales elegidas: {', '.join(s['label'] for s in chosen)}."
                      if chosen else "Sin señales extra (solo el núcleo)."))

        etiers = st.multiselect("¿Qué tiers enriquecer?", ["A", "B", "C", "D"],
                                default=["A", "B"], key="enrich_tiers")
        to_enrich = [r for r in res if r["tier"] in etiers]
        n_emp = len({(r.get("domain") or "").strip().lower()
                     for r in to_enrich if r.get("domain")})
        st.caption(f"⚠️ Enriquece **{len(to_enrich)}** leads "
                   f"(~{n_emp} empresas únicas → {n_emp} créditos de Apollo).")
        if st.button("✨ Enriquecer seleccionados",
                     disabled=not (to_enrich and HAS_CLAUDE)):
            err = None
            with st.spinner(f"Enriqueciendo {len(to_enrich)} leads…"):
                try:
                    enriched = enrich.enrich_leads(
                        to_enrich, value_prop, context=ms_context.load_context(),
                        signals=chosen)
                    by_key = {(e.get("name"), e.get("company")): e for e in enriched}
                    st.session_state["results"] = [
                        by_key.get((r.get("name"), r.get("company")), r) for r in res]
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
            if err:
                st.error(f"No se pudo enriquecer:\n\n{err}")
            else:
                st.rerun()


# ==========================================================================
# Vista: Contexto de Making Sense
# ==========================================================================
def render_context() -> None:
    st.title("🏢 Contexto de Making Sense")
    st.caption("Mantené acá el contexto vivo de Making Sense: servicios, propuesta de valor, "
               "diferenciadores, casos de éxito, aprendizajes y verticales foco. El agente lo usa "
               "para groundear el chat de campaña y el match de propuesta de valor.")
    if not ms_context.has_saved_context():
        st.info("Sembrado desde tu doc del proyecto. Editá y guardá para hacerlo tuyo.")
    txt = st.text_area("Contexto (markdown)", value=ms_context.load_context(),
                       height=480, key="ms_ctx")
    if st.button("💾 Guardar contexto", type="primary"):
        ms_context.save_context(txt)
        st.success("Contexto guardado. El agente ya lo usa en el chat y en la calificación.")


# ==========================================================================
# Router
# ==========================================================================
with st.sidebar:
    st.markdown("### 🎯 Calificador de leads")
    if st.button("🎯 Calificar", use_container_width=True):
        st.session_state["view"] = "qualify"
        st.rerun()
    if st.button("🧭 Definir campaña", use_container_width=True):
        st.session_state["view"] = "chat"
        st.rerun()
    if st.button("🏢 Contexto", use_container_width=True):
        st.session_state["view"] = "context"
        st.rerun()
    st.caption("POC LeadGen · Making Sense")

view = st.session_state["view"]
if view == "chat":
    render_chat()
elif view == "context":
    render_context()
else:
    render_qualify()

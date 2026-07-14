"""Buscador de clientes ideales — app interna (Streamlit).

Tres vistas: 🗂️ Biblioteca (ICPs guardados + sus búsquedas) → 🔧 Builder (definir el
ICP en lenguaje simple, con asistente de IA) → 🔍 Resultados (armar lista, calificar
y marcar fit/no-fit). Todo se apoya en el motor (scoring, multi-ICP, fit-rate) y los
adapters (Apollo, Claude).

Correr:  streamlit run ui/app.py   (requiere  pip install -e ".[ui]")
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT / "ui"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import os  # noqa: E402

import streamlit as st  # noqa: E402
import yaml  # noqa: E402

import ai_assist  # noqa: E402
import icp_io  # noqa: E402
import icp_translate as tr  # noqa: E402
import leadgen  # noqa: E402
import store  # noqa: E402

# En hosting, exponer st.secrets como variables de entorno para los adapters.
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:  # noqa: BLE001
    pass

ICP_DIR = _ROOT / "icp"
TIER_COLOR = {"A": "#16a34a", "B": "#2563eb", "C": "#d97706", "D": "#9ca3af"}
IMP_OPTS = ["No aplica", "Suma", "Importante", "Imprescindible"]
IMP_TO_VAL = {"No aplica": None, "Suma": "suma", "Importante": "importante",
              "Imprescindible": "imprescindible"}
VAL_TO_IMP = {None: "No aplica", "suma": "Suma", "importante": "Importante",
              "imprescindible": "Imprescindible"}
DB_LABELS = {"too_small": "Empresas muy chicas (<50 empl.)",
             "gov_edu": "Gobierno / educación",
             "outside_region": "Fuera de las regiones elegidas"}

st.set_page_config(page_title="Buscador de clientes ideales", page_icon="🔍", layout="centered")
leadgen.load_dotenv()
st.session_state.setdefault("view", "library")


def _go(view: str, **kw) -> None:
    st.session_state.view = view
    for k, v in kw.items():
        st.session_state[k] = v
    st.rerun()


def _badge(tier: str) -> str:
    c = TIER_COLOR.get(tier, "#9ca3af")
    return (f"<span style='background:{c};color:#fff;border-radius:6px;padding:2px 9px;"
            f"font-weight:800;font-size:13px'>{tier}</span>")


# --------------------------------------------------------------------------
# Vista: Biblioteca
# --------------------------------------------------------------------------
def render_library() -> None:
    c1, c2 = st.columns([3, 1])
    c1.title("🗂️ Mis ICPs")
    if c2.button("＋ Nuevo ICP", use_container_width=True):
        _go("builder", sel_icp=None)
    st.caption("Tus perfiles de cliente ideal y las búsquedas que corriste con cada uno.")

    files = icp_io.list_icps(ICP_DIR)
    if not files:
        st.info("Todavía no hay ICPs. Creá el primero con **＋ Nuevo ICP**.")
        return

    for f in files:
        data = icp_io.load_icp_dict(f)
        meta = data.get("meta", {})
        icp_id = meta.get("id", f.stem)
        stats = store.icp_stats(icp_id)
        with st.container(border=True):
            h1, h2, h3 = st.columns([3, 1, 1])
            h1.markdown(f"### {meta.get('name', f.stem)}")
            h1.caption(f"`{icp_id}` · v{meta.get('version','?')} · {meta.get('status','draft')}")
            fr = stats["fit_rate"]
            h2.metric("fit-rate", f"{fr}%" if fr is not None else "—")
            h3.metric("búsquedas", stats["n_runs"])

            b1, b2 = st.columns(2)
            if b1.button("🔍 Buscar leads", key=f"search_{icp_id}", use_container_width=True):
                _go("results", sel_icp=f.name, results_mode="new", current_run=None)
            if b2.button("✏️ Editar ICP", key=f"edit_{icp_id}", use_container_width=True):
                _go("builder", sel_icp=f.name)

            runs = store.list_runs(icp_id)
            if runs:
                with st.expander(f"Búsquedas guardadas ({len(runs)})"):
                    for r in runs:
                        tiers = " · ".join(f"{n} {t}" for t, n in sorted(r["tier_counts"].items()))
                        rc1, rc2, rc3 = st.columns([2, 2, 1])
                        kind_lbl = {"companies": "empresas", "list": "de tu lista"}.get(
                            r.get("mode"), "personas")
                        rc1.write(r["created_at"][:16].replace("T", " "))
                        rc2.caption(f"{r['n_leads']} {kind_lbl} · {tiers}")
                        if rc3.button("Ver →", key=f"view_{icp_id}_{r['run_id']}"):
                            _go("results", sel_icp=f.name, results_mode="view",
                                current_run=(icp_id, r["run_id"]))


# --------------------------------------------------------------------------
# Vista: Builder (lenguaje simple + asistente IA)
# --------------------------------------------------------------------------
def _init_builder_state(simple: dict) -> None:
    """Carga el modelo simple en el state de los widgets (para que se pre-llenen)."""
    ss = st.session_state
    ss["b_name"] = simple.get("name", "")
    ss["b_status"] = simple.get("status", "draft")
    ss["b_size"] = tuple(simple["size"])
    ss["b_regions"] = list(simple["regions"])
    ss["b_seniority"] = list(simple["seniority"])
    ss["b_departments"] = list(simple["departments"])
    ss["b_keywords"] = ", ".join(simple.get("keywords", []))
    ss["b_titles"] = ", ".join(simple.get("titles", []))
    imp_by_id = {i["id"]: i.get("importance") for i in simple["ideal"]}
    for tid in tr.FUZZY_CATALOG:
        ss[f"b_imp_{tid}"] = VAL_TO_IMP[imp_by_id.get(tid)]
    for k in DB_LABELS:
        ss[f"b_db_{k}"] = k in simple["dealbreakers"]


def _collect_simple() -> dict:
    ss = st.session_state
    return {
        "name": ss["b_name"], "status": ss["b_status"], "size": list(ss["b_size"]),
        "regions": ss["b_regions"], "seniority": ss["b_seniority"],
        "departments": ss["b_departments"],
        "ideal": [{"id": tid, "importance": IMP_TO_VAL[ss[f"b_imp_{tid}"]]}
                  for tid in tr.FUZZY_CATALOG],
        "dealbreakers": [k for k in DB_LABELS if ss[f"b_db_{k}"]],
        "keywords": [k.strip() for k in ss.get("b_keywords", "").split(",") if k.strip()],
        "titles": [t.strip() for t in ss.get("b_titles", "").split(",") if t.strip()],
    }


def render_builder() -> None:
    if st.button("← Volver a la biblioteca"):
        _go("library")
    sel = st.session_state.get("sel_icp")
    today = datetime.now(UTC).date().isoformat()
    st.title("🔧 Editar ICP" if sel else "🔧 Nuevo ICP")

    # Inicializar el state del formulario al entrar/cambiar de ICP.
    target = sel or "__new__"
    if st.session_state.get("_builder_target") != target:
        base = (tr.icp_to_simple(icp_io.load_icp_dict(ICP_DIR / sel)) if sel
                else tr.icp_to_simple(tr.new_icp_dict("Nuevo ICP", today)))
        _init_builder_state(base)
        st.session_state["_builder_target"] = target
        st.session_state["ai_reasoning"] = ""

    # --- Asistente con IA ---
    has_claude = bool(os.getenv("ANTHROPIC_API_KEY"))
    with st.expander("✨ Crear / completar con IA", expanded=not sel):
        st.caption("Describí tu cliente ideal en palabras y la IA propone el ICP. Después lo ajustás.")
        desc = st.text_area("descripción", key="b_ai_desc", label_visibility="collapsed",
                            placeholder="Ej: Empresas de servicios financieros en LATAM, medianas, "
                                        "que usan plataformas tecnológicas propias. Les hablo a CTOs "
                                        "y VPs de producto. No me sirven las muy chicas ni el gobierno.")
        gen = st.button("✨ Generar propuesta", disabled=not has_claude or not desc.strip())
        if not has_claude:
            st.caption("⚠️ Falta ANTHROPIC_API_KEY para usar la IA.")
        if gen:
            proposed, err = None, None
            with st.spinner("Pensando tu ICP…"):
                try:
                    proposed = ai_assist.propose_icp(desc)
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
            if err:
                st.error(f"No se pudo generar:\n\n{err}")
            elif proposed:
                _init_builder_state(proposed)
                st.session_state["ai_reasoning"] = proposed.get("reasoning", "")
                st.rerun()

    if st.session_state.get("ai_reasoning"):
        st.info("✨ Propuesta de la IA: " + st.session_state["ai_reasoning"])

    # --- Formulario (widgets manejados por session_state) ---
    name = st.text_input("Nombre del ICP", key="b_name")
    st.selectbox("Estado", ["draft", "active", "retired"], key="b_status",
                 format_func=lambda s: {"draft": "Borrador", "active": "Activo",
                                        "retired": "Retirado"}[s])

    st.subheader("¿Qué hace ideal a una empresa?")
    st.caption("Marcá qué tan importante es cada cosa.")
    for tid, info in tr.FUZZY_CATALOG.items():
        st.markdown(f"**{info['label']}**  \n<small style='color:#888'>{info['hint']}</small>",
                    unsafe_allow_html=True)
        st.radio(tid, IMP_OPTS, key=f"b_imp_{tid}", horizontal=True, label_visibility="collapsed")

    st.subheader("Tamaño de empresa (empleados)")
    st.slider("empleados", 10, 10000, step=10, key="b_size", label_visibility="collapsed")

    st.subheader("¿Qué sector / rubro?")
    st.text_input("sector", key="b_keywords", label_visibility="collapsed",
                  placeholder="Ej: legal services, law firms (separá por comas). Vacío = cualquier sector.",
                  help="Filtra la búsqueda en Apollo. Un ICP de 'legal services' no traerá fintech.")

    st.subheader("¿Dónde?")
    st.multiselect("regiones", list(tr.REGION_LABELS), key="b_regions",
                   format_func=tr.REGION_LABELS.get, label_visibility="collapsed")

    st.subheader("¿A quién le hablás?")
    st.multiselect("seniority", list(tr.SENIORITY_LABELS), key="b_seniority",
                   format_func=tr.SENIORITY_LABELS.get)
    st.multiselect("área", list(tr.DEPARTMENT_LABELS), key="b_departments",
                   format_func=tr.DEPARTMENT_LABELS.get)
    st.text_input("Títulos específicos (opcional)", key="b_titles",
                  placeholder="Ej: Operating Partner, Chief Digital Officer (separá por comas)",
                  help="Para roles que no entran en seniority/área. Filtra la búsqueda por "
                       "esos títulos exactos en Apollo.")

    st.subheader("Nunca trabajar con…")
    for k, label in DB_LABELS.items():
        st.checkbox(label, key=f"b_db_{k}")

    new_simple = _collect_simple()
    with st.expander("⚙️ Modo avanzado (ver el ICP técnico)"):
        base = icp_io.load_icp_dict(ICP_DIR / sel) if sel else tr.new_icp_dict(name or "nuevo", today)
        preview = tr.apply_simple_to_icp(base, dict(new_simple))
        st.code(yaml.safe_dump(preview, sort_keys=False, allow_unicode=True), language="yaml")

    st.divider()
    bump = st.radio("Tipo de cambio", ["patch", "minor", "major"], horizontal=True,
                    help="patch: ajustes · minor: agregar criterios · major: cambia la lógica")
    note = st.text_input("Nota de cambio", placeholder="Ej: subí la importancia de tech-enabled")
    if st.button("💾 Guardar ICP", type="primary"):
        data = icp_io.load_icp_dict(ICP_DIR / sel) if sel else tr.new_icp_dict(name or "nuevo", today)
        tr.apply_simple_to_icp(data, new_simple)
        ok, err = icp_io.validate_icp_dict(data)
        if not ok:
            st.error(f"No se puede guardar (inválido):\n\n{err}")
        elif not note.strip():
            st.error("Poné una nota de cambio antes de guardar.")
        else:
            icp_io.apply_version_bump(data, bump, note.strip(), datetime.now(UTC).date())
            icp_io.save_icp_dict(data, ICP_DIR / f"{data['meta']['id']}.yaml")
            st.success(f"Guardado → v{data['meta']['version']}")
            st.session_state["_builder_target"] = None  # forzar reinit al volver
            _go("library")


# --------------------------------------------------------------------------
# Vista: Resultados
# --------------------------------------------------------------------------
def _render_leads(icp_id: str, run_id: str, run: dict) -> None:
    feedback = run.get("feedback", {})
    st.caption(f"{len(run['leads'])} leads · búsqueda {run_id} · ICP v{run.get('icp_version','?')}")
    for lead in run["leads"]:
        lid = lead["lead_id"]
        with st.container(border=True):
            cols = st.columns([1, 5, 2])
            cols[0].markdown(_badge(lead.get("tier", "D")) + f"<br><b>{lead.get('fit',0):.0f}</b>",
                             unsafe_allow_html=True)
            cols[1].markdown(f"**{lead.get('empresa','?')}** — {lead.get('contacto','?')}")
            cols[1].caption(f"{lead.get('titulo') or ''} · {lead.get('industria') or ''} · "
                            f"{lead.get('empleados') or '?'} empl"
                            + ("  ·  ⛔ descalificado" if lead.get("descalificado") else ""))
            if lead.get("unmatched"):
                cols[2].caption("no encontrado en Apollo")
                continue
            mark = feedback.get(lid)
            y, n = cols[2].columns(2)
            if y.button("👍" if mark != "fit" else "✅", key=f"fit_{lid}"):
                store.set_feedback(icp_id, run_id, lid, None if mark == "fit" else "fit")
                st.rerun()
            if n.button("👎" if mark != "no_fit" else "❌", key=f"nofit_{lid}"):
                store.set_feedback(icp_id, run_id, lid, None if mark == "no_fit" else "no_fit")
                st.rerun()
            with cols[1].expander("¿por qué?"):
                for fz in lead.get("fuzzy", []):
                    st.markdown(f"- **{fz['id']}**: {fz['score']} — {fz['rationale']}")


def render_results() -> None:
    if st.button("← Volver a la biblioteca"):
        _go("library")
    sel = st.session_state.get("sel_icp")
    if not sel:
        _go("library")
        return
    data = icp_io.load_icp_dict(ICP_DIR / sel)
    icp_id = data["meta"]["id"]
    st.title(f"🔍 {data['meta'].get('name', icp_id)}")

    cur = st.session_state.get("current_run")
    if st.session_state.get("results_mode") == "view" and cur:
        _render_leads(cur[0], cur[1], store.load_run(cur[0], cur[1]))
        return

    has_apollo = bool(os.getenv("APOLLO_API_KEY"))
    has_claude = bool(os.getenv("ANTHROPIC_API_KEY"))
    s1, s2 = st.columns(2)
    s1.markdown(f"Apollo: {'🟢' if has_apollo else '🔴 falta key'}")
    s2.markdown(f"Claude: {'🟢' if has_claude else '🟡 juez simulado'}")

    kind = st.radio("¿Qué querés hacer?",
                    ["🧑 Buscar personas", "🏢 Buscar empresas", "📋 Calificar mi lista"],
                    horizontal=True,
                    help="Buscar: Apollo trae candidatos que matchean el ICP. "
                         "Calificar mi lista: vos das la lista y la puntúo contra el ICP.")

    res, mode, err = None, None, None

    if kind.startswith("📋"):
        st.caption("Pegá tu lista: CSV con encabezados (email, name, company, domain…), "
                   "o un email por línea, o 'Nombre, Empresa' por línea.")
        up = st.file_uploader("Subir CSV", type=["csv"])
        prefill = up.getvalue().decode("utf-8", errors="ignore") if up is not None else ""
        text = st.text_area("…o pegala acá", value=prefill, height=160, key="b_list",
                            placeholder="email\nana@acme.com\njohn@globex.com\n\n— o —\n"
                                        "Ana García, Acme Legal\nJohn Doe, Globex Insurance")
        rows = leadgen.parse_list(text)
        st.caption(f"**{len(rows)}** contactos detectados. ⚠️ Calificar consume créditos/tokens "
                   f"(~1 por contacto).")
        if st.button("📋 Calificar mi lista", type="primary", disabled=not has_apollo or not rows):
            with st.spinner(f"Enriqueciendo y calificando {len(rows)} contactos…"):
                try:
                    res = asyncio.run(leadgen.score_list(data, rows))
                    mode = "list"
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
    else:
        is_companies = kind.startswith("🏢")
        c1, c2 = st.columns(2)
        pool = c1.slider("Calificar (analizar)", 1, 50, 15,
                         help="Cuántos candidatos enriquecer y calificar. Es lo que cuesta.")
        top = c2.slider("Mostrar los mejores", 1, 25, 5,
                        help="Te muestro los N con mejor fit del grupo calificado.")
        st.caption(f"⚠️ Voy a calificar **{pool}** y te muestro los **{min(top, pool)}** con mejor "
                   f"fit (top tier primero). Hace llamadas reales (créditos/tokens).")
        if st.button("🔍 Armar y calificar", type="primary", disabled=not has_apollo):
            with st.spinner(f"Calificando {pool} candidatos y eligiendo los mejores {top}…"):
                try:
                    if is_companies:
                        res = asyncio.run(leadgen.build_and_score_companies(data, pool=pool, top=top))
                        mode = "companies"
                    else:
                        res = asyncio.run(leadgen.build_and_score(data, pool=pool, top=top))
                        mode = "leads"
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)

    if err:
        st.error(f"No se pudo:\n\n{err}")
    elif res is not None:
        run_id = store.save_run(icp_id, data["meta"].get("version", "?"),
                                res["query"], res["leads"], mode=mode)
        _go("results", results_mode="view", current_run=(icp_id, run_id))


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🔍 Buscador de clientes ideales")
    if st.button("🗂️ Biblioteca", use_container_width=True):
        _go("library")
    st.caption("ICP Engine · POC LeadGen")

view = st.session_state.view
if view == "builder":
    render_builder()
elif view == "results":
    render_results()
else:
    render_library()

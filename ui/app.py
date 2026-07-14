"""Calificador de leads — app interna (Streamlit), approach redefinido.

Tres vistas: 🧭 Definir campaña (chat), 🎯 Calificar (CSV → tiers + enrichment), 🏢 Contexto.
UI bilingüe (ES/EN) vía ui/i18n.py; el idioma vive en session_state['lang'].

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
import i18n  # noqa: E402
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


TIER_COLOR = {"A": "#16a34a", "B": "#2563eb", "C": "#d97706", "D": "#9ca3af"}
_BASE_LEAD_KEYS = {"tier", "name", "title", "company", "domain", "size", "industry",
                   "location", "email", "linkedin", "reason"}


def _lang() -> str:
    return st.session_state.get("lang", "es")


def L(key: str, **kw) -> str:  # noqa: N802 - atajo corto y muy usado en la UI
    """Atajo de traducción con el idioma actual."""
    return i18n.t(key, _lang(), **kw)


def _signal_label(key: str) -> str:
    """Etiqueta localizada de una señal; fallback a un humanizado del slug."""
    entry = i18n.T.get(f"signal_{key}")
    if entry:
        return L(f"signal_{key}")
    return key.replace("_", " ").capitalize()


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
    st.title("🔒 " + L("app_title").split(" ", 1)[-1])
    st.caption(L("auth_caption"))
    pw = st.text_input(L("auth_password"), type="password")
    if pw:
        if hmac.compare_digest(pw, expected):
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error(L("auth_wrong"))
    st.stop()


st.set_page_config(page_title=i18n.t("page_title"), page_icon="🎯", layout="centered")
_load_dotenv()
st.session_state.setdefault("lang", os.getenv("APP_DEFAULT_LANG", "es"))
_require_auth()
st.session_state.setdefault("view", "qualify")
HAS_CLAUDE = bool(os.getenv("ANTHROPIC_API_KEY"))


# ==========================================================================
# Vista: Definir campaña (chat multi-turno)
# ==========================================================================
def render_chat() -> None:
    lang = _lang()
    st.title(L("chat_title"))
    st.caption(L("chat_caption"))
    if not HAS_CLAUDE:
        st.warning(L("missing_key"))

    intro = i18n.t("chat_intro", lang)
    if "chat" not in st.session_state:
        st.session_state["chat"] = [{"role": "assistant", "content": intro}]
    if st.button(L("chat_restart")):
        st.session_state["chat"] = [{"role": "assistant", "content": intro}]
        st.session_state.pop("draft_campaign", None)
        st.rerun()

    for m in st.session_state["chat"]:
        st.chat_message(m["role"]).write(m["content"])

    if prompt := st.chat_input(L("chat_input_ph"), disabled=not HAS_CLAUDE):
        st.session_state["chat"].append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)
        with st.chat_message("assistant"), st.spinner(L("chat_thinking")):
            try:
                reply = chat_builder.chat_reply(st.session_state["chat"],
                                                context=ms_context.load_context(), lang=lang)
            except Exception as exc:  # noqa: BLE001
                reply = f"Error: {exc}"
            st.write(reply)
        st.session_state["chat"].append({"role": "assistant", "content": reply})

    # Generar la campaña estructurada desde la charla
    if len([m for m in st.session_state["chat"] if m["role"] == "user"]) >= 1:
        if st.button(L("chat_generate"), type="primary", disabled=not HAS_CLAUDE):
            with st.spinner(L("chat_building")):
                try:
                    st.session_state["draft_campaign"] = chat_builder.extract_campaign(
                        st.session_state["chat"], context=ms_context.load_context(), lang=lang)
                except Exception as exc:  # noqa: BLE001
                    st.error(L("gen_error", err=exc))

    draft = st.session_state.get("draft_campaign")
    if draft:
        st.divider()
        st.subheader(L("draft_header"))
        draft["name"] = st.text_input(L("f_name"), value=draft.get("name", ""))
        draft["sales_nav_filters"] = [
            f.strip() for f in st.text_area(
                L("f_filters"),
                value="\n".join(draft.get("sales_nav_filters", [])), height=120).splitlines()
            if f.strip()]
        draft["rubric"] = st.text_area(L("f_rubric_abcd"), value=draft.get("rubric", ""), height=180)
        draft["value_prop"] = st.text_area(L("f_value_prop"), value=draft.get("value_prop", ""),
                                           height=70)
        st.caption(L("signals_hint"))
        draft["enrichment_signals"] = enrich.resolve_signals(enrich.parse_custom_signals(
            st.text_area(L("f_signals"),
                         value="\n".join(f"{s['label']}: {s['question']}"
                                         for s in draft.get("enrichment_signals", [])),
                         height=120, label_visibility="collapsed")))
        if st.button(L("save_campaign"), type="primary"):
            slug = campaigns.save_campaign(draft)
            st.success(L("campaign_saved", name=draft["name"]))
            st.session_state["loaded_campaign"] = slug


# ==========================================================================
# Vista: Calificar
# ==========================================================================
def render_qualify() -> None:
    lang = _lang()
    st.title(L("qualify_title"))
    st.caption(L("qualify_caption"))

    # 1. Campaña / rúbrica
    st.subheader(L("sec_campaign"))
    camps = campaigns.list_campaigns()
    rubric_default = i18n.t("default_rubric", lang)
    vp_default, name_default = i18n.t("default_vp", lang), ""
    loaded_filters: list[str] = []
    loaded_signals: list[dict] = []
    if camps:
        options = [L("manual_option")] + [c["name"] for c in camps]
        idx = 0
        loaded = st.session_state.get("loaded_campaign")
        if loaded:
            slugs = [c["slug"] for c in camps]
            if loaded in slugs:
                idx = slugs.index(loaded) + 1
        choice = st.selectbox(L("use_saved"), options, index=idx)
        if choice != L("manual_option"):
            c = next(c for c in camps if c["name"] == choice)
            rubric_default, vp_default, name_default = c["rubric"], c["value_prop"], c["name"]
            loaded_filters = c.get("sales_nav_filters", [])
            loaded_signals = c.get("enrichment_signals", [])
            if loaded_filters:
                st.info(L("filters_suggested") + "\n\n- " + "\n- ".join(loaded_filters))
    else:
        st.caption(L("tip_campaign"))

    name = st.text_input(L("campaign_name"), value=name_default,
                         placeholder=L("campaign_name_ph"))
    rubric = st.text_area(L("rubric_label"), value=rubric_default, height=180)
    value_prop = st.text_area(L("value_prop_label"), value=vp_default, height=68)

    if st.button(L("suggest_btn"), disabled=not (HAS_CLAUDE and rubric.strip())):
        camp = {"name": name, "rubric": rubric, "value_prop": value_prop,
                "sales_nav_filters": loaded_filters}
        with st.spinner(L("suggest_spinner")):
            try:
                st.session_state["suggestions"] = chat_builder.suggest_improvements(
                    camp, context=ms_context.load_context(),
                    results=st.session_state.get("results"), lang=lang)
            except Exception as exc:  # noqa: BLE001
                st.session_state["suggestions"] = f"Error: {exc}"
    if st.session_state.get("suggestions"):
        with st.expander(L("suggest_expander"), expanded=True):
            st.markdown(st.session_state["suggestions"])
            if st.button(L("hide")):
                st.session_state.pop("suggestions", None)
                st.rerun()

    # 2. Lista
    st.subheader(L("sec_list"))
    up = st.file_uploader(L("uploader_label"), type=["csv"])
    leads: list[dict] = []
    if up is not None:
        headers, rows = qualify.read_csv(up.getvalue().decode("utf-8", errors="replace"))
        if not headers:
            st.error(L("csv_read_error"))
        else:
            auto = qualify.detect_mapping(headers)
            with st.expander(L("mapping_expander"), expanded=not auto.get("company")):
                st.caption(L("mapping_caption"))
                opts = [L("none_option")] + headers
                mapping: dict[str, str] = {}
                mcols = st.columns(2)
                for i, field in enumerate(qualify.TARGET_FIELDS):
                    with mcols[i % 2]:
                        d = auto.get(field) or ""
                        sel = st.selectbox(L(f"field_{field}"), opts,
                                           index=opts.index(d) if d in opts else 0,
                                           key=f"map_{field}")
                        mapping[field] = "" if sel == L("none_option") else sel
            leads = qualify.leads_from_rows(rows, mapping)
            if not (mapping.get("company") or mapping.get("name")):
                st.warning(L("warn_map"))
            st.success(L("leads_read", n=len(leads)))
            with st.expander(L("see_first5")):
                st.dataframe([{k: ld[k] for k in ["name", "title", "company", "domain", "size"]}
                              for ld in leads[:5]], use_container_width=True)

    # 3. Calificar
    st.subheader(L("sec_qualify"))
    if not HAS_CLAUDE:
        st.warning(L("missing_key"))
    top = min(len(leads), 100)
    if top >= 2:
        n = st.slider(L("how_many"), 1, top, min(top, 20))
    else:
        n = top  # 0 (sin lista aún) o 1 (un solo lead) → sin slider
        if not leads:
            st.caption(L("upload_to_qualify"))
    if leads:
        st.caption(L("qualify_cost", n=n))
    if st.button(L("qualify_btn"), type="primary",
                 disabled=not (leads and HAS_CLAUDE and rubric.strip())):
        err = None
        with st.spinner(L("qualify_spinner", n=n)):
            try:
                st.session_state["results"] = qualify.qualify_leads(
                    leads[:n], rubric, value_prop, context=ms_context.load_context(), lang=lang)
                st.session_state["camp_name"] = name or "leads"
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
        if err:
            st.error(L("qualify_error", err=err))

    # 4. Resultados + export
    res = st.session_state.get("results")
    if res:
        st.subheader(L("sec_results"))
        counts = Counter(r["tier"] for r in res)
        cols = st.columns(4)
        for i, tier in enumerate(["A", "B", "C", "D"]):
            cols[i].metric(f"Tier {tier}", counts.get(tier, 0))
        pick = st.multiselect(L("show_tiers"), ["A", "B", "C", "D"], default=["A", "B"])
        shown = [r for r in res if r["tier"] in pick]
        st.download_button(
            L("download_csv", n=len(shown)), qualify.leads_to_csv(shown),
            file_name=f"{st.session_state.get('camp_name', 'leads')}_{L('file_suffix')}.csv",
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
                    with st.expander(L("insights_expander")):
                        for _k, _v in _ins:
                            st.markdown(f"**{_signal_label(_k)}:** {_v}")

        # 5. Enriquecer (opcional) — señales de NEGOCIO para el mensaje, configurables
        st.subheader(L("sec_enrich"))
        st.caption(L("enrich_caption"))
        # Señales pre-cargadas desde la campaña (o defaults).
        base_sig = loaded_signals or [dict(s) for s in enrich.default_signals()]
        cat_keys = set(enrich.catalog_keys())
        default_keys = [s["key"] for s in enrich.resolve_signals(base_sig) if s["key"] in cat_keys]
        custom_default = "\n".join(f"{s['label']}: {s['question']}"
                                   for s in enrich.resolve_signals(base_sig)
                                   if s["key"] not in cat_keys)
        picked_keys = st.multiselect(L("catalog_signals"), enrich.catalog_keys(),
                                     default=default_keys, format_func=_signal_label,
                                     key="enrich_cat")
        custom_txt = st.text_area(L("custom_signals"), value=custom_default, height=90,
                                  key="enrich_custom")
        chosen = enrich.resolve_signals(
            [enrich.signal_from_key(k) for k in picked_keys]
            + enrich.parse_custom_signals(custom_txt))
        st.caption(L("core_always")
                   + (L("signals_chosen", list=", ".join(_signal_label(s["key"]) for s in chosen))
                      if chosen else L("signals_none")))

        etiers = st.multiselect(L("which_tiers"), ["A", "B", "C", "D"],
                                default=["A", "B"], key="enrich_tiers")
        to_enrich = [r for r in res if r["tier"] in etiers]
        n_emp = len({(r.get("domain") or "").strip().lower()
                     for r in to_enrich if r.get("domain")})
        st.caption(L("enrich_cost", n=len(to_enrich), e=n_emp))
        if st.button(L("enrich_btn"), disabled=not (to_enrich and HAS_CLAUDE)):
            err = None
            with st.spinner(L("enrich_spinner", n=len(to_enrich))):
                try:
                    enriched = enrich.enrich_leads(
                        to_enrich, value_prop, context=ms_context.load_context(),
                        signals=chosen, lang=lang)
                    by_key = {(e.get("name"), e.get("company")): e for e in enriched}
                    st.session_state["results"] = [
                        by_key.get((r.get("name"), r.get("company")), r) for r in res]
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
            if err:
                st.error(L("enrich_error", err=err))
            else:
                st.rerun()


# ==========================================================================
# Vista: Contexto de Making Sense
# ==========================================================================
def render_context() -> None:
    st.title(L("context_title"))
    st.caption(L("context_caption"))
    if not ms_context.has_saved_context():
        st.info(L("context_seeded"))
    txt = st.text_area(L("context_label"), value=ms_context.load_context(),
                       height=480, key="ms_ctx")
    if st.button(L("save_context"), type="primary"):
        ms_context.save_context(txt)
        st.success(L("context_saved"))


# ==========================================================================
# Router
# ==========================================================================
with st.sidebar:
    _labels = list(i18n.LANGS.keys())
    _codes = list(i18n.LANGS.values())
    _sel = st.radio(L("lang_label"), _labels,
                    index=_codes.index(_lang()) if _lang() in _codes else 0,
                    horizontal=True)
    if i18n.LANGS[_sel] != _lang():
        st.session_state["lang"] = i18n.LANGS[_sel]
        st.rerun()
    st.markdown("### " + L("app_title"))
    if st.button(L("nav_qualify"), use_container_width=True):
        st.session_state["view"] = "qualify"
        st.rerun()
    if st.button(L("nav_chat"), use_container_width=True):
        st.session_state["view"] = "chat"
        st.rerun()
    if st.button(L("nav_context"), use_container_width=True):
        st.session_state["view"] = "context"
        st.rerun()
    st.caption(L("sidebar_footer"))

view = st.session_state["view"]
if view == "chat":
    render_chat()
elif view == "context":
    render_context()
else:
    render_qualify()

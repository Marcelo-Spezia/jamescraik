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

import activity as ms_activity  # noqa: E402
import campaigns  # noqa: E402
import chat_builder  # noqa: E402
import context as ms_context  # noqa: E402
import enrich  # noqa: E402
import exa_enrich as ms_exa  # noqa: E402
import hubspot as ms_hubspot  # noqa: E402
import i18n  # noqa: E402
import leads_store  # noqa: E402
import message as msg_gen  # noqa: E402
import ms_ui  # noqa: E402
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
                   "location", "email", "linkedin", "reason",
                   # campos del pipeline (no son insights de enrichment)
                   "id", "status", "message", "notes", "activity", "campaign_slug",
                   "campaign_name", "updated_at"}
# Estados en los que el lead ya aceptó la conexión → tiene sentido traer su actividad.
_CONNECTED_STATUSES = {"accepted", "message_ready", "sent", "replied"}


def _lang() -> str:
    return st.session_state.get("lang", "es")


def _msg_lang() -> str:
    """Idioma del MENSAJE de outreach, independiente del idioma de la UI.

    El equipo usa la UI en español, pero los prospectos suelen ser en inglés → default 'en'.
    """
    return st.session_state.get("msg_lang", "en")


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
    st.title(L("app_title"))
    st.caption(L("auth_caption"))
    pw = st.text_input(L("auth_password"), type="password")
    if pw:
        if hmac.compare_digest(pw, expected):
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error(L("auth_wrong"))
    st.stop()


st.set_page_config(page_title=i18n.t("page_title"), layout="centered")
ms_ui.apply_theme()  # Making Sense Design System — una sola vez, tras set_page_config
_load_dotenv()
st.session_state.setdefault("lang", os.getenv("APP_DEFAULT_LANG", "es"))
_require_auth()
st.session_state.setdefault("view", "home")
HAS_CLAUDE = bool(os.getenv("ANTHROPIC_API_KEY"))


# ==========================================================================
# Vista: Inicio (biblioteca de campañas)
# ==========================================================================
def _campaign_card(c: dict) -> None:
    slug = c["slug"]
    st.markdown(f"**{c.get('name') or '—'}**")
    vp = (c.get("value_prop") or "").strip() or L("no_vp")
    st.caption(vp[:120] + ("…" if len(vp) > 120 else ""))
    st.caption(L("card_meta", f=len(c.get("sales_nav_filters", [])),
                 s=len(c.get("enrichment_signals", []))))
    upd = (c.get("updated_at") or "")[:10]
    if upd:
        st.caption(L("card_updated", date=upd))

    if st.session_state.get("confirm_delete") == slug:
        st.warning(L("confirm_delete", name=c.get("name") or "—"))
        cc = st.columns(2)
        if cc[0].button(L("confirm_yes"), key=f"delyes_{slug}", type="primary",
                        use_container_width=True):
            campaigns.delete_campaign(slug)
            st.session_state.pop("confirm_delete", None)
            st.rerun()
        if cc[1].button(L("confirm_cancel"), key=f"delno_{slug}", use_container_width=True):
            st.session_state.pop("confirm_delete", None)
            st.rerun()
        return

    if st.button(L("card_use"), key=f"use_{slug}", type="primary", use_container_width=True):
        st.session_state["loaded_campaign"] = slug
        st.session_state["view"] = "qualify"
        st.rerun()
    b = st.columns(3)
    if b[0].button(L("card_edit"), key=f"edit_{slug}", use_container_width=True):
        st.session_state["draft_campaign"] = campaigns.load_campaign(slug)
        st.session_state["view"] = "chat"
        st.rerun()
    if b[1].button(L("card_dup"), key=f"dup_{slug}", use_container_width=True):
        src = campaigns.load_campaign(slug)
        copy = {k: v for k, v in src.items()
                if k not in ("slug", "created_at", "updated_at")}
        copy["name"] = f"{src.get('name', '')} {L('copy_suffix')}".strip()
        campaigns.save_campaign(copy)
        st.rerun()
    if b[2].button(L("card_del"), key=f"del_{slug}", use_container_width=True):
        st.session_state["confirm_delete"] = slug
        st.rerun()


def render_home() -> None:
    st.title(L("home_title"))
    st.caption(L("home_caption"))
    if st.button(L("home_new"), type="primary"):
        st.session_state.pop("draft_campaign", None)
        st.session_state.pop("chat", None)
        st.session_state["view"] = "chat"
        st.rerun()
    try:
        camps = campaigns.list_campaigns()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Error: {exc}")
        return
    if not camps:
        st.info(L("home_empty"))
        return
    st.caption(L("home_count", n=len(camps)))
    for i in range(0, len(camps), 2):
        cols = st.columns(2)
        for col, c in zip(cols, camps[i:i + 2]):
            with col, st.container(border=True):
                _campaign_card(c)


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
    total = len(leads)
    if total >= 2:
        # Sin tope artificial: el máximo es la lista completa; default = toda la lista.
        n = st.slider(L("how_many"), 1, total, total)
    else:
        n = total  # 0 (sin lista aún) o 1 (un solo lead) → sin slider
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
        dcol, scol = st.columns(2)
        dcol.download_button(
            L("download_csv", n=len(shown)), qualify.leads_to_csv(shown),
            file_name=f"{st.session_state.get('camp_name', 'leads')}_{L('file_suffix')}.csv",
            mime="text/csv", use_container_width=True)
        # Guardar en el pipeline persistente (Supabase) — solo los tiers elegidos.
        save_tiers = scol.multiselect(L("save_tiers"), ["A", "B", "C", "D"],
                                      default=["A", "B"], key="save_tiers",
                                      label_visibility="collapsed")
        to_save = [r for r in res if r["tier"] in save_tiers]
        if scol.button(L("save_to_pipeline"), type="primary", use_container_width=True,
                       disabled=not to_save):
            slug = st.session_state.get("loaded_campaign") or campaigns._slug(name)
            try:
                ins, upd = leads_store.get_store().upsert_leads(to_save, slug, name or "leads")
                st.success(L("saved_to_pipeline", ins=ins, upd=upd))
            except Exception as exc:  # noqa: BLE001
                st.error(L("save_error", err=exc))
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
# Vista: Pipeline (leads guardados + estado + mensaje)
# ==========================================================================
def _value_prop_for(lead: dict, camps: list[dict]) -> str:
    camp = next((c for c in camps if c["slug"] == lead.get("campaign_slug")), None)
    return camp.get("value_prop", "") if camp else ""


def _exa_facts(exa: dict) -> list[tuple[str, str, str]]:
    """Facts no-null de Exa → [(clave_label, valor, source_url)] (company + persona)."""
    comp = (exa or {}).get("company") or {}
    pers = (exa or {}).get("person") or {}
    out: list[tuple[str, str, str]] = []
    f = comp.get("funding")
    if f:
        parts = [str(x) for x in (f.get("stage"), f.get("amount_usd"), f.get("date")) if x]
        if parts:
            out.append(("exa_f_funding", " · ".join(parts), f.get("src") or ""))
    for key, lk in (("hiring", "exa_f_hiring"), ("geo", "exa_f_geo")):
        node = comp.get(key)
        if node and node.get("v"):
            out.append((lk, node["v"], node.get("src") or ""))
    for key in ("public_activity", "content", "career_moves", "press"):
        node = pers.get(key)
        if node and node.get("v"):
            out.append((f"exa_f_{key}", node["v"], node.get("src") or ""))
    return out


def _render_exa(exa: dict) -> None:
    facts = _exa_facts(exa)
    if not facts:
        st.caption(L("exa_none"))
        return
    for lk, val, src in facts:
        line = f"**{L(lk)}:** {val}"
        if src:
            line += f"  ([{L('exa_source')}]({src}))"
        st.markdown(line)


def _pipeline_card(lead: dict, store, camps: list[dict], context: str) -> None:
    lid = lead["id"]
    color = TIER_COLOR.get(lead.get("tier"), "#9ca3af")
    keys = leads_store.STATUSES
    labels = [L(f"status_{k}") for k in keys]
    with st.container(border=True):
        st.markdown(
            f"<span style='background:{color};color:#fff;border-radius:6px;padding:1px 8px;"
            f"font-weight:800'>{lead.get('tier') or '—'}</span> &nbsp;<b>{lead.get('name')}</b>"
            f" — {lead.get('title', '')} · {lead.get('company', '')}", unsafe_allow_html=True)
        if lead.get("reason"):
            st.caption(lead["reason"])

        cur = lead.get("status", "qualified")
        cur = cur if cur in keys else "qualified"
        new_label = st.selectbox(L("lead_status"), labels, index=keys.index(cur),
                                 key=f"st_{lid}")
        new_key = keys[labels.index(new_label)]
        if new_key != cur:
            store.update_fields(lid, {"status": new_key})
            st.rerun()

        ins = [(k, lead[k]) for k in _insight_keys(lead) if lead.get(k)]
        if ins:
            with st.expander(L("insights_expander")):
                for k, v in ins:
                    st.markdown(f"**{_signal_label(k)}:** {v}")

        # Actividad de LinkedIn (Fase 2) — solo sobre leads que aceptaron la conexión.
        if cur in _CONNECTED_STATUSES:
            act = lead.get("activity") or {}
            if isinstance(act, dict) and act.get("summary"):
                with st.expander(L("activity_label"), expanded=True):
                    st.caption(act["summary"])
            if st.button(L("fetch_activity"), key=f"act_{lid}"):
                src = ms_activity.get_source()
                lk = lead.get("linkedin") or ""
                if getattr(src, "mode", "sync") == "async":
                    # Clay: disparamos el pedido; el resultado vuelve por clay-webhook.
                    try:
                        sent = src.request_activity(lid, lk)
                    except Exception as exc:  # noqa: BLE001
                        sent = False
                        st.error(f"{exc}")
                    st.info(L("activity_requested") if sent else L("activity_none"))
                else:
                    with st.spinner(L("activity_spinner")):
                        got = src.fetch_activity(lk)
                    if got:
                        store.update_fields(lid, {"activity": got})
                        st.rerun()
                    else:
                        st.info(L("activity_none"))

        # Enrichment web con Exa (company + persona) — complementa a Clay (async fire→poll).
        exa = lead.get("exa") if isinstance(lead.get("exa"), dict) else None
        exa_status = exa.get("status") if exa else None
        exa_src = ms_exa.get_source()
        if getattr(exa_src, "configured", False):
            if exa_status == "completed":
                with st.expander(L("exa_label"), expanded=True):
                    _render_exa(exa)
            elif exa_status == "pending":
                st.caption(L("exa_pending"))
            elif exa_status == "failed":
                st.caption(L("exa_failed"))
            fire_label = L("exa_refresh") if exa_status == "completed" else L("exa_fetch")
            if st.button(fire_label, key=f"exafire_{lid}"):
                try:
                    rid = exa_src.request_enrichment(lead)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"{exc}")
                else:
                    if rid:
                        store.update_fields(lid, {"exa": {"run_id": rid, "status": "pending"}})
                        st.rerun()
                    else:
                        st.info(L("exa_no_anchor"))
            if exa_status == "pending" and st.button(L("exa_update"), key=f"exapoll_{lid}"):
                try:
                    got = exa_src.poll(exa.get("run_id"))
                except Exception as exc:  # noqa: BLE001
                    st.error(f"{exc}")
                else:
                    if got:
                        store.update_fields(lid, {"exa": got})
                        st.rerun()
                    else:
                        st.info(L("exa_still_running"))

        label = L("regen_message") if lead.get("message") else L("gen_message")
        if st.button(label, key=f"gen_{lid}", disabled=not HAS_CLAUDE):
            with st.spinner(L("gen_message_spinner")):
                m = msg_gen.generate_message(lead, value_prop=_value_prop_for(lead, camps),
                                             context=context, lang=_msg_lang())
            store.update_fields(lid, {"message": m, "status": "message_ready"})
            st.rerun()

        if lead.get("message"):
            edited = st.text_area(L("message_label"), value=lead["message"],
                                  key=f"msg_{lid}", height=140)
            if st.button(L("save_message"), key=f"savemsg_{lid}"):
                store.update_fields(lid, {"message": edited})
                st.success(L("message_saved"))
            st.caption(L("copy_hint"))
            st.code(edited, language=None)


def _board_card(lead: dict, store) -> None:
    """Tarjeta compacta del board: tier + nombre + empresa, mover de estado, abrir detalle."""
    lid = lead["id"]
    color = TIER_COLOR.get(lead.get("tier"), "#9ca3af")
    keys = leads_store.STATUSES
    labels = [L(f"status_{k}") for k in keys]
    cur = lead.get("status", "qualified")
    cur = cur if cur in keys else "qualified"
    selected = st.session_state.get("pipeline_selected") == lid
    with st.container(border=True):
        st.markdown(
            f"<span style='background:{color};color:#fff;border-radius:6px;padding:0 6px;"
            f"font-weight:800;font-size:0.8em'>{lead.get('tier') or '—'}</span> "
            f"<b>{lead.get('name') or '—'}</b>", unsafe_allow_html=True)
        sub = " · ".join(x for x in (lead.get("title"), lead.get("company")) if x)
        if sub:
            st.caption(sub)
        with st.popover(L("board_move"), use_container_width=True):
            new_label = st.radio(L("lead_status"), labels, index=keys.index(cur),
                                 key=f"mv_{lid}")
            new_key = keys[labels.index(new_label)]
            if new_key != cur:
                store.update_fields(lid, {"status": new_key})
                st.rerun()
        btn = "primary" if selected else "secondary"
        if st.button(L("board_open"), key=f"open_{lid}", use_container_width=True, type=btn):
            st.session_state["pipeline_selected"] = None if selected else lid
            st.rerun()


def _render_board(leads: list[dict], store) -> None:
    """Board tipo kanban: una columna por etapa del funnel + descartados aparte."""
    order = [k for k in leads_store.STATUSES if k != "discarded"]
    by_status: dict[str, list[dict]] = {k: [] for k in order}
    discarded: list[dict] = []
    for ld in leads:
        s = ld.get("status", "qualified")
        if s == "discarded":
            discarded.append(ld)
        else:
            by_status.get(s, by_status["qualified"]).append(ld)

    cols = st.columns(len(order))
    for col, s in zip(cols, order):
        with col:
            st.markdown(
                f"<div style='font-weight:800;font-size:0.82em;text-transform:uppercase;"
                f"letter-spacing:.03em'>{L(f'status_{s}')}</div>"
                f"<div style='color:#9ca3af;font-size:0.8em;margin-bottom:.4em'>"
                f"{len(by_status[s])}</div>", unsafe_allow_html=True)
            for ld in by_status[s]:
                _board_card(ld, store)

    if discarded:
        with st.expander(L("board_discarded", n=len(discarded))):
            for ld in discarded:
                _board_card(ld, store)


def render_pipeline() -> None:
    st.title(L("pipeline_title"))
    st.caption(L("pipeline_caption"))
    store = leads_store.get_store()
    camps = campaigns.list_campaigns()  # archivos de campaña (para la propuesta de valor del mensaje)
    # El filtro se arma con las campañas que REALMENTE tienen leads en el pipeline
    # (Supabase), no con los archivos de campaña — así aparecen aunque el archivo no exista.
    try:
        slug_by_name = {c["name"]: c["slug"] for c in store.list_lead_campaigns()}
    except Exception as exc:  # noqa: BLE001
        st.error(f"Error: {exc}")
        return

    options = [L("pipeline_all")] + list(slug_by_name)
    # Preselección al venir desde Métricas ("Abrir en Pipeline").
    pre = st.session_state.pop("pipeline_slug", None)
    idx = 0
    if pre:
        pre_name = next((n for n, s in slug_by_name.items() if s == pre), None)
        if pre_name in options:
            idx = options.index(pre_name)
    fcol, vcol, mcol = st.columns([2, 1, 1])
    camp_choice = fcol.selectbox(L("pipeline_campaign"), options, index=idx)
    slug = None if camp_choice == L("pipeline_all") else slug_by_name[camp_choice]
    view = vcol.radio(L("pipeline_view"), [L("pipeline_view_board"), L("pipeline_view_list")],
                      horizontal=True)
    is_board = view == L("pipeline_view_board")
    # Idioma del MENSAJE, independiente de la UI (default inglés: los prospectos suelen serlo).
    mlangs = {"English": "en", "Español": "es"}
    cur_ml = _msg_lang()
    ml_idx = list(mlangs.values()).index(cur_ml) if cur_ml in mlangs.values() else 0
    st.session_state["msg_lang"] = mlangs[mcol.selectbox(L("msg_lang_label"),
                                                          list(mlangs), index=ml_idx)]
    context = ms_context.load_context()

    keys = leads_store.STATUSES
    labels = {k: L(f"status_{k}") for k in keys}
    # El filtro por estado solo aplica a la Lista; el Board ya muestra todos los estados.
    picked_keys = None
    if not is_board:
        picked = st.multiselect(L("pipeline_status_filter"), [labels[k] for k in keys])
        picked_keys = [k for k in keys if labels[k] in picked] or None

    try:
        leads = store.list_leads(campaign_slug=slug, statuses=picked_keys)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Error: {exc}")
        return
    if not leads:
        st.info(L("pipeline_empty"))
        return
    st.caption(L("pipeline_count", n=len(leads)))

    if not is_board:
        for lead in leads:
            _pipeline_card(lead, store, camps, context)
        return

    # El board necesita ancho: ensanchamos el contenedor SOLO en esta vista
    # (inyectando el estilo únicamente acá; las demás vistas siguen centradas).
    st.markdown(
        "<style>section.main .block-container,"
        "div[data-testid='stMainBlockContainer']{max-width:1600px !important;}</style>",
        unsafe_allow_html=True)

    # Panel de detalle ARRIBA del board: al 'Abrir' un lead se ve de inmediato.
    sel_id = st.session_state.get("pipeline_selected")
    sel_lead = next((ld for ld in leads if ld["id"] == sel_id), None) if sel_id else None
    if sel_id and not sel_lead:
        # el seleccionado ya no está en el filtro actual (cambió la campaña) → limpiar.
        st.session_state.pop("pipeline_selected", None)
    if sel_lead:
        hcol, ccol = st.columns([4, 1])
        hcol.subheader(L("board_detail_title"))
        if ccol.button(L("board_close"), key="close_detail", use_container_width=True):
            st.session_state.pop("pipeline_selected", None)
            st.rerun()
        _pipeline_card(sel_lead, store, camps, context)
        st.divider()
    else:
        st.caption(L("board_detail_hint"))

    _render_board(leads, store)


# ==========================================================================
# Vista: Métricas (funnel por campaña)
# ==========================================================================
def render_metrics() -> None:
    st.title(L("metrics_title"))
    st.caption(L("metrics_caption"))
    store = leads_store.get_store()

    # HubSpot detrás del adapter: reuniones + oportunidades por campaña (o "—" sin token).
    hs = ms_hubspot.get_source()
    connected = getattr(hs, "configured", False)
    conv = None
    if connected:
        try:
            conv = hs.conversions()
        except Exception as exc:  # noqa: BLE001
            st.warning(f"HubSpot: {exc}")
            connected = False

    try:
        rows = leads_store.campaign_metrics(store, conversions=conv)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Error: {exc}")
        return
    if not rows:
        st.info(L("metrics_empty"))
        return

    table = []
    for r in rows:
        rate = f'{round(100 * r["accepted"] / r["connection_sent"])}%' if r["connection_sent"] else "—"
        table.append({
            L("m_campaign"): r["name"],
            L("m_leads"): r["leads"],
            L("m_sent"): r["connection_sent"],
            L("m_accepted"): r["accepted"],
            L("m_accept_rate"): rate,
            L("m_messages"): r["sent"],
            L("m_replies"): r["replied"],
            L("m_meetings"): r.get("meetings", 0) if connected else "—",
            L("m_opportunities"): r.get("opportunities", 0) if connected else "—",
        })
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption(L("m_hubspot_hint_ok") if connected else L("m_hubspot_hint"))

    # Entrar a una campaña en el Pipeline para el seguimiento lead por lead.
    by_name = {r["name"]: r["slug"] for r in rows}
    sel = st.selectbox(L("m_open_label"), list(by_name))
    if st.button(L("m_open_btn")):
        st.session_state["pipeline_slug"] = by_name[sel]
        st.session_state["view"] = "pipeline"
        st.rerun()


# ==========================================================================
# Vista: Contexto de Making Sense
# ==========================================================================
def render_context() -> None:
    st.title(L("context_title"))
    st.caption(L("context_caption"))
    try:
        saved = ms_context.has_saved_context()
        current = ms_context.load_context()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Error: {exc}")
        return
    if not saved:
        st.info(L("context_seeded"))
    txt = st.text_area(L("context_label"), value=current, height=480, key="ms_ctx")
    if st.button(L("save_context"), type="primary"):
        try:
            ms_context.save_context(txt)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error: {exc}")
            return
        st.success(L("context_saved"))


# ==========================================================================
# Router
# ==========================================================================
def _nav(view_key: str, label_key: str, current: str) -> None:
    """Botón de navegación; resalta (primary) el que corresponde a la vista activa."""
    if st.button(L(label_key), use_container_width=True,
                 type="primary" if current == view_key else "secondary"):
        st.session_state["view"] = view_key
        st.rerun()


with st.sidebar:
    _labels = list(i18n.LANGS.keys())
    _codes = list(i18n.LANGS.values())
    _sel = st.radio(L("lang_label"), _labels,
                    index=_codes.index(_lang()) if _lang() in _codes else 0,
                    horizontal=True)
    if i18n.LANGS[_sel] != _lang():
        st.session_state["lang"] = i18n.LANGS[_sel]
        st.rerun()
    ms_ui.logo("dark", width=160)
    current = st.session_state.get("view", "home")

    # Inicio (biblioteca de campañas) como punto de entrada.
    _nav("home", "nav_home", current)

    # Segmento 1 — flujo de trabajo: primero definir la campaña, después calificar.
    st.caption(L("nav_group_flow"))
    _nav("chat", "nav_chat", current)
    _nav("qualify", "nav_qualify", current)
    _nav("pipeline", "nav_pipeline", current)
    _nav("metrics", "nav_metrics", current)

    # Segmento 2 — configuración (zona más estática).
    st.divider()
    st.caption(L("nav_group_setup"))
    _nav("context", "nav_context", current)

    st.divider()
    st.caption(L("sidebar_footer"))

view = st.session_state["view"]
if view == "home":
    render_home()
elif view == "chat":
    render_chat()
elif view == "pipeline":
    render_pipeline()
elif view == "metrics":
    render_metrics()
elif view == "context":
    render_context()
else:
    render_qualify()

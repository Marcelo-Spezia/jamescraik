"""i18n mínimo para la UI: textos ES/EN + directiva de idioma para la IA.

Uso:  i18n.t("clave", lang, **kwargs)   →  string traducido (con .format si hay kwargs).
El idioma vive en st.session_state['lang'] ('es' | 'en'); default vía APP_DEFAULT_LANG.
"""

from __future__ import annotations

LANGS = {"Español": "es", "English": "en"}


def ai_directive(lang: str) -> str:
    """Instrucción para que el modelo responda en el idioma elegido."""
    return ("Respondé siempre en español." if lang == "es"
            else "Respond entirely in English, regardless of the input language.")


# clave → {es, en}. Los {placeholders} se resuelven con .format(**kwargs).
T: dict[str, dict[str, str]] = {
    # --- meta / auth / sidebar ---
    "page_title": {"es": "Calificador de leads", "en": "Lead Qualifier"},
    "app_title": {"es": "🎯 Calificador de leads", "en": "🎯 Lead Qualifier"},
    "auth_caption": {"es": "Ingresá la contraseña para continuar.",
                     "en": "Enter the password to continue."},
    "auth_password": {"es": "Contraseña", "en": "Password"},
    "auth_wrong": {"es": "Contraseña incorrecta.", "en": "Incorrect password."},
    "lang_label": {"es": "🌐 Idioma / Language", "en": "🌐 Language / Idioma"},
    "nav_home": {"es": "🏠 Inicio", "en": "🏠 Home"},
    "nav_qualify": {"es": "🎯 Calificar", "en": "🎯 Qualify"},
    "nav_chat": {"es": "🧭 Definir campaña", "en": "🧭 Define campaign"},
    "nav_context": {"es": "🏢 Contexto", "en": "🏢 Context"},
    "nav_group_flow": {"es": "FLUJO", "en": "WORKFLOW"},
    "nav_group_setup": {"es": "CONFIGURACIÓN", "en": "SETUP"},

    # --- home / biblioteca de campañas ---
    "home_title": {"es": "🏠 Inicio", "en": "🏠 Home"},
    "home_caption": {
        "es": "Tus campañas guardadas. Creá una nueva o abrí una para calificar tu lista.",
        "en": "Your saved campaigns. Create a new one or open one to qualify your list."},
    "home_new": {"es": "➕ Nueva campaña", "en": "➕ New campaign"},
    "home_empty": {"es": "Todavía no tenés campañas. Creá la primera con **➕ Nueva campaña**.",
                   "en": "No campaigns yet. Create your first one with **➕ New campaign**."},
    "home_count": {"es": "{n} campaña(s)", "en": "{n} campaign(s)"},
    "no_vp": {"es": "(sin propuesta de valor)", "en": "(no value proposition)"},
    "card_meta": {"es": "{f} filtros · {s} señales", "en": "{f} filters · {s} signals"},
    "card_updated": {"es": "Editada: {date}", "en": "Updated: {date}"},
    "card_use": {"es": "🎯 Usar", "en": "🎯 Use"},
    "card_edit_help": {"es": "Editar", "en": "Edit"},
    "card_dup_help": {"es": "Duplicar", "en": "Duplicate"},
    "card_del_help": {"es": "Eliminar", "en": "Delete"},
    "copy_suffix": {"es": "(copia)", "en": "(copy)"},
    "confirm_delete": {"es": "¿Eliminar «{name}»?", "en": "Delete «{name}»?"},
    "confirm_yes": {"es": "Sí, eliminar", "en": "Yes, delete"},
    "confirm_cancel": {"es": "Cancelar", "en": "Cancel"},
    "sidebar_footer": {"es": "POC LeadGen · Making Sense", "en": "LeadGen POC · Making Sense"},
    "missing_key": {"es": "Falta ANTHROPIC_API_KEY.", "en": "ANTHROPIC_API_KEY is missing."},

    # --- chat view ---
    "chat_title": {"es": "🧭 Definir campaña", "en": "🧭 Define campaign"},
    "chat_caption": {
        "es": "Charlá con la IA sobre tu campaña. Te ayuda a iterar los filtros de "
              "Sales Navigator, la rúbrica de calificación y la propuesta de valor.",
        "en": "Chat with the AI about your campaign. It helps you iterate the Sales "
              "Navigator filters, the qualification rubric and the value proposition."},
    "chat_restart": {"es": "🗑️ Empezar de nuevo", "en": "🗑️ Start over"},
    "chat_input_ph": {"es": "Contale sobre tu campaña…", "en": "Tell it about your campaign…"},
    "chat_thinking": {"es": "Pensando…", "en": "Thinking…"},
    "chat_generate": {"es": "✨ Generar campaña desde la charla",
                      "en": "✨ Generate campaign from the chat"},
    "chat_building": {"es": "Armando la campaña…", "en": "Building the campaign…"},
    "gen_error": {"es": "No se pudo generar:\n\n{err}", "en": "Could not generate:\n\n{err}"},
    "draft_header": {"es": "Campaña propuesta — revisá y guardá",
                     "en": "Proposed campaign — review and save"},
    "f_name": {"es": "Nombre", "en": "Name"},
    "f_filters": {"es": "Filtros para Sales Navigator (uno por línea)",
                  "en": "Sales Navigator filters (one per line)"},
    "f_rubric_abcd": {"es": "Rúbrica (A/B/C/D)", "en": "Rubric (A/B/C/D)"},
    "f_value_prop": {"es": "Propuesta de valor", "en": "Value proposition"},
    "signals_hint": {
        "es": "✨ Señales de enrichment que Claude sugiere para esta campaña "
              "(una por línea — `etiqueta: qué averiguar`). Editá libremente.",
        "en": "✨ Enrichment signals Claude suggests for this campaign "
              "(one per line — `label: what to find out`). Edit freely."},
    "f_signals": {"es": "Señales de enrichment", "en": "Enrichment signals"},
    "save_campaign": {"es": "💾 Guardar campaña", "en": "💾 Save campaign"},
    "campaign_saved": {"es": "Campaña guardada: **{name}**. Ya podés usarla en 🎯 Calificar.",
                       "en": "Campaign saved: **{name}**. You can now use it in 🎯 Qualify."},

    # --- qualify view ---
    "qualify_title": {"es": "🎯 Calificar leads", "en": "🎯 Qualify leads"},
    "qualify_caption": {
        "es": "Subí tu lista, elegí una campaña (o escribí la rúbrica), y la IA califica "
              "en tiers A/B/C/D con el por qué. Después filtrás y exportás.",
        "en": "Upload your list, pick a campaign (or write the rubric), and the AI qualifies "
              "into A/B/C/D tiers with the reasoning. Then filter and export."},
    "sec_campaign": {"es": "1. Campaña", "en": "1. Campaign"},
    "manual_option": {"es": "(escribir manualmente)", "en": "(write manually)"},
    "use_saved": {"es": "Usar campaña guardada", "en": "Use a saved campaign"},
    "filters_suggested": {"es": "**Filtros sugeridos para Sales Navigator:**",
                          "en": "**Suggested Sales Navigator filters:**"},
    "tip_campaign": {"es": "Tip: podés definir campañas con el chat en 🧭 Definir campaña.",
                     "en": "Tip: you can define campaigns with the chat in 🧭 Define campaign."},
    "campaign_name": {"es": "Nombre de la campaña", "en": "Campaign name"},
    "campaign_name_ph": {"es": "Ej: CFOs fintech Argentina", "en": "e.g. Fintech CFOs Argentina"},
    "rubric_label": {"es": "Rúbrica — qué hace a un lead A / B / C / D",
                     "en": "Rubric — what makes a lead A / B / C / D"},
    "value_prop_label": {"es": "Propuesta de valor (para evaluar el fit)",
                         "en": "Value proposition (to assess fit)"},
    "suggest_btn": {"es": "💡 Sugerí mejoras a esta campaña",
                    "en": "💡 Suggest improvements to this campaign"},
    "suggest_spinner": {"es": "Analizando la campaña contra el contexto de Making Sense…",
                        "en": "Analyzing the campaign against Making Sense context…"},
    "suggest_expander": {"es": "💡 Recomendaciones para mejorar la campaña",
                         "en": "💡 Recommendations to improve the campaign"},
    "hide": {"es": "Ocultar", "en": "Hide"},
    "sec_list": {"es": "2. Tu lista", "en": "2. Your list"},
    "uploader_label": {"es": "Subí un CSV (Sales Navigator, Apollo, Clay, export propio…)",
                       "en": "Upload a CSV (Sales Navigator, Apollo, Clay, your own export…)"},
    "csv_read_error": {
        "es": "No pude leer columnas del CSV. ¿Está separado por comas y con encabezados?",
        "en": "Couldn't read columns from the CSV. Is it comma-separated with headers?"},
    "mapping_expander": {"es": "🔗 Columnas detectadas — revisá y corregí",
                         "en": "🔗 Detected columns — review and fix"},
    "mapping_caption": {
        "es": "Asigná cada campo a una columna de tu CSV. Lo que quede en «(ninguno)» se "
              "ignora. Sirve para cualquier formato de lista.",
        "en": "Map each field to a column of your CSV. Anything left as «(none)» is ignored. "
              "Works with any list format."},
    "none_option": {"es": "(ninguno)", "en": "(none)"},
    "warn_map": {"es": "Asigná al menos **Empresa** o **Nombre** para poder calificar bien.",
                 "en": "Map at least **Company** or **Name** to qualify properly."},
    "leads_read": {"es": "✅ {n} leads leídos.", "en": "✅ {n} leads read."},
    "see_first5": {"es": "Ver los primeros 5", "en": "See the first 5"},
    "sec_qualify": {"es": "3. Calificar", "en": "3. Qualify"},
    "how_many": {"es": "¿Cuántos calificar?", "en": "How many to qualify?"},
    "upload_to_qualify": {"es": "Subí un CSV arriba para calificar.",
                          "en": "Upload a CSV above to qualify."},
    "qualify_cost": {
        "es": "⚠️ Se califican **{n}** leads (en tandas de ~10 por llamada a Claude). "
              "Listas grandes tardan más y cuestan más.",
        "en": "⚠️ Qualifies **{n}** leads (in batches of ~10 per Claude call). "
              "Large lists take longer and cost more."},
    "qualify_btn": {"es": "🎯 Calificar lista", "en": "🎯 Qualify list"},
    "qualify_spinner": {"es": "Calificando {n} leads…", "en": "Qualifying {n} leads…"},
    "qualify_error": {"es": "No se pudo calificar:\n\n{err}", "en": "Could not qualify:\n\n{err}"},
    "sec_results": {"es": "4. Resultados", "en": "4. Results"},
    "show_tiers": {"es": "Mostrar tiers", "en": "Show tiers"},
    "download_csv": {"es": "⬇️ Descargar CSV ({n} leads)", "en": "⬇️ Download CSV ({n} leads)"},
    "file_suffix": {"es": "calificados", "en": "qualified"},
    "insights_expander": {"es": "✨ Insights para el mensaje", "en": "✨ Insights for the message"},
    "sec_enrich": {"es": "5. Enriquecer (opcional)", "en": "5. Enrich (optional)"},
    "enrich_caption": {
        "es": "Suma señales de **negocio** para el mensaje. Las señales varían por campaña — "
              "elegí del catálogo y/o pedí a medida. Enriquece 1 empresa única = 1 crédito Apollo.",
        "en": "Adds **business** signals for the message. Signals vary per campaign — pick from "
              "the catalog and/or request custom ones. Enriches 1 unique company = 1 Apollo credit."},
    "catalog_signals": {"es": "Señales del catálogo", "en": "Catalog signals"},
    "custom_signals": {"es": "Señales a medida (una por línea — `etiqueta: qué averiguar`)",
                       "en": "Custom signals (one per line — `label: what to find out`)"},
    "core_always": {"es": "Siempre se agregan: **Match propuesta de valor** y **Hook**. ",
                    "en": "Always added: **Value proposition match** and **Hook**. "},
    "signals_chosen": {"es": "Señales elegidas: {list}.", "en": "Chosen signals: {list}."},
    "signals_none": {"es": "Sin señales extra (solo el núcleo).",
                     "en": "No extra signals (core only)."},
    "which_tiers": {"es": "¿Qué tiers enriquecer?", "en": "Which tiers to enrich?"},
    "enrich_cost": {
        "es": "⚠️ Enriquece **{n}** leads (~{e} empresas únicas → {e} créditos de Apollo).",
        "en": "⚠️ Enriches **{n}** leads (~{e} unique companies → {e} Apollo credits)."},
    "enrich_btn": {"es": "✨ Enriquecer seleccionados", "en": "✨ Enrich selected"},
    "enrich_spinner": {"es": "Enriqueciendo {n} leads…", "en": "Enriching {n} leads…"},
    "enrich_error": {"es": "No se pudo enriquecer:\n\n{err}",
                     "en": "Could not enrich:\n\n{err}"},

    # --- context view ---
    "context_title": {"es": "🏢 Contexto de Making Sense", "en": "🏢 Making Sense context"},
    "context_caption": {
        "es": "Mantené acá el contexto vivo de Making Sense: servicios, propuesta de valor, "
              "diferenciadores, casos de éxito, aprendizajes y verticales foco. El agente lo "
              "usa para groundear el chat de campaña y el match de propuesta de valor.",
        "en": "Keep Making Sense's living context here: services, value proposition, "
              "differentiators, case studies, learnings and focus verticals. The agent uses "
              "it to ground the campaign chat and the value-proposition match."},
    "context_seeded": {"es": "Sembrado desde tu doc del proyecto. Editá y guardá para hacerlo tuyo.",
                       "en": "Seeded from your project doc. Edit and save to make it yours."},
    "context_label": {"es": "Contexto (markdown)", "en": "Context (markdown)"},
    "save_context": {"es": "💾 Guardar contexto", "en": "💾 Save context"},
    "context_saved": {"es": "Contexto guardado. El agente ya lo usa en el chat y en la calificación.",
                      "en": "Context saved. The agent already uses it in the chat and qualification."},

    # --- defaults (rúbrica / propuesta de valor) ---
    "default_vp": {
        "es": "Making Sense desarrolla software a medida y producto digital para empresas "
              "tech-enabled.",
        "en": "Making Sense builds custom software and digital products for tech-enabled "
              "companies."},
    "default_rubric": {
        "es": ("Describí a quién buscás y qué hace a un lead A / B / C / D. Ejemplo:\n"
               "- A: CFO / Director Financiero de fintech o empresa de software / tech-enabled, "
               "mid-market (50-2000), AR/LATAM.\n"
               "- B: Finanzas en una empresa de servicios profesionales con algo de tecnología.\n"
               "- C: Empresa tradicional / no-tech, o tamaño / geografía dudosos.\n"
               "- D: No fit — rol equivocado, gobierno / educación, otro rubro, o ruido."),
        "en": ("Describe who you're looking for and what makes a lead A / B / C / D. Example:\n"
               "- A: CFO / Finance leader at a fintech or software / tech-enabled company, "
               "mid-market (50-2000), NA/LATAM.\n"
               "- B: Finance at a professional-services company with some technology.\n"
               "- C: Traditional / non-tech company, or dubious size / geography.\n"
               "- D: No fit — wrong role, government / education, other industry, or noise.")},

    # --- chat intro (primer mensaje del asistente) ---
    "chat_intro": {
        "es": ("¡Hola! Te ayudo a definir la campaña. Contame:\n\n"
               "- ¿Qué estás ofreciendo y a quién querés llegar?\n"
               "- ¿Qué hace que un lead sea ideal vs. uno que no te sirve?\n\n"
               "Con eso vamos puliendo juntos los **filtros para Sales Navigator** (los más "
               "excluyentes) y la **rúbrica de calificación** (qué hace a un lead A/B/C/D)."),
        "en": ("Hi! I'll help you define the campaign. Tell me:\n\n"
               "- What are you offering and who do you want to reach?\n"
               "- What makes a lead ideal vs. one that isn't a fit?\n\n"
               "With that we'll refine together the **Sales Navigator filters** (the most "
               "exclusive ones) and the **qualification rubric** (what makes a lead A/B/C/D).")},

    # --- etiquetas de campos del mapeo de CSV ---
    "field_name": {"es": "Nombre", "en": "Name"},
    "field_first_name": {"es": "Nombre (pila)", "en": "First name"},
    "field_last_name": {"es": "Apellido", "en": "Last name"},
    "field_title": {"es": "Título / Cargo", "en": "Title / Role"},
    "field_company": {"es": "Empresa", "en": "Company"},
    "field_domain": {"es": "Dominio / Web", "en": "Domain / Website"},
    "field_size": {"es": "Tamaño / Empleados", "en": "Size / Employees"},
    "field_industry": {"es": "Industria", "en": "Industry"},
    "field_location": {"es": "Ubicación", "en": "Location"},
    "field_email": {"es": "Email", "en": "Email"},
    "field_linkedin": {"es": "LinkedIn", "en": "LinkedIn"},

    # --- etiquetas de señales de enrichment (display) ---
    "signal_funding": {"es": "Inversión / funding", "en": "Funding / investment"},
    "signal_growth": {"es": "Crecimiento", "en": "Growth"},
    "signal_maturity": {"es": "Madurez / legacy", "en": "Tech maturity / legacy"},
    "signal_geo_expansion": {"es": "Expansión geográfica", "en": "Geographic expansion"},
    "signal_platform": {"es": "Stack / plataforma", "en": "Stack / platform"},
    "signal_regulatory": {"es": "Presión regulatoria", "en": "Regulatory pressure"},
    "signal_hiring_tech": {"es": "Contrataciones en tech", "en": "Tech hiring"},
    "signal_role_focus": {"es": "Foco del rol", "en": "Role focus"},
    "signal_value_prop_match": {"es": "Match propuesta de valor", "en": "Value proposition match"},
    "signal_hook": {"es": "Hook / ángulo", "en": "Hook / angle"},
}


def t(key: str, lang: str = "es", **kwargs) -> str:
    entry = T.get(key, {})
    s = entry.get(lang) or entry.get("es") or key
    return s.format(**kwargs) if kwargs else s

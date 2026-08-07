# James Craik — Contexto de la app (LeadGen tool)

> Doc de contexto portable, generado 2026-08-05. Groundeado en el código actual
> (rama `main`). Pensado para retomar el análisis en otra sesión. **No contiene
> secretos** — solo nombres de variables de entorno.

---

## 1. Qué es

Herramienta interna de **Lead Generation** de la vertical LeadGen de Making Sense.
Evolucionó del "ICP Engine" (motor de scoring de ICP) a un flujo **end-to-end de
outreach**:

**Definir campaña (chat) → Calificar lista (CSV → tiers A/B/C/D) → Enriquecer →
Guardar en Pipeline → Outreach (mensaje + estados) → Métricas (funnel + HubSpot).**

Making Sense vende **modernización / estado de negocio** (no tech stack). El tech
stack es solo evidencia/input para inferir madurez, legacy, crecimiento, inversión —
nunca un insight que se muestre. Ver §7 (enrichment).

---

## 2. Principios de arquitectura (no negociables)

1. **Agnóstico a herramientas.** Toda fuente externa (data, enrichment, CRM, LLM,
   actividad) vive detrás de una **interfaz adapter**. El motor opera sobre el modelo
   canónico. Cada adapter tiene una implementación real + un stub in-memory para
   tests/dev sin credenciales. `get_source()`/`get_store()` eligen según env.
2. **ICP/campaña como dato, versionable.** Las campañas son archivos (JSON) externos
   al motor.
3. **Explicable + determinístico donde se puede; LLM solo para lo difuso.** Cada score
   trae su "por qué".

---

## 3. Stack

- **Python 3.12**, venv en `.venv`. UI en **Streamlit** (pin 1.58). pytest + ruff
  (line-length 100).
- **Anthropic Claude API** (structured output vía `output_config`, prompt caching).
- **Supabase** (Postgres) como store durable multi-usuario (`supabase-py` 2.31.0).
- **Supabase Edge Functions** (Deno/TypeScript) para webhooks entrantes.
- HTTP: `httpx` (ya presente; se usa para HubSpot y Clay POST).
- Correr local: `.venv/bin/streamlit run ui/app.py`
- Entrypoint: [ui/app.py](ui/app.py). App vieja del ICP Engine en `ui/app_legacy.py` (legado).

---

## 4. Vistas de la app (`ui/app.py`)

Navegación: **Inicio** (standalone) · grupo **FLUJO** (Definir campaña → Calificar →
Pipeline → Métricas) · grupo **CONFIGURACIÓN** (Contexto). Selector de idioma ES/EN.
Candado de contraseña opcional (`_require_auth`, usa `APP_PASSWORD`).

| Vista | Función | Qué hace |
|---|---|---|
| Inicio | `render_home` | Biblioteca de campañas guardadas |
| Definir campaña | `render_chat` | Chat con Claude arma la campaña (filtros Sales Nav + rúbrica + propuesta de valor + señales de enrichment) |
| Calificar | `render_qualify` | Sube CSV → mapea columnas → califica en tiers A/B/C/D con "por qué" → enriquece A/B → export CSV → "Guardar en pipeline" |
| Pipeline | `render_pipeline` | **Board (kanban) / Lista**. Board = columna por estado; tarjeta compacta; "Abrir" → panel de detalle (`_pipeline_card`) con estado, insights, actividad LinkedIn, generar/editar/copiar mensaje |
| Métricas | `render_metrics` | Funnel por campaña + reuniones/oportunidades de HubSpot |
| Contexto | `render_context` | Edita la base de conocimiento de Making Sense |

---

## 5. Modelo de datos

### Tabla `leads` (Supabase)
Columnas: `id`, `campaign_slug`, `campaign_name`, `name`, `title`, `company`, `domain`,
`size`, `industry`, `location`, `email`, `linkedin_url`, `tier`, `reason`,
`enrichment` (jsonb), `message`, `status`, `notes`, `activity` (jsonb), `created_at`,
`updated_at`. Índice único parcial en `(campaign_slug, linkedin_url)`. RLS on
(service_role bypassa).

- `norm_linkedin(url)` normaliza la URL (minúsculas, sin protocolo/www/query/slash
  final) → `linkedin.com/in/<slug>`. **Espejado en TS** en los dos webhooks.
- `lead_to_row` / `row_to_lead`: separan columnas base del jsonb `enrichment` (insights)
  y aplanan al leer.

### Estados del pipeline (`leads_store.STATUSES`)
```
qualified → connection_sent → accepted → message_ready → sent → replied
                                                                    (+ discarded, fuera del funnel)
```
- `_FUNNEL_ORDER` = los 6 sin `discarded`. `funnel_counts` cuenta "llegó AL MENOS a esta
  etapa" (acumulativo). `discarded` no cuenta.
- `_CONNECTED_STATUSES` = {accepted, message_ready, sent, replied} → solo estos muestran
  el botón "Traer actividad".

### Campañas (archivos)
`campaigns/*.json` (via `ui/campaigns.py`). Contienen filtros Sales Nav, rúbrica,
propuesta de valor, señales de enrichment. Se versionan en git. **Ojo: en Streamlit
Cloud el disco es efímero → los archivos de campaña NO persisten entre redeploys; los
leads sí (Supabase).**

---

## 6. Módulos (`ui/`)

| Archivo | Rol |
|---|---|
| `app.py` | Entrypoint Streamlit, todas las vistas, auth, nav, i18n shortcut `L()` |
| `chat_builder.py` | Chat multi-turno que arma la campaña (`chat_reply`, `extract_campaign`, `suggest_improvements`) |
| `campaigns.py` | Persistencia de campañas (JSON) |
| `qualify.py` | Lee cualquier CSV (`read_csv`, `detect_mapping`, `leads_from_rows`), califica en lote (`qualify_batch`), export (`leads_to_csv`) |
| `enrich.py` | Enrichment de señales de NEGOCIO (catálogo configurable), en lote |
| `message.py` | `generate_message` — borrador de LinkedIn post-conexión (usa actividad como hook) |
| `activity.py` | Adapter de actividad LinkedIn (Stub / Clay async) |
| `hubspot.py` | Adapter de HubSpot (reuniones + oportunidades) |
| `leads_store.py` | Store de leads (Supabase / InMemory) + funnel + métricas |
| `context.py` | Base de conocimiento de Making Sense (load/save markdown) |
| `i18n.py` | Diccionario ES/EN (`T`, `t()`, `ai_directive`) |
| `ms_ui.py` | Making Sense Design System (theme, logos, componentes) |
| `ai_assist.py`, `leadgen.py`, `icp_io.py`, `icp_translate.py`, `store.py` | Legado del ICP Engine (editor de ICP, Apollo leadgen, runs) |

---

## 7. Enrichment (dos flujos DISTINTOS — no confundir)

### A) Señales de negocio (tiers A/B) — corre DENTRO de la app
- `ui/enrich.py`, disparado desde **Calificar → "5. Enriquecer"**, en lote.
- Usa **Apollo** (dato duro: funding/revenue) + **Claude** (inferencias).
- Catálogo `SIGNAL_CATALOG` (funding, growth, maturity, geo_expansion, platform,
  regulatory, hiring_tech, role_focus) + `CORE_SIGNALS` (value_prop_match, hook =
  SIEMPRE). Configurable por campaña (multiselect + texto libre); Claude las propone
  en el chat. Schema y prompt **dinámicos** según las señales elegidas.
- **NO muestra tech stack como insight** (solo lo usa como evidencia para inferir).

### B) Actividad de LinkedIn (posteos) — corre EN CLAY, no en la app
- Restricción: LinkedIn no tiene API pública; scraping va contra ToS → proveedor
  compatible (**Clay**) detrás de `ui/activity.py`.
- **Se dispara desde Pipeline → panel de detalle del lead → botón "Traer actividad de
  LinkedIn"** ([ui/app.py:492](ui/app.py#L492)). Manual, por lead, solo si el estado
  está en `_CONNECTED_STATUSES`.
- Flujo async: app hace POST `{lead_id, linkedin_url}` a `CLAY_WEBHOOK_URL` →
  **Clay ejecuta el enrichment de cada contacto** (Find Recent Posts + resumen IA) →
  POST de vuelta a la Edge Function `clay-webhook` → escribe `leads.activity`.
  **No es instantáneo** (llega por webhook).

---

## 8. Integraciones externas (adapters) — dónde corre cada una

| Fuente | Adapter | Corre en | Config (env) | Estado |
|---|---|---|---|---|
| Claude (LLM) | directo en cada módulo | app | `ANTHROPIC_API_KEY` | ✅ |
| Apollo (data/enrichment) | `leadgen.py` / `enrich.py` | app | `APOLLO_API_KEY` | ✅ |
| Supabase (store) | `SupabaseLeadStore` | app (cliente) | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | ✅ |
| Clay (actividad LinkedIn) | `ClayActivitySource` | **Clay** (async) | `CLAY_WEBHOOK_URL` | ✅ (tabla Clay armada) |
| Expandi (LinkedIn automation) | Edge Function `expandi-webhook` | **Supabase** | `EXPANDI_WEBHOOK_SECRET` | ✅ |
| HubSpot (reuniones/oportunidades) | `HubSpotSource` | app (REST API) | `HUBSPOT_TOKEN` | ✅ |

### Webhooks (Supabase Edge Functions, Deno/TS)
- **`expandi-webhook`**: recibe eventos de Expandi (`?status=...&token=...`), matchea por
  LinkedIn URL en cualquier parte del payload, avanza el estado del lead. **Solo avanza**
  (nunca retrocede). Eventos configurados: Connection Request Sent → `connection_sent`,
  Accepted → `accepted`, Message Sent → `sent`, Reply → `replied`.
- **`clay-webhook`**: recibe `{lead_id, summary?, posts?}` de Clay, escribe `leads.activity`.
- Deploy vía dashboard (Via Editor, `--no-verify-jwt`); los secrets NO se actualizan por
  git push → hay que re-pegarlos + redeploy.

### HubSpot — lógica de atribución (importante)
- **La campaña vive del lado NUESTRO (Supabase `campaign_slug`), no en HubSpot.**
- `HubSpotSource.conversions()` trae SOLO los contactos convertidos (Search API de
  contactos, filterGroups en OR: `engagements_last_meeting_booked` HAS_PROPERTY **o**
  `num_associated_deals` > 0, ambos con `exp_contact_profile_url`).
- **Match por LinkedIn URL** (`exp_contact_profile_url` / `hs_linkedin_url`, normalizada
  con `norm_linkedin`), fallback **email**. El join HubSpot↔nosotros es la URL de LinkedIn.
- **Reunión** = `engagements_last_meeting_booked` seteado. **Oportunidad** =
  `num_associated_deals` > 0 (pipeline único "Opportunities Pipeline").
- `campaign_metrics(store, conversions=)` cruza los leads de cada campaña contra el mapa.
- Límites: un contacto sin LinkedIn/email no matchea; misma persona en 2 campañas cuenta
  en las 2; reuniones fuera de campaña trackeada no se atribuyen.
- Alternativa no implementada: atribuir por la campaña de Expandi
  (`exp_contact_campaign_member_id`) en vez de por LinkedIn URL.

---

## 9. Variables tuneables (para analizar)

### Env vars
| Variable | Uso | Default / nota |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude | requerida para todo el LLM |
| `APOLLO_API_KEY` | Apollo (enrichment dato duro) | — |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | store durable | sin ellas → InMemory (no persiste) |
| `CLAY_WEBHOOK_URL` | actividad LinkedIn | sin ella → stub (muestra "sin proveedor") |
| `HUBSPOT_TOKEN` | métricas HubSpot | sin él → "—" en Métricas |
| `APP_PASSWORD` | candado de la app | sin él → dev local abierto |
| `APP_DEFAULT_LANG` | idioma default | `es` \| `en` |
| `ICP_QUALIFY_MODEL` | modelo de calificación | `claude-haiku-4-5` (~5× más barato) |
| `ICP_JUDGE_MODEL` | modelo del judge (ICP legado) | `claude-opus-4-8` |
| `ICP_QUALIFY_BATCH` | leads por llamada al calificar | default 10 |
| `ICP_ENRICH_BATCH` | leads por llamada al enriquecer | default 5 |
| `ICP_ACTIVITY_DEMO` | `=1` muestra actividad de ejemplo | dev/demo |

> **Local**: van en `.env` (gitignored). **Deploy (Streamlit Cloud)**: `.env` NO se sube
> → hay que cargarlas en **Settings → Secrets** (formato TOML) y **Reboot**. Las env se
> leen al arrancar el proceso → tras cambiar `.env` local hay que **reiniciar** el server.

### Modelos LLM
- Calificación → **Haiku 4.5** (`claude-haiku-4-5`) por costo/volumen.
- Enrichment / mensaje / chat → **Opus 4.8** (`claude-opus-4-8`).

### Otras constantes de interés (código)
- `TIER_COLOR` (app.py): A verde / B azul / C ámbar / D gris.
- `leads_store.STATUSES` / `_FUNNEL_ORDER` / `_RANK`: definición del funnel.
- `enrich.SIGNAL_CATALOG` / `CORE_SIGNALS`: catálogo de señales de enrichment.
- Board: CSS `max-width:1600px` inyectado SOLO en la vista board (el resto es
  `layout="centered"`).

---

## 10. i18n y Design System
- **Bilingüe ES/EN**: `ui/i18n.py` (`T` dict clave→{es,en}, `t(key,lang,**kw)`). Atajo
  `L()` en app.py. La IA responde en el idioma elegido (se propaga `lang` a los `_system`).
  Sin emoji en copy; sentence case.
- **Making Sense Design System**: `ui/ms_ui.py` + `ui/streamlit_styles.css` (Red Hat
  Display, navy, gradiente, botones pill, logos SVG). Gotcha histórico: un `</style>` en
  un comentario del CSS rompía la pantalla → `apply_theme` lo strippea.

---

## 11. Tests
~182 tests (pytest), ruff limpio. `pythonpath = ["src", "ui"]`. Adapters con stubs
in-memory → todo el flujo se testea sin credenciales. Tests clave: `test_leads_store`,
`test_hubspot`, `test_qualify`, `test_enrich`, `test_activity`, `test_i18n`, `test_auth`.

---

## 12. Deploy
- Repo GitHub `Marcelo-Spezia/jamescraik`. Desplegada en **Streamlit Community Cloud**.
- Candado por contraseña (`APP_PASSWORD`) + allowlist por email de Streamlit (la app
  gasta créditos → no dejar pública).
- Disco efímero → campañas (archivos) no persisten entre redeploys; leads sí (Supabase).

---

## 13. Pendientes / abiertos
- **Rotar `HUBSPOT_TOKEN`** (se pegó en un chat) + cargarlo en Secrets de Streamlit.
- Cargar `CLAY_WEBHOOK_URL` (y confirmar Supabase/Anthropic) en Secrets de Streamlit
  para que actividad + pipeline anden en el deploy.
- (Sugerido) rotar la `SUPABASE_SERVICE_KEY` (se pegó en un chat).
- Backlog: disparo de actividad en lote / auto al pasar a `accepted`; variantes de
  mensaje; paralelizar calificación de listas grandes; loop de fit-rate (auto-nutrir el
  contexto desde feedback de campañas); atribución HubSpot por campaña de Expandi.
- Legado ICP Engine (`app_legacy.py`, `leadgen.py`, `icp_*`, `store.py`, `docs/icp-engine-spec.md`)
  sigue en el repo pero fuera del flujo actual.

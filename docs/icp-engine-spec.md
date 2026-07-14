# ICP Engine — Spec técnico (POC · E1)

> Fuente de verdad del diseño del motor. Última actualización: 2026-06-18.
> Estado: spec para handoff a desarrollo (Claude Code). Tool-agnostic.
> Documento vivo — se versiona junto al código.

---

## 1. Propósito y alcance

El **ICP Engine** es el artefacto que permite **representar cualquier ICP, versionarlo, y calificar cuentas/contactos contra él** produciendo un fit-score explicable. No es "un ICP": es el motor que aplica el ICP que se le inyecte.

Distinción que gobierna todo el diseño:

- **ICP-como-dato** (Capa A): un perfil concreto. Es contenido, versionable, hay muchos. Vive como archivo YAML.
- **ICP Engine** (Capa B): el schema + la lógica que lee *cualquier* ICP válido y puntúa contra él. Es código estable.

**Alcance del POC (este spec):** las tres piezas que atacan la raíz del problema de calidad —
1. **ICP Registry** — almacén versionable de definiciones de ICP.
2. **Scoring Engine** — califica cuenta + contacto contra una versión de ICP.
3. **Feedback loop** — sales marca fit/no-fit; alimenta el refinamiento del ICP.

Ingestion y enrichment entran como **tajadas finas**: lo mínimo para meter datos reales y probar el scoring. El armado automático de listas (E2), outreach (E4), qualification/handoff (E3) y dashboard (E5) están **fuera de alcance** (ver §13).

**Métrica del POC:** ICP-fit rate (ver §11).

---

## 2. Principios de diseño → implicancias técnicas

1. **Agnóstico a herramientas.** Toda fuente externa (data, enrichment, CRM, output) se accede detrás de una **interfaz adapter** (§12). El motor no importa SDKs de proveedores; opera sobre el modelo canónico (§4). Cambiar de proveedor = escribir un adapter, no re-arquitecturar.
2. **ICP vivo y versionable.** El ICP es dato externo al motor, en YAML, con **semver y changelog** (§9). El motor nunca hardcodea criterios. Soporta multi-ICP.
3. **Ágil y ligero.** El scoring es **explicable por construcción** (cada score trae su "por qué") para validar con sales antes de invertir en build pesado. Determinístico donde se puede; LLM solo donde el criterio es difuso.

---

## 3. Arquitectura (resumen)

```
                 ┌─────────────────────────┐
                 │  ICP Registry (YAML)     │  ← versionable, multi-ICP
                 │  v1, v2, …               │
                 └────────────┬─────────────┘
                              │ ICP activo (versión)
                              ▼
  entidad cruda ─► [ingestion] ─► [enrichment] ─► [SCORING ENGINE] ─► resultado
   (fuente ext.)    normaliza      completa        fit-score +          (score + tier +
                    a canónico     atributos       por qué              knockouts + por qué)
                                                        ▲
                                                        │ refina / nueva versión
                                   [feedback de sales: fit / no-fit]
```

Componentes detallados en `solucion_leadgen_end_to_end` (diagrama macro) y en el diagrama del ICP Engine. Este spec define los **contratos** entre ellos.

---

## 4. Modelo de datos canónico

Representación interna **independiente de cualquier herramienta**. Todo adapter de ingestion normaliza a esto. Campos `null` permitidos (gap a resolver por enrichment).

### 4.1 `Account` (empresa)

| Campo | Tipo | Notas |
|---|---|---|
| `account_id` | string | ID canónico interno (estable entre fuentes). |
| `name` | string | Razón social / nombre comercial. |
| `domain` | string | Dominio web. Clave de dedup primaria. |
| `industry` | string | Vertical normalizada (taxonomía propia, ver §4.3). |
| `employee_count` | int | Headcount. |
| `revenue_usd` | int | Revenue anual estimado (USD). |
| `country` | string | ISO-3166. |
| `region` | string | ej. NA, LATAM, EMEA. |
| `founded_year` | int | |
| `funding_stage` | enum | seed/series_a/series_b/growth/enterprise/bootstrapped/public/unknown. |
| `tech_stack` | string[] | Tecnologías detectadas (tecnográfico). |
| `intent_signals` | Signal[] | Señales de intent observadas (ver §4.4). |
| `source` | string | Adapter de origen. |
| `enriched_fields` | string[] | Qué campos completó enrichment (trazabilidad). |
| `raw` | object | Payload original de la fuente (auditoría). |

### 4.2 `Contact` (persona)

| Campo | Tipo | Notas |
|---|---|---|
| `contact_id` | string | ID canónico interno. |
| `account_id` | string | FK a `Account`. |
| `full_name` | string | |
| `title` | string | Cargo literal. |
| `seniority` | enum | c_level/vp/director/manager/ic/unknown (normalizado del título). |
| `department` | enum | engineering/product/data/ops/marketing/sales/exec/other. |
| `country` | string | |
| `linkedin_url` | string | |
| `email` | string | Puede ser null en el POC. |
| `source` | string | |
| `enriched_fields` | string[] | |
| `raw` | object | |

### 4.3 Taxonomías

`industry`, `seniority`, `department`, `funding_stage` usan **enums/listas controladas** versionadas en `docs/taxonomies/`. El enrichment debe mapear valores de proveedor → taxonomía canónica. Esto evita que "Software / SaaS / IT Services" rompan el matching de criterios.

### 4.4 `Signal` (intent)

| Campo | Tipo | Notas |
|---|---|---|
| `type` | string | ej. job_post_revops, funding_round, leadership_change, tech_install, content_engagement. |
| `strength` | enum | strong/moderate/weak. |
| `observed_at` | date | Para decay temporal. |
| `source` | string | |
| `detail` | string | Texto observable (ej. "publicó búsqueda de Head of Growth"). |

---

## 5. Schema del ICP (artefacto versionable)

El ICP es un **archivo YAML** que cumple este schema. Un archivo = un ICP. Ver ejemplo completo en `docs/icp.example.yaml`.

### 5.1 Estructura de alto nivel

```yaml
meta:            # identidad y versión del ICP
segments: []     # 1..n segmentos (cada uno con sus criterios)
scoring:         # config de cómo se combina y se tieriza
```

### 5.2 `meta`

```yaml
meta:
  id: icp-saas-midmarket          # slug estable
  name: "Mid-market SaaS - NA"
  version: 1.0.0                   # semver (ver §9)
  status: draft                    # draft | active | retired
  created: 2026-06-18
  updated: 2026-06-18
  author: marchel
  changelog:
    - version: 1.0.0
      date: 2026-06-18
      note: "Versión inicial."
```

### 5.3 `segments[]`

Cada segmento define criterios a nivel **account** y **contact**, sus **pesos**, **knockouts** (must-have: si falla, descalifica) y **disqualifiers** (si matchea, descalifica).

```yaml
segments:
  - id: core
    name: "Core mid-market"
    weight: 1.0                    # peso del segmento si hay varios

    account_criteria:
      - field: employee_count      # campo del modelo canónico (§4.1)
        op: between                # eq|neq|in|not_in|gte|lte|between|contains_any
        value: [200, 2000]
        weight: 25                 # contribución al account_score (0-100 total)
        kind: scored               # scored | knockout
      - field: industry
        op: in
        value: [software, fintech, healthtech]
        weight: 30
        kind: scored
      - field: region
        op: in
        value: [NA]
        weight: 15
        kind: scored
      - field: funding_stage
        op: in
        value: [series_b, growth]
        weight: 15
        kind: scored
      - field: tech_stack
        op: contains_any
        value: [salesforce, hubspot]
        weight: 15
        kind: scored

    contact_criteria:
      - field: seniority
        op: in
        value: [c_level, vp, director]
        weight: 50
        kind: scored
      - field: department
        op: in
        value: [engineering, product, data]
        weight: 50
        kind: scored

    fuzzy_criteria:                # evaluados por LLM (§6.3)
      - id: digital_maturity
        prompt: "¿La empresa muestra señales de madurez digital / inversión en producto tech?"
        weight: 20                 # se suma al pool de account_score
        applies_to: account

    knockouts:                     # must-have; si NO se cumple → disqualified
      - field: employee_count
        op: gte
        value: 50
        reason: "Demasiado chica: ACV no justifica el ciclo."

    disqualifiers:                 # si matchea → disqualified
      - field: industry
        op: in
        value: [government, education_k12]
        reason: "Ciclos y compliance fuera de fit."

    intent_boost:                  # señales que suman al score final
      - signal_type: funding_round
        points: 10
      - signal_type: leadership_change
        points: 8

    sourcing:                      # hints de SOURCING (no afectan el scoring)
      industry_keywords:           # palabras clave de sector para filtrar la búsqueda
        - legal services
        - law firms
```

**Sourcing vs. scoring (§5.3.1).** `sourcing` separa *a quién buscar* de *cómo calificar lo que vuelve*. Los `industry_keywords` los usan los adapters de ingestion (§12) para acotar el pool en la fuente (ej. `q_organization_keyword_tags` en Apollo) — así un ICP vertical-específico (legal) no trae empresas de otra vertical (fintech). El motor de scoring **ignora** `sourcing`; los criterios difusos siguen haciendo la calificación cualitativa fina sobre lo que la búsqueda trajo.

### 5.4 `scoring`

```yaml
scoring:
  account_weight: 0.6              # combinación account/contact en el fit final
  contact_weight: 0.4
  intent_max_boost: 20             # tope de puntos por intent
  tiers:                           # mapeo score → tier
    - tier: A
      min: 80
    - tier: B
      min: 60
    - tier: C
      min: 40
    # < 40 => tier D (no priorizar)
  fuzzy:
    enabled: true
    model_hint: "modelo de juicio; configurable por env, no hardcodear proveedor"
```

---

## 6. Lógica de scoring (híbrido: reglas + LLM)

Entrada: `(Account, Contact, ICP@version)`. Salida: `ScoreResult` (§7). Pipeline determinístico salvo el paso 3.

### 6.1 Paso 1 — Knockouts y disqualifiers (gate)

Se evalúan **primero**. Si algún `knockout` no se cumple, o algún `disqualifier` matchea, el resultado es `disqualified=true`, `tier=D`, score informativo pero no se prioriza. Se registra **cuál** criterio disparó (para el "por qué"). Los knockouts pueden aplicar a nivel account o contact.

### 6.2 Paso 2 — Score por reglas (determinístico)

Para cada criterio `kind: scored`, evaluar `op(field, value)`:
- match → suma `weight`.
- no match → suma 0.

Este paso produce, por nivel, los pesos *ganados* (`Σ weights que matchean`) y el *total* determinístico (`Σ weights scored`). La normalización a 0-100 se hace en §6.4, junto con los criterios difusos, para que ambos compartan un mismo pool.

Cada criterio evaluado se guarda como `contribution` (campo, esperado, observado, match, puntos) → esto **es** la explicación.

### 6.3 Paso 3 — Criterios difusos (LLM)

Solo los `fuzzy_criteria`. El motor arma un prompt acotado con: el criterio (`prompt`), los datos relevantes de la entidad, y pide salida estructurada `{score_0_1, rationale}`. El `rationale` entra en el "por qué".

Los criterios difusos son **ciudadanos de primera clase del scoring**: su `weight` entra al mismo pool que los criterios determinísticos del nivel indicado (`applies_to`). Un criterio difuso aporta `score_0_1 * weight` puntos *ganados* sobre un denominador que incluye su `weight`. Así un criterio difuso de peso alto (ej. "¿es tech-enabled?") puede **dominar** el score del nivel, no solo darle un boost marginal (ver §6.4).

Reglas para el LLM (no negociables):
- **Salida estructurada** (JSON), nunca prosa libre.
- Si el modelo no tiene datos suficientes → `score_0_1: 0` + rationale "datos insuficientes" (no inventar).
- El proveedor/modelo es **configurable por env** (principio agnóstico). El spec no lo fija.
- Determinismo razonable: temperatura baja; cachear por `(criterio, entidad, versión_icp)`.

### 6.4 Paso 4 — Combinación e intent

El score de cada nivel (account / contact) normaliza, sobre un **único pool**, los criterios determinísticos (`scored`) y los difusos de ese nivel:

```
# Por nivel (idem para contact):
account_total  = Σ(weight de account_criteria scored) + Σ(weight de fuzzy account)   # ver degradación
account_earned = Σ(weight de account_criteria que matchean) + Σ(score_0_1 * weight de fuzzy account)
account_score  = clamp(account_earned / account_total * 100, 0, 100)   # 0 si account_total == 0

base = account_weight * account_score + contact_weight * contact_score
intent_points = min(Σ intent_boost matcheados, intent_max_boost)
fit_score = clamp(base + intent_points, 0, 100)
```

**Degradación elegante (§6.3):** si el paso fuzzy no corre para un nivel —no hay `JudgeModel`, `fuzzy.enabled=false`, o no hay `fuzzy_criteria`— los pesos difusos **no** entran al denominador; el nivel se normaliza solo sobre sus criterios determinísticos. Nunca se penaliza a una cuenta por datos que no se pudieron evaluar; cuando un criterio difuso sí se evalúa y devuelve `score_0_1: 0`, ese 0 sí cuenta (no ganó esos puntos).

### 6.5 Paso 5 — Tier

`tier` se deriva de `fit_score` vía `scoring.tiers`. Si `disqualified` → `tier = D` siempre.

---

## 7. Output del motor — `ScoreResult`

JSON. Es lo que consume sales, el handoff y el loop de feedback. **La explicabilidad es obligatoria.**

```json
{
  "account_id": "acc_123",
  "contact_id": "ct_456",
  "icp_id": "icp-saas-midmarket",
  "icp_version": "1.0.0",
  "scored_at": "2026-06-18T14:00:00Z",
  "fit_score": 78,
  "tier": "B",
  "disqualified": false,
  "account_score": 82,
  "contact_score": 70,
  "intent_points": 8,
  "knockouts": [
    {"field": "employee_count", "op": "gte", "value": 50, "passed": true}
  ],
  "disqualifiers": [],
  "contributions": [
    {"level": "account", "field": "industry", "expected": ["software","fintech","healthtech"], "observed": "software", "match": true, "points": 30},
    {"level": "account", "field": "employee_count", "expected": [200,2000], "observed": 1400, "match": true, "points": 25},
    {"level": "contact", "field": "seniority", "expected": ["c_level","vp","director"], "observed": "director", "match": true, "points": 50}
  ],
  "fuzzy": [
    {"id": "digital_maturity", "score_0_1": 0.7, "points": 14, "rationale": "Stack moderno + equipo de producto visible."}
  ],
  "intent": [
    {"signal_type": "leadership_change", "points": 8, "detail": "Nuevo VP Eng (hace 2 meses)."}
  ],
  "explanation": "Fit B (78). Empresa fuerte (industria + tamaño + stack). Contacto director en eng. Suma señal de leadership change. Baja el contact_score por departamento parcialmente fuera de foco."
}
```

`explanation` es un resumen legible (puede generarlo el LLM a partir de `contributions`); `contributions` es la fuente auditable.

---

## 8. ICP Registry

- Cada ICP es un archivo en `icp/` (ej. `icp/saas-midmarket.yaml`). **Multi-ICP** = varios archivos.
- El motor recibe **qué ICP y qué versión** usar (parámetro explícito). Nunca asume "el ICP por defecto".
- Validación de schema al cargar (ej. JSON Schema / pydantic-equivalente). Un ICP inválido **no** se puede activar.
- `status: active` marca el ICP en uso; `draft` se puede scorear en modo prueba; `retired` se conserva para auditar scores históricos.

---

## 9. Versionado del ICP

- **Semver** en `meta.version`:
  - **patch** (1.0.x): ajuste de valores/pesos sin cambiar campos.
  - **minor** (1.x.0): agregar criterios o segmentos.
  - **major** (x.0.0): cambios que rompen comparabilidad de scores (cambia la lógica de fit).
- Todo `ScoreResult` guarda `icp_id` + `icp_version`: un score siempre es interpretable contra la definición que lo produjo.
- `changelog` obligatorio en cada bump.
- **Cómo nace una v2:** el feedback de sales (§10) muestra patrones de error (ej. "los no-fit suelen ser <100 empleados") → se ajusta el YAML → nuevo bump → se re-scorea. El histórico queda asociado a su versión.

---

## 10. Contrato del feedback loop

Sales marca cada lead trabajado como fit / no-fit. Estructura del registro:

```json
{
  "account_id": "acc_123",
  "contact_id": "ct_456",
  "icp_id": "icp-saas-midmarket",
  "icp_version": "1.0.0",
  "predicted_tier": "B",
  "predicted_fit_score": 78,
  "verdict": "no_fit",          // fit | no_fit
  "reason_code": "wrong_size",  // taxonomía corta: wrong_size | wrong_industry | wrong_persona | bad_timing | good_fit | other
  "reason_note": "Eran 40 personas, no calificaban.",
  "marked_by": "sdr_sofia",
  "marked_at": "2026-06-20T10:00:00Z"
}
```

Uso:
- **Medición:** alimenta el ICP-fit rate (§11) por versión.
- **Refinamiento:** agregando `verdict` real vs `predicted_tier` se ve dónde el ICP sobre/sub-califica → guía el ajuste de criterios/pesos hacia una nueva versión.
- `reason_code` es una **lista controlada** para poder agregar; `reason_note` es libre.

> POC: el feedback puede capturarse incluso en una planilla/formulario simple mientras cumpla este contrato. No requiere integración pesada todavía.

---

## 11. Métrica — ICP-fit rate

```
ICP-fit rate (versión, período) =
   # leads marcados "fit" / # leads marcados (fit + no_fit)
```

- Se reporta **por versión de ICP** (para ver si v2 mejora sobre v1).
- **Baseline:** capturar el fit-rate actual del proceso manual antes de aplicar el motor (acción pendiente del Project). Sin baseline no hay con qué comparar.
- Métrica secundaria: correlación entre `tier` predicho y `verdict` real (¿los A/B son realmente fit más seguido que C/D?).

---

## 12. Adapters (contratos abstractos)

El motor no conoce proveedores. Define interfaces; cada herramienta del stack se implementa detrás de una:

| Interfaz | Responsabilidad | Entra / sale |
|---|---|---|
| `IngestionSource` | Traer cuentas/contactos crudos y normalizar a canónico (§4). | → `Account[]`, `Contact[]` |
| `EnrichmentProvider` | Completar `enriched_fields` faltantes que el scoring necesita. | `Account/Contact` → idem completado |
| `CrmGateway` | De-dup y validación contra CRM (existe ya? está en pipeline?). | `Account` → estado en CRM |
| `ResultSink` | Persistir/entregar `ScoreResult` aguas abajo. | `ScoreResult[]` → destino |
| `FeedbackSource` | Leer los registros de feedback de sales (§10). | → `Feedback[]` |
| `JudgeModel` | Evaluar `fuzzy_criteria` (LLM). Configurable por env. | prompt → `{score_0_1, rationale}` |

Implementar un adapter ≠ tocar el motor. Esto es lo que hace la solución swappable.

---

## 13. Fuera de alcance (POC)

- **E2** armado/enrichment automático de listas a escala (acá solo tajada fina manual).
- **E3** qualification post-respuesta y handoff con scoring propio.
- **E4** orquestación de outreach multicanal.
- **E5** dashboard (acá el fit-rate puede vivir en una planilla).
- UI de edición del ICP (se edita el YAML a mano por ahora).

---

## 14. Acceptance criteria del POC (definition of done)

1. Cargar un ICP YAML válido desde `icp/`; rechazar uno inválido con error claro.
2. Dado `(Account, Contact, ICP@version)`, devolver un `ScoreResult` completo (§7) con knockouts, contributions y explanation.
3. Los knockouts/disqualifiers fuerzan `tier D` y se reportan.
4. El paso fuzzy funciona con `JudgeModel` configurable y degradada elegante si no hay datos.
5. Versionar un ICP (bump + changelog) y re-scorear un set: los scores quedan asociados a su versión.
6. Ingerir un registro de feedback (§10) y calcular el ICP-fit rate por versión.
7. Correr sobre un set real chico (ej. 50-100 cuentas) y que sales valide la explicación de al menos una muestra.

---

## 15. Handoff a Claude Code — notas

Estructura de repo sugerida (lenguaje a elección; el spec es agnóstico):

```
/icp/                     # ICPs versionables (YAML)
  saas-midmarket.yaml
/docs/
  icp-engine-spec.md      # este documento
  icp.example.yaml        # template comentado
  taxonomies/             # enums controlados
/src/
  canonical/              # modelos Account/Contact/Signal
  registry/               # carga + validación de ICP
  scoring/                # pipeline §6 (rules + fuzzy + combine + tier)
  adapters/               # implementaciones de §12 (una por proveedor)
  feedback/               # §10 + fit-rate §11
/tests/
  fixtures/               # cuentas/contactos de prueba + ICPs de prueba
```

Recomendaciones para el build:
- Empezar por `canonical` + `registry` + `scoring` con **fixtures** (sin adapters reales): así se prueba el motor end-to-end con datos mock antes de tocar ninguna herramienta.
- `JudgeModel` detrás de interfaz desde el día uno (no llamar a un proveedor directo en `scoring`).
- Tests sobre el pipeline de scoring con ICPs sintéticos cubriendo: knockout, disqualifier, match parcial, intent boost, tier boundaries.
- El YAML es el contrato: si el motor necesita un campo nuevo, primero se agrega al schema (§5) y a este doc.

---

*Documento vivo. Próximo paso de contenido: definir el ICP v1 real (con la skill `icp-architect`) y materializarlo como el primer archivo de `icp/`.*

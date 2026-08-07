# Mini-diseño — Exa como fuente complementaria en el enrichment

> Diseño (no implementación). Generado 2026-08-06. Decisiones cerradas con Marcelo:
> **(1)** patrón async fire→poll · **(2)** company + persona en UN solo `agent/run` ·
> **(3)** Clay y Exa son complementarios (LinkedIn=Clay, web=Exa) · **(4)** de la persona
> traemos: actividad pública, contenido producido, movimientos de carrera, prensa.
>
> Groundeado en el benchmark en vivo (Apollo viene stale en el ICP real: mediana ~18.6
> meses de funding; Exa trae el evento con grounding 100% auditable).

---

## 1. Objetivo y ubicación

Sumar Exa como fuente de **web-research grounded** en el **enrichment de A/B**
(post-calificación), al lado de Apollo y Clay. **Complementa, no compite.**

**No se toca**: la calificación, el path de Apollo (`company_signals`), ni la
integración de Clay. Es aditivo y **degrada elegante**: sin `EXA_API_KEY` o si Exa
devuelve null, el enrichment queda como hoy.

Por qué en enrichment y NO en calificación: la calificación corre sobre TODA la lista
(incluye C/D que se descartan); meter Exa ahí sería pagar ~$0.10 + 30-94s por leads que
se tiran. El enrichment corre solo sobre A/B ya filtrados.

```
Calificar (rúbrica) → A/B → ENRICHMENT
                              ├─ Apollo → company hard-data (employee, industry, country)  [existe]
                              ├─ Clay   → posteos de LinkedIn del contacto                   [existe]
                              └─ Exa    → company (funding/hiring/geo) + persona (web)   ★ NUEVO
                                        ↓
                              LLM sintetiza los signals, ahora grounded + con fuente
```

---

## 2. Adapter (detrás de interfaz — principio del proyecto)

Nuevo `ui/exa_enrich.py`, mismo patrón que `activity.py` / `hubspot.py`:

- `StubExaSource` — sin `EXA_API_KEY`: no hace nada (el enrichment sigue como hoy).
- `ExaEnrichmentSource` — real, httpx, **un `agent/run` por lead** que cubre company +
  persona. `mode = "async"`.
- `get_source()` — Exa si hay `EXA_API_KEY`, si no el stub.

Métodos:
- `request_enrichment(lead) -> run_id` — crea el run (fire). Ancla la persona por
  **LinkedIn URL** + nombre + empresa en el query; grounding obligatorio (null si no lo
  puede fundar en una fuente).
- `poll(run_id) -> dict | None` — GET del run; None si sigue `pending`, dict parseado si
  terminal.

Reusa el cliente httpx del benchmark (`scripts/bench/exa_client.py`) como referencia,
pero el adapter productivo vive en `ui/` (el `scripts/bench` es descartable).

---

## 3. Flujo async fire→poll (la latencia son 30-94s/lead)

Exa Agent es **request→poll** (no manda webhook como Clay), así que poleamos nosotros.

**Paso 1 — Disparar** (botón "Enriquecer con Exa" sobre los A/B elegidos):
- Estimador de costo + confirmación (como el benchmark). ~$0.107/lead.
- Concurrencia ≤2 (límite pay-as-you-go de Exa).
- Por cada lead: `request_enrichment` → guarda `{run_id, status:"pending"}` en `lead.exa`.
- Devuelve al toque (no bloquea).

**Paso 2 — Traer** (botón "Actualizar Exa", o auto-poll al abrir la vista):
- Por cada lead con `status:"pending"`: `poll(run_id)`.
- Si terminal: parsea, guarda el resultado + `status:"completed"` (o `"failed"`).
- Idempotente: re-pollear no re-dispara ni re-paga.

Estados: `pending → completed | failed`. (Un lead sin `exa` = nunca se disparó.)

> Fallback si no querés el fire→poll aún: sincrónico con spinner + pool de 2, solo para
> lotes chicos (5-10). Documentado, no default.

---

## 4. Un solo `agent/run`: company + persona

Query (una sola llamada, mitad de costo):

> "For the company at {domain} and the person {name}, {title} at {company}
> (LinkedIn: {linkedin_url}): find (A) the company's most recent funding round, active
> technical hiring, and recent geographic expansion; and (B) about that specific person:
> recent public activity (talks, podcasts, interviews), content they authored, career
> moves, and press mentions. Anchor the person by the LinkedIn URL. Return null for
> anything you cannot ground in a source."

`outputSchema` (cada dato con su `source_url`):
```json
{
  "type": "object",
  "properties": {
    "company": {
      "type": "object",
      "properties": {
        "funding": {"stage": "...", "amount_usd": "...", "date": "...", "source_url": "..."},
        "hiring": {"value": "...", "source_url": "..."},
        "geo_expansion": {"value": "...", "source_url": "..."}
      }
    },
    "person": {
      "type": "object",
      "properties": {
        "public_activity": {"value": "...", "source_url": "..."},
        "content": {"value": "...", "source_url": "..."},
        "career_moves": {"value": "...", "source_url": "..."},
        "press": {"value": "...", "source_url": "..."}
      }
    }
  }
}
```
`effort: "medium"` FIJO (nunca "auto"). Reusa el parser tolerante del benchmark
(null + no rompe si una shape viene distinta).

---

## 5. Modelo de datos

Nueva columna `exa` (jsonb) en la tabla `leads`, espejando `activity` de Clay:
```json
{
  "run_id": "...", "status": "completed", "fetched_at": "...",
  "company": { "funding": {"v": "...", "src": "url"}, "hiring": {...}, "geo": {...} },
  "person":  { "public_activity": {"v","src"}, "content": {...},
               "career_moves": {...}, "press": {...} }
}
```
Migración: `alter table public.leads add column if not exists exa jsonb;`
Siempre se guarda **la fuente por dato** (auditable + para mostrar/verificar en la UI).

En `leads_store.py`: `row_to_lead` incluye `exa` (como ya hace con `activity`);
`update_fields` ya sirve para escribirlo.

---

## 6. Cómo alimenta el mensaje

Dos consumidores, ambos ganan grounding real:
- **`enrich.py`** — los facts de Exa entran al prompt del LLM. Se agrega `source="exa"`
  al modelo de señal (hoy es `"apollo"` | `"llm"`). Signals hoy adivinados
  (`hiring_tech`, `geo_expansion`, `funding`, `maturity`, `hook`) pasan de hipótesis a
  **hecho con fuente** cuando hay dato de Exa; si no, siguen como `"llm"`.
- **`message.py`** — hoy usa `activity.summary` (Clay) como hook principal; se le suman
  los facts de **persona** de Exa (carrera, prensa, charlas, contenido) como munición
  extra, con cita. Clay = posteos de LinkedIn; Exa = presencia web fuera de LinkedIn.
  Evitar repetir en el mensaje lo que ya trae Clay (dedupe simple por overlap de texto).

---

## 7. Costo y control
- ~$0.107/lead, **solo A/B**. Caché por lead (`status` evita re-disparar).
- Concurrencia ≤2. Estimador + confirmación antes de disparar. Cap de aborto (como el
  benchmark).

---

## 8. Gate de validación (la persona NO está probada)
El benchmark validó **company**; **persona no**. Antes de prender persona-Exa en el
flujo real: mini-validación barata (5-10 leads, chequeo las URLs a mano) para confirmar
que el match de persona no trae homónimos. Si el grounding no cierra, arrancamos solo con
company y sumamos persona después.

---

## 9. Riesgos honestos
- **Desambiguación de persona**: el ancla LinkedIn + grounding filtran, pero no es
  infalible. El gate del §8 existe por esto.
- **Latencia**: obliga al fire→poll (más piezas que un swap sincrónico).
- **Poll manual**: sin webhook, el resultado llega cuando el usuario aprieta "Actualizar"
  (o auto-poll al abrir). Aceptable para el POC; a futuro, un `pg_cron` en Supabase podría
  poll-ear solo.
- **Solape con Clay**: resuelto como complementario, pero hay que dedupe en el mensaje.

---

## 10. Checklist de implementación (cuando se apruebe)
1. Migración Supabase: columna `exa` jsonb.
2. `ui/exa_enrich.py`: `StubExaSource` + `ExaEnrichmentSource` (fire + poll) + `get_source()`.
3. `leads_store.py`: `row_to_lead` incluye `exa`.
4. `enrich.py`: `source="exa"`; los facts de Exa entran al prompt de síntesis.
5. `message.py`: sumar facts de persona de Exa como hook, con dedupe vs Clay.
6. UI: botones "Enriquecer con Exa" (fire) + "Actualizar Exa" (poll), estados en la
   tarjeta del lead. i18n ES/EN.
7. Tests: parser tolerante (fixtures), fire/poll con cliente inyectado, dedupe vs Clay.
8. Config: `EXA_API_KEY` en `.env` local + Secrets de Streamlit.
9. Gate §8: validar persona en 5-10 leads antes de prenderla productiva.

---

## Decisiones aún abiertas (para cuando implementemos)
- **UI**: ¿los botones fire/poll van en Calificar (sección enrichment) o también en el
  detalle del Pipeline? (hoy Clay se dispara desde el Pipeline).
- **Auto-poll**: ¿poll automático al abrir la vista, o solo botón manual?
- **Señales**: ¿qué signals exactos marcamos `source="exa"` por default?

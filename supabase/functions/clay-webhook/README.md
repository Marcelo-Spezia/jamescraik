# Actividad de LinkedIn con Clay (Fase 2)

Enriquecimiento **asincrónico** de posteos recientes, app-triggered:

```
App ("Traer actividad")  ──POST {lead_id, linkedin_url}──►  Tabla Clay (webhook de entrada)
                                                                │ enriquece: posteos recientes
                                                                ▼
   leads.activity  ◄──POST {lead_id, summary, posts}──  Edge Function clay-webhook
```

## 0. Migración (una vez, SQL Editor de Supabase)
```sql
alter table public.leads add column if not exists activity jsonb;
```

## 1. Deploy de la Edge Function
```bash
supabase functions deploy clay-webhook --no-verify-jwt
supabase secrets set CLAY_WEBHOOK_SECRET="elegí-un-secreto-largo"
```
(`--no-verify-jwt`: Clay no manda JWT de Supabase; la seguridad la da `?token=`.)

URL de vuelta (la usás en Clay, paso 2c):
```
https://utmjrigiqztpjhxgwuhd.supabase.co/functions/v1/clay-webhook?token=TU_SECRETO
```

## 2. La tabla en Clay (lo armás vos en la UI de Clay)
La spec; los nombres exactos de integraciones/columnas los confirmás en Clay:

**a. Fuente = Webhook (entrada).** Creá la tabla con fuente "Webhook / Import from
webhook". Clay te da una URL — esa va en el `.env` de la app como `CLAY_WEBHOOK_URL`.
La app le va a mandar filas con `{ lead_id, linkedin_url }`.

**b. Enrichment = posteos recientes.** Agregá una columna que, a partir de
`linkedin_url`, traiga los **posteos recientes** del perfil (elegí en Clay la
integración/proveedor que ofrezca esto). Opcional: una columna de IA que **resuma** los
posteos en 1-2 frases (campo `summary`).

**c. Acción = Send Webhook (salida).** Al terminar el enriquecimiento, que mande un POST a
la URL del paso 1, con este body:
```json
{
  "lead_id": "{{ lead_id }}",
  "summary": "{{ resumen }}",
  "posts": ["{{ posteo_1 }}", "{{ posteo_2 }}"]
}
```
`lead_id` es el que le mandó la app (echoalo tal cual) → matcheo exacto.

## 3. Conectar la app
En `.env` (local) y en los Secrets de Streamlit (deploy):
```
CLAY_WEBHOOK_URL=<la URL de entrada de tu tabla de Clay>
```
Con eso, el botón "Traer actividad" pasa a disparar el pedido a Clay (antes usaba el stub).

## 4. Probar (simular el back de Clay)
Con un lead ya en el pipeline (agarrá su `id` de Supabase):
```bash
curl -X POST \
  "https://utmjrigiqztpjhxgwuhd.supabase.co/functions/v1/clay-webhook?token=TU_SECRETO" \
  -H "content-type: application/json" \
  -d '{"lead_id":"<UUID_DEL_LEAD>","summary":"Posteó sobre su ronda Serie B.","posts":["Anunciamos la Serie B…"]}'
```
Esperado: `{"ok":true,"matched":1}`. En el Pipeline, el lead muestra la actividad y el
mensaje la usa de hook.

## Notas
- Es **asincrónico**: "Traer actividad" dispara; el dato aparece cuando Clay termina.
- Match por `lead_id` (exacto); `linkedin_url` como fallback.
- Si `matched: 0`, revisá que el `lead_id` del payload sea el de un lead existente.

# Webhook de Expandi → Supabase (Edge Function)

Recibe el webhook de Expandi cuando un prospecto **acepta la conexión** o **responde**,
y actualiza el estado del lead en la tabla `leads` (matcheando por URL de LinkedIn).

## 1. Deploy

**Opción A — Supabase CLI** (recomendada):
```bash
# desde la raíz del repo, logueado en Supabase y con el proyecto linkeado
supabase functions deploy expandi-webhook --no-verify-jwt
supabase secrets set EXPANDI_WEBHOOK_SECRET="elegí-un-secreto-largo"
```
> `--no-verify-jwt` es **imprescindible**: Expandi no manda el JWT de Supabase. La
> seguridad la da el `?token=` (nuestro secreto), no el JWT.

**Opción B — Dashboard:** Supabase → **Edge Functions** → **Deploy a new function** →
nombre `expandi-webhook` → pegá `index.ts` → en **Settings** de la función, desactivá
**"Verify JWT"** → en **Secrets** agregá `EXPANDI_WEBHOOK_SECRET`.

`SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` los inyecta Supabase solo (no hay que setearlos).

## 2. URL del webhook

```
https://utmjrigiqztpjhxgwuhd.supabase.co/functions/v1/expandi-webhook?status=accepted&token=TU_SECRETO
```
- `status` = a qué estado pasa el lead: `accepted` (aceptó conexión) o `replied` (respondió).
- `token` = el `EXPANDI_WEBHOOK_SECRET`.
- opcional `campaign_slug=...` para acotar el update a una campaña.

## 3. Configurar en Expandi

En el flujo de la campaña, agregá un paso **Webhook** después del evento:
- Tras **"connection accepted"** → URL con `?status=accepted&token=...`
- Tras **"replied"** (si lo usás) → URL con `?status=replied&token=...`

No importa el formato del payload que mande Expandi: la función busca la URL de LinkedIn
en cualquier parte del cuerpo.

## 4. Probar (simular Expandi)

Con un lead ya guardado en el pipeline (que tenga esa URL de LinkedIn):
```bash
curl -X POST \
  "https://utmjrigiqztpjhxgwuhd.supabase.co/functions/v1/expandi-webhook?status=accepted&token=TU_SECRETO" \
  -H "content-type: application/json" \
  -d '{"profile":"https://www.linkedin.com/in/EL-PERFIL-DEL-LEAD/","event":"connection_accepted"}'
```
Respuesta esperada: `{"ok":true,"linkedin":"linkedin.com/in/el-perfil-del-lead","status":"accepted","matched":1}`.
Después, en la vista **Pipeline** de la app, ese lead debería figurar como **Conectado**.

## 5. Verificar / debug

- **Logs**: Supabase → Edge Functions → `expandi-webhook` → Logs. Ahí ves el payload real
  de Expandi y cuántos leads matcheó. Si `matched: 0`, la URL de LinkedIn del webhook no
  coincide con la guardada (revisá que el lead esté en el pipeline con esa misma URL).
- `matched: 0` con `"no se encontró URL de LinkedIn"` → el payload de Expandi no trae la
  URL donde esperábamos; copiá un ejemplo del log y ajustamos el regex.

## Notas
- El match es por URL de LinkedIn normalizada (igual que `norm_linkedin` en
  `ui/leads_store.py`). Si Expandi manda otro identificador (ej. un hash), lo adaptamos
  cuando veamos un payload real en los logs.
- Rotá `EXPANDI_WEBHOOK_SECRET` cuando quieras: `supabase secrets set ...` (efecto inmediato).

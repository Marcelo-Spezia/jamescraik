// Edge Function: recibe el webhook de Expandi y actualiza el estado del lead en Supabase.
//
// Expandi NO tiene API de entrada, pero manda webhooks de salida. Configurás una URL
// por paso de campaña, con el estado y un token en el query string, p.ej:
//   https://<proj>.supabase.co/functions/v1/expandi-webhook?status=accepted&token=SECRETO
//   https://<proj>.supabase.co/functions/v1/expandi-webhook?status=replied&token=SECRETO
//
// Matchea el lead por URL de LinkedIn (normalizada igual que en Python) — la busca en
// CUALQUIER parte del payload, así no dependemos del formato exacto de Expandi.
//
// Deploy:  supabase functions deploy expandi-webhook --no-verify-jwt
//          supabase secrets set EXPANDI_WEBHOOK_SECRET=...    (elegí un secreto)
// (--no-verify-jwt es CLAVE: Expandi no manda JWT de Supabase; protegemos con ?token=)

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ALLOWED = ["qualified", "connection_sent", "accepted",
                 "message_ready", "sent", "replied", "discarded"];

// Espejo EXACTO de norm_linkedin() en ui/leads_store.py (para que matchee lo guardado).
function normLinkedin(raw: string): string | null {
  let s = (raw || "").trim().toLowerCase();
  if (!s) return null;
  s = s.replace(/^https?:\/\//, "");
  if (s.startsWith("www.")) s = s.slice(4);
  s = s.split("?")[0].replace(/\/+$/, "");
  return s || null;
}

// Busca la primera URL de perfil de LinkedIn en un texto cualquiera (payload + query).
function findLinkedin(text: string): string | null {
  const m = text.match(/([a-z]+:\/\/)?(www\.)?linkedin\.com\/in\/[a-z0-9\-_%.]+/i);
  return m ? m[0] : null;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);

  // 1) Auth por token compartido (reemplaza al JWT).
  const secret = Deno.env.get("EXPANDI_WEBHOOK_SECRET");
  if (secret && url.searchParams.get("token") !== secret) {
    return json({ ok: false, error: "unauthorized" }, 401);
  }

  // 2) Estado destino (por query param; default 'accepted').
  const status = url.searchParams.get("status") ?? "accepted";
  if (!ALLOWED.includes(status)) {
    return json({ ok: false, error: `status inválido: ${status}` }, 400);
  }

  // 3) Buscar la URL de LinkedIn en todo el payload (+ query).
  const raw = await req.text().catch(() => "");
  const linkedin = findLinkedin(raw + " " + url.search);
  if (!linkedin) {
    console.log("webhook sin URL de LinkedIn. Payload:", raw.slice(0, 2000));
    return json({ ok: false, reason: "no se encontró URL de LinkedIn en el payload" }, 200);
  }
  const norm = normLinkedin(linkedin);

  // 4) Actualizar el/los lead(s). Opcional: acotar a una campaña con ?campaign_slug=...
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
  let q = supabase.from("leads").update({ status }).eq("linkedin_url", norm);
  const slug = url.searchParams.get("campaign_slug");
  if (slug) q = q.eq("campaign_slug", slug);
  const { data, error } = await q.select("id");
  if (error) {
    console.error("error actualizando:", error.message);
    return json({ ok: false, error: error.message }, 500);
  }
  console.log(`webhook: ${norm} -> ${status} (${data?.length ?? 0} lead(s))`);
  return json({ ok: true, linkedin: norm, status, matched: data?.length ?? 0 });
});

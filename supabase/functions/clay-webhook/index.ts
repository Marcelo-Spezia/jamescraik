// Edge Function: recibe el resultado de enriquecimiento de Clay y guarda la actividad
// de LinkedIn del lead en Supabase (leads.activity).
//
// Flujo (app-triggered): el botón "Traer actividad" hace POST del lead a la webhook de
// entrada de la tabla de Clay → Clay enriquece (posteos recientes) → Clay hace POST del
// resultado ACÁ → actualizamos leads.activity matcheando por lead_id (o linkedin_url).
//
// Payload esperado (lo definís vos en la acción "Send webhook" de Clay):
//   { "lead_id": "<uuid>", "summary": "<resumen>", "posts": [ "...", "..." ] }
// (linkedin_url opcional como fallback de matcheo).
//
// Deploy:  supabase functions deploy clay-webhook --no-verify-jwt
//          supabase secrets set CLAY_WEBHOOK_SECRET=...      (mismo token en la URL de Clay)
// URL en Clay:  https://<proj>.supabase.co/functions/v1/clay-webhook?token=SECRETO

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

function normLinkedin(raw: string): string | null {
  let s = (raw || "").trim().toLowerCase();
  if (!s) return null;
  s = s.replace(/^https?:\/\//, "");
  if (s.startsWith("www.")) s = s.slice(4);
  s = s.split("?")[0].replace(/\/+$/, "");
  return s || null;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);

  // 1) Auth por token compartido.
  const secret = Deno.env.get("CLAY_WEBHOOK_SECRET");
  if (secret && url.searchParams.get("token") !== secret) {
    return json({ ok: false, error: "unauthorized" }, 401);
  }

  // 2) Parseo del payload de Clay.
  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, error: "invalid json" }, 400);
  }

  const leadId = (body.lead_id ?? body.leadId ?? "") as string;
  const linkedin = (body.linkedin_url ?? body.linkedin ?? "") as string;
  if (!leadId && !linkedin) {
    console.log("clay webhook sin lead_id ni linkedin. Payload:", JSON.stringify(body).slice(0, 2000));
    return json({ ok: false, reason: "falta lead_id o linkedin_url" }, 200);
  }

  // 3) Armar el objeto de actividad (posteos recientes).
  // `posts` puede venir como lista (["...","..."]) o como un texto (una línea por posteo).
  let posts: string[] = [];
  if (Array.isArray(body.posts)) {
    posts = body.posts.map((p) => String(p).trim()).filter(Boolean);
  } else if (typeof body.posts === "string" && body.posts.trim()) {
    posts = body.posts.split("\n").map((s) => s.trim()).filter(Boolean);
  }
  // `summary` opcional: si Clay no lo manda, lo armamos con los primeros posteos.
  let summary = (body.summary ?? "") as string;
  if (!summary && posts.length) {
    summary = "Posteos recientes: " + posts.slice(0, 3).join(" · ");
  }
  const activity = {
    summary,
    items: posts.map((p) => ({ type: "post", text: p })),
    source: "clay",
    fetched_at: new Date().toISOString(),
  };

  // 4) Guardar en el lead (por id; si no, por linkedin_url normalizado).
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
  let q = supabase.from("leads").update({ activity });
  q = leadId ? q.eq("id", leadId) : q.eq("linkedin_url", normLinkedin(linkedin));
  const { data, error } = await q.select("id");
  if (error) {
    console.error("error actualizando:", error.message);
    return json({ ok: false, error: error.message }, 500);
  }
  console.log(`clay webhook: ${leadId || normLinkedin(linkedin)} (${data?.length ?? 0} lead(s))`);
  return json({ ok: true, matched: data?.length ?? 0 });
});

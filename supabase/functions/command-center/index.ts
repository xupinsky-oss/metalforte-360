import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};
const OWNER_ID = "8ced6ddc-d1be-4bf8-95c1-39324930320a";

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "GET") {
    return new Response("Método não permitido.", { status: 405, headers: corsHeaders });
  }

  const url = Deno.env.get("SUPABASE_URL");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !anon || !serviceRole) {
    return new Response("Configuração indisponível.", { status: 503, headers: corsHeaders });
  }
  const token = request.headers.get("Authorization")?.replace(/^Bearer\s+/i, "");
  if (!token) return new Response("Autenticação necessária.", { status: 401, headers: corsHeaders });
  const auth = createClient(url, anon);
  const { data: userData, error: authError } = await auth.auth.getUser(token);
  if (authError || !userData.user) return new Response("Sessão inválida.", { status: 401, headers: corsHeaders });
  if (userData.user.id !== OWNER_ID) return new Response("Acesso não autorizado.", { status: 403, headers: corsHeaders });

  const supabase = createClient(url, serviceRole);
  const bucket = Deno.env.get("SUPABASE_BUCKET") ?? "metalforte-private";
  const path = Deno.env.get("SUPABASE_DASHBOARD_PATH") ?? "dashboard/command-center.json";
  const { data, error } = await supabase.storage.from(bucket).download(path);
  if (error || !data) {
    return new Response("Resumo ainda não foi publicado.", { status: 503, headers: corsHeaders });
  }
  return new Response(await data.text(), {
    headers: { ...corsHeaders, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
});


import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
};

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "GET") {
    return new Response("Método não permitido.", { status: 405, headers: corsHeaders });
  }

  const url = Deno.env.get("SUPABASE_URL");
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !serviceRole) {
    return new Response("Configuração indisponível.", { status: 503, headers: corsHeaders });
  }

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

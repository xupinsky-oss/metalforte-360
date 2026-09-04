import { createClient } from "npm:@supabase/supabase-js@2";

const jsonHeaders = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" };
const steps = [
  "Disparo solicitado", "Autorização e permissões", "Preparação do ambiente",
  "Coleta TOTVS / GoodData", "Validação da base", "Tratamento e normalização",
  "Publicação da base privada", "Geração de métricas e agregados",
  "Publicação do resumo", "Validação pós-carga", "Painel disponível",
];

function cors(request: Request) {
  const origin = request.headers.get("origin") ?? "";
  const allowed = (Deno.env.get("ETL_ALLOWED_ORIGINS") ?? "https://xupinsky-oss.github.io")
    .split(",").map((item) => item.trim()).filter(Boolean);
  return {
    "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0],
    "Access-Control-Allow-Headers": "authorization, apikey, content-type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Vary": "Origin",
  };
}

function response(request: Request, body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...jsonHeaders, ...cors(request) } });
}

function clean(value: unknown, max = 240) {
  return String(value ?? "").replace(/[\r\n\t]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: cors(request) });
  if (!["GET", "POST"].includes(request.method)) return response(request, { error: "Método não permitido." }, 405);

  const url = Deno.env.get("SUPABASE_URL");
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const authHeader = request.headers.get("authorization") ?? "";
  const accessToken = authHeader.replace(/^Bearer\s+/i, "");
  if (!url || !serviceRole || !accessToken) return response(request, { error: "Configuração ou sessão indisponível." }, 503);

  const admin = createClient(url, serviceRole, { auth: { persistSession: false } });
  const { data: userData, error: userError } = await admin.auth.getUser(accessToken);
  if (userError || !userData.user) return response(request, { error: "Sessão inválida ou expirada." }, 401);
  const user = userData.user;
  const allowedEmails = (Deno.env.get("ETL_ALLOWED_EMAILS") ?? "").split(",").map((item) => item.trim().toLowerCase()).filter(Boolean);
  const authorized = user.app_metadata?.etl_admin === true || (!!user.email && allowedEmails.includes(user.email.toLowerCase()));
  if (!authorized) return response(request, { error: "Usuário sem permissão para operar o ETL." }, 403);

  const bucket = Deno.env.get("SUPABASE_BUCKET") ?? "metalforte-private";
  async function readRun(path: string) {
    const { data, error } = await admin.storage.from(bucket).download(path);
    if (error || !data) return null;
    try { return JSON.parse(await data.text()); } catch { return null; }
  }

  if (request.method === "GET") {
    const view = new URL(request.url).searchParams.get("view") ?? "latest";
    if (view === "latest") return response(request, { run: await readRun("etl/latest.json") });
    if (view !== "history") return response(request, { error: "Consulta inválida." }, 400);
    const { data: files, error } = await admin.storage.from(bucket).list("etl/runs", { limit: 20, sortBy: { column: "updated_at", order: "desc" } });
    if (error) return response(request, { error: "Histórico temporariamente indisponível." }, 503);
    const runs = (await Promise.all((files ?? []).filter((file) => file.name.endsWith(".json")).map((file) => readRun(`etl/runs/${file.name}`)))).filter(Boolean);
    return response(request, { runs });
  }

  let payload: Record<string, unknown>;
  try { payload = await request.json(); } catch { return response(request, { error: "JSON inválido." }, 400); }
  const environment = clean(payload.environment, 20);
  const scope = clean(payload.scope, 20);
  const reason = clean(payload.reason);
  if (!payload.confirmed || !["homologacao", "producao"].includes(environment) || scope !== "full" || reason.length < 10) {
    return response(request, { error: "Ambiente, escopo, motivo e confirmação são obrigatórios." }, 400);
  }

  const repository = Deno.env.get("GITHUB_REPOSITORY");
  const githubToken = Deno.env.get("GITHUB_DISPATCH_TOKEN");
  const workflow = Deno.env.get("GITHUB_WORKFLOW_FILE") ?? "atualizar-base.yml";
  const ref = Deno.env.get("GITHUB_WORKFLOW_REF") ?? "main";
  if (!repository || !githubToken) return response(request, { error: "Disparo real ainda não configurado no ambiente seguro." }, 503);

  const requestId = crypto.randomUUID();
  const now = new Date().toISOString();
  const run = { id: requestId, status: "queued", source: "control_tower", environment, scope, requested_by: user.email ?? user.id, reason, started_at: now, updated_at: now, steps: steps.map((name, index) => ({ name, status: index < 2 ? "completed" : "pending", message: index === 0 ? "Solicitação registrada" : index === 1 ? "Usuário autorizado" : "Aguardando", at: index < 2 ? now : null })), events: [{ at: now, level: "info", message: "Solicitação manual aceita pela Control Tower." }] };
  const body = new Blob([JSON.stringify(run)], { type: "application/json" });
  const upload = async (path: string) => admin.storage.from(bucket).upload(path, body, { contentType: "application/json", upsert: true });
  const [requestUpload, latestUpload] = await Promise.all([upload(`etl/runs/${requestId}.json`), upload("etl/latest.json")]);
  if (requestUpload.error || latestUpload.error) {
    return response(request, { error: "Não foi possível registrar a auditoria da solicitação." }, 503);
  }

  const dispatch = await fetch(`https://api.github.com/repos/${repository}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${githubToken}`, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json", "User-Agent": "metalforte360-etl-control" },
    body: JSON.stringify({ ref, inputs: { request_id: requestId, environment, scope, requested_by: user.email ?? user.id, reason, confirmation: environment === "producao" ? "ATUALIZAR" : "HOMOLOGAR" } }),
  });
  if (!dispatch.ok) {
    run.status = "failure"; run.updated_at = new Date().toISOString();
    run.events.push({ at: run.updated_at, level: "error", message: `GitHub recusou o disparo (HTTP ${dispatch.status}).` });
    const failedBody = new Blob([JSON.stringify(run)], { type: "application/json" });
    await Promise.all([admin.storage.from(bucket).upload(`etl/runs/${requestId}.json`, failedBody, { contentType: "application/json", upsert: true }), admin.storage.from(bucket).upload("etl/latest.json", failedBody, { contentType: "application/json", upsert: true })]);
    return response(request, { error: "O GitHub recusou o disparo. Consulte a configuração administrativa." }, 502);
  }
  return response(request, { accepted: true, request_id: requestId }, 202);
});

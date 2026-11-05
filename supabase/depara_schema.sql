create table public.depara_clientes (
 id bigint generated always as identity primary key,
 codigo_cliente text not null check (length(btrim(codigo_cliente)) > 0),
 loja text not null default '',
 razao_social text not null check (length(btrim(razao_social)) > 0),
 grupo_economico text,
 ativo boolean not null default true,
 atualizado_em timestamptz not null default now(),
 unique(codigo_cliente,loja)
);
create table public.depara_vendedores (
 vendedor_cadastro text primary key check (length(btrim(vendedor_cadastro)) > 0),
 vendedor_painel text not null check (length(btrim(vendedor_painel)) > 0),
 classificacao text,
 ativo boolean not null default true,
 atualizado_em timestamptz not null default now()
);
create table public.depara_controle (
 id boolean primary key default true check(id),
 revisao bigint not null default 0,
 pronto boolean not null default false,
 atualizado_em timestamptz not null default now()
);
insert into public.depara_controle(id) values(true);
alter table public.depara_clientes enable row level security;
alter table public.depara_vendedores enable row level security;
alter table public.depara_controle enable row level security;
revoke all on public.depara_clientes, public.depara_vendedores, public.depara_controle from public,anon,authenticated;
grant select on public.depara_clientes,public.depara_vendedores,public.depara_controle to service_role;
create function public.depara_marcar_linha() returns trigger language plpgsql security invoker set search_path = '' as $fn$
begin new.atualizado_em = now(); return new; end;
$fn$;
create function public.depara_marcar_versao() returns trigger language plpgsql security invoker set search_path = '' as $fn$
begin update public.depara_controle set revisao=revisao+1,atualizado_em=now() where id; return null; end;
$fn$;
create trigger depara_clientes_linha before update on public.depara_clientes for each row execute function public.depara_marcar_linha();
create trigger depara_vendedores_linha before update on public.depara_vendedores for each row execute function public.depara_marcar_linha();
create trigger depara_clientes_versao after insert or update or delete on public.depara_clientes for each statement execute function public.depara_marcar_versao();
create trigger depara_vendedores_versao after insert or update or delete on public.depara_vendedores for each statement execute function public.depara_marcar_versao();
create function public.metalforte_depara_version() returns jsonb language sql stable security invoker set search_path = '' as $fn$
 select jsonb_build_object('version',revisao,'ready',pronto,'updated_at',atualizado_em) from public.depara_controle where id;
$fn$;
create function public.metalforte_depara_snapshot() returns jsonb language sql stable security invoker set search_path = '' as $fn$
 select jsonb_build_object(
 'version',c.revisao,'ready',c.pronto,
 'customers',coalesce((select jsonb_agg(jsonb_build_array(codigo_cliente,loja,razao_social,grupo_economico)) from public.depara_clientes where ativo),'[]'::jsonb),
 'sellers',coalesce((select jsonb_agg(jsonb_build_array(vendedor_cadastro,vendedor_painel,classificacao)) from public.depara_vendedores where ativo),'[]'::jsonb)
 ) from public.depara_controle c where id and pronto;
$fn$;
revoke all on function public.depara_marcar_linha(), public.depara_marcar_versao(), public.metalforte_depara_version(), public.metalforte_depara_snapshot() from public,anon,authenticated;
grant execute on function public.metalforte_depara_version(),public.metalforte_depara_snapshot() to service_role;
comment on table public.depara_clientes is 'METALFORTE 360: editar grupo_economico; razão social é usada quando o grupo está vazio. ativo=false desativa o mapeamento.';
comment on table public.depara_vendedores is 'METALFORTE 360: editar vendedor_painel e classificacao; vendedor_cadastro deve corresponder à origem.';
notify pgrst,'reload schema';

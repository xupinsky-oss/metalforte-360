-- METALFORTE 360 | Modelo comercial unificado
--
-- Objetivo
-- --------
-- Centralizar a visão comercial na granularidade mais segura para valores:
--     1 linha por filial + pedido + item.
--
-- As movimentações do processo ficam separadas em uma trilha de eventos. Isso
-- impede que várias liberações, OPs, cargas ou notas multipliquem o faturamento
-- de um mesmo item quando forem consultadas no Command Center.
--
-- Origem mapeada no projeto legado TOTVS/GoodData
-- ------------------------------------------------
-- SC5: cabeçalho do pedido de venda
-- SC6: itens do pedido de venda
-- SC9: liberações
-- SC2/SD3: ordem de produção e apontamentos
-- DAI/DAK: itens e cabeçalho de carga
-- SD1/SD2: faturamento, custo, imposto e margem
-- SA1/SB1/SA3/SZT: cliente, produto, vendedor e motivo de perda
--
-- Como usar
-- ----------
-- 1. O extrator deve carregar as tabelas `stg` abaixo, preservando as chaves
--    de origem e `carregado_em`.
-- 2. O aplicativo e as análises devem consultar SOMENTE as visões `analytics`.
-- 3. Não exponha o schema `stg` pela Data API. Ele contém dados operacionais
--    granulares; não existem permissões públicas neste script.
--
-- Este arquivo é um contrato de carga e pode ser aplicado em PostgreSQL/Supabase
-- depois de revisado no SQL Editor. Não contém credenciais nem altera dados da
-- fonte TOTVS.

create schema if not exists stg;
create schema if not exists analytics;

comment on schema stg is 'Camada de recebimento do TOTVS/GoodData. Não expor pela API.';
comment on schema analytics is 'Camada semântica do METALFORTE 360.';

-- ---------------------------------------------------------------------------
-- 1. CAMADA DE RECEBIMENTO: dimensões
-- ---------------------------------------------------------------------------

create table if not exists stg.cliente (
  sistema_origem text not null default 'TOTVS',
  filial text not null default '',
  codigo_cliente text not null,
  loja text not null default '',
  nome_cliente text,
  nome_fantasia text,
  segmento_cliente text,
  classificacao_cliente text,
  cnpj text,
  cidade text,
  uf text,
  regiao text,
  rota text,
  ativo boolean,
  atualizado_origem_em timestamptz,
  carregado_em timestamptz not null default now(),
  primary key (sistema_origem, filial, codigo_cliente, loja)
);

create table if not exists stg.produto (
  sistema_origem text not null default 'TOTVS',
  filial text not null default '',
  codigo_produto text not null,
  descricao_produto text,
  grupo_produto text,
  subgrupo_produto text,
  familia_produto text,
  especificacao text,
  subespecificacao text,
  unidade_medida text,
  peso_unitario_kg numeric(18,6),
  ativo boolean,
  atualizado_origem_em timestamptz,
  carregado_em timestamptz not null default now(),
  primary key (sistema_origem, filial, codigo_produto)
);

create table if not exists stg.vendedor (
  sistema_origem text not null default 'TOTVS',
  filial text not null default '',
  codigo_vendedor text not null,
  nome_vendedor text,
  categoria_vendedor text,
  equipe text,
  gestor text,
  ativo boolean,
  atualizado_origem_em timestamptz,
  carregado_em timestamptz not null default now(),
  primary key (sistema_origem, filial, codigo_vendedor)
);

create table if not exists stg.motivo_perda (
  sistema_origem text not null default 'TOTVS',
  codigo_motivo text not null,
  motivo_perda text,
  grupo_motivo text,
  ativo boolean,
  carregado_em timestamptz not null default now(),
  primary key (sistema_origem, codigo_motivo)
);

-- ---------------------------------------------------------------------------
-- 2. CAMADA DE RECEBIMENTO: fatos na granularidade de origem
-- ---------------------------------------------------------------------------

create table if not exists stg.pedido_cabecalho (
  sistema_origem text not null default 'TOTVS',
  filial text not null,
  pedido text not null,
  tipo_pedido text,
  status_pedido text,
  codigo_cliente text,
  loja_cliente text,
  codigo_vendedor text,
  data_orcamento date,
  data_emissao_pv date,
  data_desejo_cliente date,
  data_previsao_entrega date,
  condicao_pagamento text,
  tipo_frete text,
  rota text,
  valor_pedido_cabecalho numeric(18,2),
  atualizado_origem_em timestamptz,
  carregado_em timestamptz not null default now(),
  primary key (sistema_origem, filial, pedido)
);

create table if not exists stg.pedido_item (
  sistema_origem text not null default 'TOTVS',
  filial text not null,
  pedido text not null,
  item text not null,
  codigo_produto text,
  descricao_item text,
  grupo_produto_origem text,
  codigo_cliente text,
  loja_cliente text,
  codigo_vendedor text,
  tipo_pedido text,
  quantidade_pedida numeric(18,6),
  quantidade_entregue numeric(18,6),
  quantidade_empenhada numeric(18,6),
  peso_kg numeric(18,6),
  unidade_medida text,
  preco_lista numeric(18,6),
  preco_unitario numeric(18,6),
  desconto_valor numeric(18,2),
  desconto_percentual numeric(9,6),
  valor_item numeric(18,2),
  custo_medio numeric(18,2),
  imposto_medio numeric(18,2),
  codigo_motivo_perda text,
  perdido boolean not null default false,
  data_emissao_pv date,
  data_desejo_cliente date,
  data_sugerida_entrega date,
  data_carga_planejada date,
  atualizado_origem_em timestamptz,
  carregado_em timestamptz not null default now(),
  primary key (sistema_origem, filial, pedido, item)
);

-- Há uma linha para cada movimentação. Liberar novamente o mesmo item não
-- substitui o histórico; a visão final usa a última liberação para o status.
create table if not exists stg.pedido_liberacao (
  id bigint generated always as identity primary key,
  sistema_origem text not null default 'TOTVS',
  filial text not null,
  pedido text not null,
  item text,
  liberado_em timestamptz,
  status_liberacao text,
  bloqueio_credito boolean,
  bloqueio_estoque boolean,
  observacao text,
  carregado_em timestamptz not null default now()
);

create table if not exists stg.ordem_producao_item (
  id bigint generated always as identity primary key,
  sistema_origem text not null default 'TOTVS',
  filial text not null,
  pedido text,
  item text,
  ordem_producao text,
  emitida_em timestamptz,
  confirmada_em timestamptz,
  os_gerada_em timestamptz,
  status_producao text,
  quantidade_planejada numeric(18,6),
  quantidade_produzida numeric(18,6),
  carregado_em timestamptz not null default now()
);

create table if not exists stg.carga_item (
  id bigint generated always as identity primary key,
  sistema_origem text not null default 'TOTVS',
  filial text not null,
  pedido text,
  item text,
  carga text,
  montagem_carga_em timestamptz,
  tipo_carga text,
  status_carga text,
  carregado_em timestamptz not null default now()
);

-- Uma nota pode ter mais de uma linha para o mesmo pedido/item. Por isso,
-- faturamento é agregado antes de ser unido ao pedido_item.
create table if not exists stg.nota_item (
  id bigint generated always as identity primary key,
  sistema_origem text not null default 'TOTVS',
  filial text not null,
  pedido text,
  item text,
  nota_fiscal text,
  emitida_em timestamptz,
  saida_em timestamptz,
  quantidade_faturada numeric(18,6),
  peso_faturado_kg numeric(18,6),
  faturamento numeric(18,2),
  custo numeric(18,2),
  imposto numeric(18,2),
  margem numeric(18,2),
  carregado_em timestamptz not null default now()
);

-- Orçamento é mantido separado para aceitar orçamentos ainda não convertidos
-- em pedido. Ao ser convertido, pedido/item deve receber o vínculo abaixo.
create table if not exists stg.orcamento_item (
  sistema_origem text not null default 'TOTVS',
  filial text not null,
  orcamento text not null,
  item text not null,
  pedido_convertido text,
  item_pedido_convertido text,
  codigo_cliente text,
  loja_cliente text,
  codigo_vendedor text,
  codigo_produto text,
  emitido_em timestamptz,
  aprovado_em timestamptz,
  rejeitado_em timestamptz,
  validade_ate date,
  status_orcamento text,
  quantidade numeric(18,6),
  peso_kg numeric(18,6),
  valor_orcado numeric(18,2),
  codigo_motivo_perda text,
  carregado_em timestamptz not null default now(),
  primary key (sistema_origem, filial, orcamento, item)
);

-- ---------------------------------------------------------------------------
-- 3. ÍNDICES PARA AS CONSULTAS OPERACIONAIS E PARA AS CARGAS INCREMENTAIS
-- ---------------------------------------------------------------------------

create index if not exists ix_pedido_item_cliente on stg.pedido_item (filial, codigo_cliente);
create index if not exists ix_pedido_item_vendedor on stg.pedido_item (filial, codigo_vendedor);
create index if not exists ix_pedido_item_produto on stg.pedido_item (filial, codigo_produto);
create index if not exists ix_liberacao_pedido_item on stg.pedido_liberacao (filial, pedido, item, liberado_em desc);
create index if not exists ix_producao_pedido_item on stg.ordem_producao_item (filial, pedido, item, emitida_em desc);
create index if not exists ix_carga_pedido_item on stg.carga_item (filial, pedido, item, montagem_carga_em desc);
create index if not exists ix_nota_pedido_item on stg.nota_item (filial, pedido, item, emitida_em desc);
create index if not exists ix_orcamento_status on stg.orcamento_item (filial, status_orcamento, emitido_em);

-- ---------------------------------------------------------------------------
-- 4. VISÃO CANÔNICA: UMA LINHA POR PEDIDO/ITEM
-- ---------------------------------------------------------------------------

create or replace view analytics.vw_comercial_item_360
with (security_invoker = true)
as
with liberacao as (
  select
    sistema_origem, filial, pedido, item,
    max(liberado_em) as data_liberacao,
    bool_or(coalesce(bloqueio_credito, false)) as possui_bloqueio_credito,
    bool_or(coalesce(bloqueio_estoque, false)) as possui_bloqueio_estoque
  from stg.pedido_liberacao
  group by 1, 2, 3, 4
),
liberacao_pedido as (
  select
    sistema_origem, filial, pedido,
    max(liberado_em) as data_liberacao,
    bool_or(coalesce(bloqueio_credito, false)) as possui_bloqueio_credito,
    bool_or(coalesce(bloqueio_estoque, false)) as possui_bloqueio_estoque
  from stg.pedido_liberacao
  where item is null
  group by 1, 2, 3
),
producao as (
  select
    sistema_origem, filial, pedido, item,
    max(emitida_em) as data_emissao_op,
    max(confirmada_em) as data_confirmacao_op,
    max(os_gerada_em) as data_os,
    max(status_producao) filter (where status_producao is not null) as status_producao,
    sum(coalesce(quantidade_planejada, 0)) as quantidade_planejada_op,
    sum(coalesce(quantidade_produzida, 0)) as quantidade_produzida
  from stg.ordem_producao_item
  group by 1, 2, 3, 4
),
carga as (
  select
    sistema_origem, filial, pedido, item,
    max(montagem_carga_em) as data_montagem_carga,
    max(status_carga) filter (where status_carga is not null) as status_carga
  from stg.carga_item
  group by 1, 2, 3, 4
),
nota as (
  select
    sistema_origem, filial, pedido, item,
    max(emitida_em) as data_emissao_nf,
    max(saida_em) as data_saida,
    sum(coalesce(quantidade_faturada, 0)) as quantidade_faturada,
    sum(coalesce(peso_faturado_kg, 0)) as peso_faturado_kg,
    sum(coalesce(faturamento, 0)) as faturamento,
    sum(coalesce(custo, 0)) as custo_faturado,
    sum(coalesce(imposto, 0)) as imposto_faturado,
    sum(coalesce(margem, 0)) as margem_faturada
  from stg.nota_item
  group by 1, 2, 3, 4
),
orcamento as (
  select
    sistema_origem, filial, pedido_convertido, item_pedido_convertido,
    max(emitido_em) as data_orcamento,
    sum(coalesce(valor_orcado, 0)) as valor_orcado,
    max(aprovado_em) as data_aprovacao_orcamento,
    max(rejeitado_em) as data_rejeicao_orcamento,
    max(status_orcamento) filter (where status_orcamento is not null) as status_orcamento,
    max(codigo_motivo_perda) filter (where codigo_motivo_perda is not null) as codigo_motivo_perda
  from stg.orcamento_item
  where pedido_convertido is not null
  group by 1, 2, 3, 4
)
select
  concat_ws('|', pi.sistema_origem, pi.filial, pi.pedido, pi.item) as pedido_item_id,
  pi.sistema_origem,
  pi.filial,
  pi.pedido,
  pi.item,
  coalesce(o.data_orcamento, pc.data_orcamento) as data_orcamento,
  coalesce(o.status_orcamento, 'SEM_ORCAMENTO_VINCULADO') as status_orcamento,
  o.data_aprovacao_orcamento,
  o.data_rejeicao_orcamento,
  coalesce(o.valor_orcado, 0) as valor_orcado,
  pc.data_emissao_pv,
  coalesce(pi.data_desejo_cliente, pc.data_desejo_cliente) as data_desejo_cliente,
  coalesce(pi.data_sugerida_entrega, pc.data_previsao_entrega) as data_previsao_entrega,
  coalesce(l.data_liberacao, lp.data_liberacao) as data_liberacao,
  pr.data_emissao_op,
  pr.data_confirmacao_op,
  pr.data_os,
  ca.data_montagem_carga,
  n.data_emissao_nf,
  n.data_saida,
  pc.codigo_cliente,
  pc.loja_cliente,
  coalesce(pi.codigo_cliente, pc.codigo_cliente) as codigo_cliente_item,
  coalesce(pi.loja_cliente, pc.loja_cliente) as loja_cliente_item,
  coalesce(cl.nome_cliente, cl.nome_fantasia) as cliente,
  coalesce(cl.segmento_cliente, cl.classificacao_cliente, 'Não classificado') as segmento_cliente,
  cl.cidade,
  cl.uf,
  coalesce(pi.codigo_vendedor, pc.codigo_vendedor) as codigo_vendedor,
  vd.nome_vendedor as vendedor,
  vd.categoria_vendedor,
  vd.equipe as equipe_vendas,
  pi.codigo_produto,
  coalesce(prd.descricao_produto, pi.descricao_item) as produto,
  coalesce(prd.grupo_produto, pi.grupo_produto_origem, 'Não classificado') as grupo_produto,
  prd.subgrupo_produto,
  prd.familia_produto,
  prd.especificacao,
  pc.tipo_pedido,
  pc.tipo_frete,
  pc.rota,
  pi.unidade_medida,
  pi.quantidade_pedida,
  pi.quantidade_entregue,
  pi.quantidade_empenhada,
  pi.peso_kg as peso_pedido_kg,
  pi.preco_lista,
  pi.preco_unitario,
  pi.desconto_valor,
  pi.desconto_percentual,
  pi.valor_item as valor_pedido,
  pi.custo_medio as custo_pedido,
  pi.imposto_medio as imposto_pedido,
  n.quantidade_faturada,
  n.peso_faturado_kg,
  n.faturamento,
  n.custo_faturado,
  n.imposto_faturado,
  n.margem_faturada,
  case when coalesce(n.faturamento, 0) <> 0
       then n.margem_faturada / n.faturamento end as margem_faturada_percentual,
  coalesce(pi.perdido, false) or o.data_rejeicao_orcamento is not null as perdido,
  coalesce(o.codigo_motivo_perda, pi.codigo_motivo_perda) as codigo_motivo_perda,
  mp.motivo_perda,
  mp.grupo_motivo as grupo_motivo_perda,
  coalesce(l.possui_bloqueio_credito, lp.possui_bloqueio_credito, false) as bloqueio_credito,
  coalesce(l.possui_bloqueio_estoque, lp.possui_bloqueio_estoque, false) as bloqueio_estoque,
  pr.status_producao,
  ca.status_carga,
  case
    when n.data_saida is not null then 'FATURADO_EXPEDIDO'
    when n.data_emissao_nf is not null then 'NF_EMITIDA'
    when ca.data_montagem_carga is not null then 'CARGA_MONTADA'
    when pr.data_confirmacao_op is not null then 'PRODUCAO_CONFIRMADA'
    when pr.data_emissao_op is not null then 'EM_PRODUCAO'
    when coalesce(l.possui_bloqueio_credito, lp.possui_bloqueio_credito, false) then 'BLOQUEIO_CREDITO'
    when coalesce(l.possui_bloqueio_estoque, lp.possui_bloqueio_estoque, false) then 'AGUARDANDO_ESTOQUE'
    when coalesce(l.data_liberacao, lp.data_liberacao) is not null then 'LIBERADO_AGUARDANDO_FLUXO'
    when coalesce(pi.perdido, false) or o.data_rejeicao_orcamento is not null then 'PERDIDO_OU_REJEITADO'
    else 'PEDIDO_EMITIDO'
  end as etapa_atual,
  case
    when n.data_saida is not null and coalesce(pi.data_desejo_cliente, pc.data_desejo_cliente) is not null
      then case when n.data_saida::date <= coalesce(pi.data_desejo_cliente, pc.data_desejo_cliente)
                then 'ATENDIDO_NO_PRAZO' else 'ENTREGUE_COM_ATRASO' end
    when n.data_saida is null and coalesce(pi.data_desejo_cliente, pc.data_desejo_cliente) < current_date
      then 'PRAZO_VENCIDO'
    when coalesce(pi.data_desejo_cliente, pc.data_desejo_cliente) is null then 'SEM_DATA_DESEJO'
    else 'NO_PRAZO'
  end as status_prazo_cliente,
  greatest(pi.carregado_em, pc.carregado_em, coalesce(n.carregado_em, '-infinity'::timestamptz)) as atualizado_em
from stg.pedido_item pi
join stg.pedido_cabecalho pc
  on pc.sistema_origem = pi.sistema_origem
 and pc.filial = pi.filial
 and pc.pedido = pi.pedido
left join stg.cliente cl
  on cl.sistema_origem = pi.sistema_origem
 and cl.filial = pi.filial
 and cl.codigo_cliente = coalesce(pi.codigo_cliente, pc.codigo_cliente)
 and cl.loja = coalesce(pi.loja_cliente, pc.loja_cliente, '')
left join stg.vendedor vd
  on vd.sistema_origem = pi.sistema_origem
 and vd.filial = pi.filial
 and vd.codigo_vendedor = coalesce(pi.codigo_vendedor, pc.codigo_vendedor)
left join stg.produto prd
  on prd.sistema_origem = pi.sistema_origem
 and prd.filial = pi.filial
 and prd.codigo_produto = pi.codigo_produto
left join liberacao l
  on l.sistema_origem = pi.sistema_origem and l.filial = pi.filial
 and l.pedido = pi.pedido and l.item = pi.item
left join liberacao_pedido lp
  on lp.sistema_origem = pi.sistema_origem and lp.filial = pi.filial and lp.pedido = pi.pedido
left join producao pr
  on pr.sistema_origem = pi.sistema_origem and pr.filial = pi.filial
 and pr.pedido = pi.pedido and pr.item = pi.item
left join carga ca
  on ca.sistema_origem = pi.sistema_origem and ca.filial = pi.filial
 and ca.pedido = pi.pedido and ca.item = pi.item
left join nota n
  on n.sistema_origem = pi.sistema_origem and n.filial = pi.filial
 and n.pedido = pi.pedido and n.item = pi.item
left join orcamento o
  on o.sistema_origem = pi.sistema_origem and o.filial = pi.filial
 and o.pedido_convertido = pi.pedido and o.item_pedido_convertido = pi.item
left join stg.motivo_perda mp
  on mp.sistema_origem = pi.sistema_origem
 and mp.codigo_motivo = coalesce(o.codigo_motivo_perda, pi.codigo_motivo_perda);

comment on view analytics.vw_comercial_item_360 is
  'Visão canônica na granularidade filial/pedido/item. Use para valores, margem, mix, clientes e vendedores.';

-- ---------------------------------------------------------------------------
-- 5. TRILHA DO FUNIL: UMA LINHA POR EVENTO DE CADA PEDIDO/ITEM
-- ---------------------------------------------------------------------------
-- Esta visão é a fonte do funil. Nunca some valores de etapas; escolha uma
-- etapa atual por pedido/item (campo etapa_atual da visão canônica).

create or replace view analytics.vw_fluxo_evento_360
with (security_invoker = true)
as
select pedido_item_id, sistema_origem, filial, pedido, item,
       'ORCAMENTO_EMITIDO'::text as evento, data_orcamento::timestamptz as data_evento,
       valor_orcado as valor_referencia, peso_pedido_kg as peso_referencia
from analytics.vw_comercial_item_360 where data_orcamento is not null
union all
select pedido_item_id, sistema_origem, filial, pedido, item,
       'PEDIDO_EMITIDO', data_emissao_pv::timestamptz, valor_pedido, peso_pedido_kg
from analytics.vw_comercial_item_360 where data_emissao_pv is not null
union all
select pedido_item_id, sistema_origem, filial, pedido, item,
       'PEDIDO_LIBERADO', data_liberacao, valor_pedido, peso_pedido_kg
from analytics.vw_comercial_item_360 where data_liberacao is not null
union all
select pedido_item_id, sistema_origem, filial, pedido, item,
       'OP_EMITIDA', data_emissao_op, valor_pedido, peso_pedido_kg
from analytics.vw_comercial_item_360 where data_emissao_op is not null
union all
select pedido_item_id, sistema_origem, filial, pedido, item,
       'OP_CONFIRMADA', data_confirmacao_op, valor_pedido, peso_pedido_kg
from analytics.vw_comercial_item_360 where data_confirmacao_op is not null
union all
select pedido_item_id, sistema_origem, filial, pedido, item,
       'CARGA_MONTADA', data_montagem_carga, valor_pedido, peso_pedido_kg
from analytics.vw_comercial_item_360 where data_montagem_carga is not null
union all
select pedido_item_id, sistema_origem, filial, pedido, item,
       'NF_EMITIDA', data_emissao_nf, faturamento, peso_faturado_kg
from analytics.vw_comercial_item_360 where data_emissao_nf is not null
union all
select pedido_item_id, sistema_origem, filial, pedido, item,
       'SAIDA_REALIZADA', data_saida, faturamento, peso_faturado_kg
from analytics.vw_comercial_item_360 where data_saida is not null;

comment on view analytics.vw_fluxo_evento_360 is
  'Eventos cronológicos para lead time e rastreio do funil. Valores de etapas não são aditivos.';

-- ---------------------------------------------------------------------------
-- 6. CONSULTAS DE VALIDAÇÃO PÓS-CARGA (executar após a primeira carga)
-- ---------------------------------------------------------------------------
--
-- Atualidade da carga:
-- select max(atualizado_em) as ultima_carga, count(*) as itens
-- from analytics.vw_comercial_item_360;
--
-- Verificação de duplicidade no grão canônico (precisa retornar zero linhas):
-- select pedido_item_id, count(*)
-- from analytics.vw_comercial_item_360
-- group by 1 having count(*) > 1;
--
-- Reconciliação de faturamento contra a origem (o valor deve coincidir):
-- select sum(faturamento) from analytics.vw_comercial_item_360;
-- select sum(faturamento) from stg.nota_item;
--
-- Funil por etapa atual (cada pedido/item aparece uma única vez):
-- select etapa_atual, count(*) as itens, sum(valor_pedido) as valor_pedido
-- from analytics.vw_comercial_item_360
-- group by 1 order by 2 desc;

-- Cria um TENANT: um schema e um papel do Postgres que só enxerga esse schema.
--
-- Rode no SQL Editor do Supabase. Antes de executar, troque os dois valores abaixo.
--
-- ===========================================================================
-- TOPOLOGIA (dois projetos Supabase, um por tenant — cabe no plano gratuito,
-- que permite exatamente 2 projetos ativos):
--
--   Projeto PRIVADO  ->  schema `gm`     papel `gm_app`     dados reais
--   Projeto DEMO     ->  schema `demo`   papel `gm_demo`    dados inventados
--
-- Bancos separados já impedem a vitrine de alcançar o dado real: são servidores
-- e credenciais diferentes. O schema e o papel restrito continuam valendo como
-- SEGUNDA camada — se um dia alguém apontar a vitrine para o banco errado, o
-- papel não tem permissão e a conexão falha em vez de vazar.
--
-- Errar a URL de conexão é o tipo de engano que acontece às duas da manhã.
-- ===========================================================================

\set tenant   'demo'      -- 'gm' no projeto privado
\set papel    'gm_demo'   -- 'gm_app' no projeto privado
\set senha    'TROQUE-ESTA-SENHA'

BEGIN;

-- 1. O schema do tenant.
CREATE SCHEMA IF NOT EXISTS :"tenant";

-- 2. O papel que a aplicação usa para conectar.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'papel') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'papel', :'senha');
  END IF;
END
$$;

-- 3. O search_path vem do PAPEL, não da aplicação.
--    Assim vale em qualquer conexão, inclusive através do PgBouncer, onde um `SET`
--    avulso pode não sobreviver à troca de conexão física entre transações.
ALTER ROLE :"papel" SET search_path = :"tenant";

-- 4. Permissões: tudo no schema do tenant.
GRANT USAGE, CREATE ON SCHEMA :"tenant" TO :"papel";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA :"tenant" TO :"papel";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA :"tenant" TO :"papel";
-- As migrações criam tabelas DEPOIS desta execução; sem isto elas nasceriam sem
-- permissão para o próprio papel que as criou usar em conexões futuras.
ALTER DEFAULT PRIVILEGES IN SCHEMA :"tenant" GRANT ALL ON TABLES TO :"papel";
ALTER DEFAULT PRIVILEGES IN SCHEMA :"tenant" GRANT ALL ON SEQUENCES TO :"papel";

-- 5. A linha que faz o desenho valer. Sem ela, `PUBLIC` (todo papel) herda USAGE em
--    `public` por padrão no Postgres — e o tenant leria o que houver lá.
REVOKE ALL ON SCHEMA public FROM :"papel";
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM :"papel";

COMMIT;

-- ---------------------------------------------------------------------------
-- CONFERIR — conectado COMO o papel criado, isto tem que dar "permission denied":
--
--   SELECT count(*) FROM public.vehicles;
--
-- Se devolver um número em vez de erro, o isolamento NÃO está de pé.
-- No tenant de demonstração, não publique a credencial antes de ver o erro.
--
-- Depois, a aplicação sobe com:
--   DATABASE_URL=...  (usuário = o papel criado aqui)
--   DB_SCHEMA=demo    (ou gm)
-- e as migrações criam as tabelas dentro do schema sozinhas.
-- ---------------------------------------------------------------------------

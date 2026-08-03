# CLAUDE.md — GM Locações (ERP de Frota)

ERP de frota de uma locadora de veículos para motoristas de app. **Repositório público.**

```
Lucro do veículo = receitas − despesas − valor_compra + valor_venda
```

Tudo existe para alimentar essa conta. Mudança que corrompe esse número está errada, por mais
bonita que seja.

## Arquitetura

**Este repositório é o primeiro sistema, e é peça de portfólio — público, de propósito.**

Existe um **segundo** sistema, `gm-locacoes`: uma reescrita em Node/TypeScript (Fastify + Prisma
+ React + React Native), privada, e é ela que está em produção. A reescrita foi decisão do dono —
TypeScript em toda a stack e app Android nativo —, **não falha deste projeto**: este chegou a 12
domínios, 43 endpoints e rodou com dado real.

Consequência prática: **este repositório é a fonte das regras de negócio.** As armadilhas listadas
no fim deste arquivo custaram sessões inteiras e foram descobertas aqui, com dado real. Reescrever
não é motivo para redescobrir.

Não há mescla entre os dois: linguagens diferentes, históricos sem ancestral comum.

```
backend/             FastAPI + SQLAlchemy 2 + Alembic (Python 3.13)
  run_server.py        entrada do .exe;  erp-frota-api.spec  receita do PyInstaller
  app/core/            config · errors · security · context · storage · paths
  app/db/              session · base (base.py importa TODOS os models)
  app/domains/<dom>/   models · schemas · service · router
frontend/            React 19 + TS + Vite + Tailwind + TanStack Query
desktop/             Electron: Postgres embutido -> backend -> janela
  vendor/pgsql/        Postgres portátil (fora do git, ~300 MB, baixado uma vez)
scripts/             iniciar-erp · web · backup · demo · seed_demo
Dockerfile           imagem única (React compilado + API) para Render/Railway/Fly
render.yaml          variáveis do deploy — sem nenhum segredo, o público lê isto
```

**O Docker acabou.** O banco era um container (`docker-compose.yml`) e hoje é o Postgres
portátil de `desktop/vendor/pgsql`, que sobe como processo comum. O arquivo foi **removido** —
está no histórico do git se um dia fizer falta. Não o traga de volta sem motivo: ele custava um
pré-requisito pesado (Docker Desktop instalado e rodando) para quem só quer abrir o programa,
e este é um sistema de uma máquina só.

**Portas:** 5434 banco · 8010 API · 5273 Vite. Não são as padrão de propósito — 5432/5433, 8000
e 5173 já estão ocupadas por outros projetos.

**A API serve a interface compilada** (`frontend/dist` → `static/`). Funciona porque as rotas da
interface são em português (`/veiculos`) e as da API em inglês (`/vehicles`): não colidem. O
catch-all da SPA fica **por último** no `main.py` — não registre rota depois dele.

## Rodar (dev)

```bash
desktop/vendor/pgsql/bin/pg_ctl -D "%LOCALAPPDATA%\GM Locacoes\pgdata" -o "-p 5434" -w start
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8010
cd frontend && npm run dev
```

Login: senha sorteada no 1º boot, em `%LOCALAPPDATA%\GM Locacoes\senha-inicial-admin.txt`.

Os quatro scripts, e quando usar cada um:

| | |
|---|---|
| `iniciar-erp.ps1` | abre o sistema nesta máquina (o `GM Locações.cmd` chama este) |
| `web.ps1` | expõe na rede local, para acessar do celular — **HTTP, só rede de casa** |
| `demo.ps1` | vitrine isolada na 8011, banco próprio, apagado ao sair |
| `backup.ps1 -Verificar` | copia banco **e** arquivos, e prova que a cópia restaura |

## Regras permanentes

1. **Dinheiro é `Decimal` / `Numeric(12,2)`. NUNCA `float`.** Em ERP financeiro, `float` é bug
   de dinheiro. A API entrega dinheiro como string; o frontend só exibe, nunca calcula.
2. **Migração Alembic para toda mudança de schema.** Nunca `Base.metadata.create_all`.
3. **Services nunca usam bulk DML** (`session.execute(update(...))`, `query.delete()`) em tabela
   auditada. O listener de auditoria é cego a isso e o log fica com buraco. Carregue o objeto e
   altere o atributo.
4. **Não duplicar fato financeiro.** Compra, venda e caução moram em UM lugar só
   (`vehicles.purchase_price`, `vehicles.sale_price`, `contracts.deposit_amount`). Criar
   categoria de receita para venda ou caução conta o lucro em dobro. Decidido — não reintroduzir.
   A caução vira receita (`caucao_retida`) só na parte retida ao encerrar o contrato.
5. **Endpoint sem consumo no frontend é endpoint NÃO ENTREGUE.** Adicione a tela e teste ponta a
   ponta na mesma sessão. Não é formalidade: em duas sessões apareceram **três** casos —
   `PATCH /vehicles` (dava para corrigir o valor de compra só por SQL), `POST /users` (não havia
   tela de usuários) e, no outro sistema, `POST /files` (nenhum `input type="file"` existia).
   Ninguém percebe porque nada quebra: a funcionalidade simplesmente não existe.
   **Ainda em aberto aqui:** contratos, manutenções e multas têm `PATCH`/`DELETE` sem tela.
6. **Ao final de CADA sessão, atualize o `BACKLOG.md`** (data, o que foi feito, decisões, pendências).
7. Peça confirmação antes de ação destrutiva (deletar, force-push, `alembic downgrade`).
8. Identificadores em inglês; comentários e UI em português. Commits `tipo: descrição` em
   português (feat/fix/docs/refactor/test).

## Segurança (o repositório é PÚBLICO)

1. **Nenhum segredo no código-fonte.** Senha padrão em repositório aberto é senha de todo mundo.
   `ADMIN_PASSWORD` vazio → o seed sorteia e entrega em arquivo. `SECRET_KEY` é sorteado por
   instalação (`paths.installation_secret`). Fora de `ENV=dev`, subir com o segredo padrão é erro
   fatal por decisão (`config.py`).
2. **Nunca versionar:** `.env`, `secret.key`, `senha-inicial-admin.txt`, `storage/`,
   `desktop/vendor/`, `pgdata/`. Antes de commitar, confira o `git status`.
3. **LGPD.** CNH, CPF, contratos e fotos são dado pessoal. `storage/` **nunca** é servido como
   pasta estática — download só pelo endpoint autenticado `GET /files/{key}`.
4. **Nunca logar** senha, token, hash, CPF ou CNH. Nem em `logger.debug`, nem em mensagem de erro.
5. **Nunca retornar `hashed_password`** em schema Pydantic de saída.
6. **Dado de teste é inventado.** Nenhum motorista, placa ou CPF real em fixture, seed ou doc.
7. **Dois modos, duas premissas.** No desktop, o banco escuta só em `localhost` e sem senha
   (`-A trust`) porque é banco de uma máquina só. **Em nuvem isso não vale**: Supabase com
   senha e SSL, `ENV=production`, e o boot falha sem `SECRET_KEY` forte e `ADMIN_PASSWORD`
   (ver `config.py`). Nunca leve o `-A trust` para fora da máquina.
8. **Em nuvem, disco de container é efêmero.** `STORAGE_BACKEND=supabase`, senão foto de
   vistoria e contrato assinado somem no deploy seguinte. `SECRET_KEY` fixo por variável de
   ambiente — sorteado a cada deploy deslogaria todo mundo.
9. **Pooler do Supabase (6543) exige `prepare_threshold=None` e `NullPool`.** Ele reaproveita
   conexões entre transações e derruba os prepared statements do psycopg. O erro é
   `prepared statement "_pg3_0" does not exist`, intermitente e só sob carga. Já tratado em
   `db/session.py`, detectado pelo host — não desfaça.

## Economia de contexto

O que mantém uma sessão barata neste repo:

- **Não leia arquivo inteiro.** `Grep` para achar, `Read` com `offset`/`limit` na faixa. Os
  domínios são pequenos e repetitivos: ler um `router.py` já ensina o padrão dos outros.
- **Não rode a suíte toda para validar um domínio.** `pytest tests/test_money.py -q`. A suíte
  completa (177 testes, ~75 s) fica para o fim da sessão.
- **`npm run build` é a verificação que vale**, não `tsc --noEmit`. O build roda `tsc -b`, que é
  mais estrito e pega erro que o `--noEmit` deixa passar (aconteceu com uma união de tipos).
- **Nunca leia** `package-lock.json`, `desktop/vendor/`, `.venv/`, `node_modules/`, `dist/`.
- **Não repita aqui o que já está no código.** Este arquivo entra no contexto toda sessão; ele
  guarda o que NÃO dá para descobrir lendo o repositório — decisões e armadilhas.
- **Uma entrada por sessão no BACKLOG**, curta. Histórico antigo se condensa, não se acumula.

## Teste verde que não testa nada é pior que teste nenhum

Numa sessão só, três testes foram escritos que passavam sem provar coisa alguma. Antes de
comemorar um teste novo que passou de primeira, **desconfie**:

- **Instrumentação desligada.** Um contador de consultas do Prisma lia sempre zero, porque o
  cliente não emitia evento de `query`. `0 <= 0 + 2` passava.
- **Passar por ausência.** Um teste afirmava que certa consulta *não* montava um `IN` com ids —
  e passaria também se a consulta nem acontecesse. A cura é exigir antes que a coisa tenha
  acontecido.
- **Asserção sobre campo inexistente.** `assert.equal(x.netCost, ...)` com `netCost` `undefined`
  falha por engano, não por bug — e a versão "corrigida" com `?? 0` teria passado sempre.

**Se um teste passa de primeira, quebre o código de propósito e confirme que ele falha.**

## Armadilhas mapeadas (não recaia)

### Domínio

- `custo_por_km` divide por `(current_odometer − purchase_odometer)`; `roi` divide por
  investimento. Carro novo ou `purchase_price = 0` → **divisão por zero**. Retornar `NULL`, não 500.
- Inadimplência é **derivada** (`status IN ('pending','partial') AND due_date < hoje`), não
  armazenada. Não criar job noturno.
- Cobrança semanal é **idempotente** via `UNIQUE(contract_id, period_start)`. Pode rodar a cada boot.
- **Vender carro com contrato ativo → 409.** Senão a geração semanal criaria aluguel para um carro
  que não é mais do dono, e a caução ficaria presa.
- `payback` cobre só a OPERAÇÃO (a venda não entra). Carro vendido que não se pagou rodando
  devolve vazio — projetar prazo para um carro que não é mais seu seria mentira.

### Ambiente

- **Python 3.13, não 3.14.** `pydantic-core==2.33.2` não tem wheel `cp314` e o PyO3 0.24.1 recusa
  Python acima do 3.13 — o pip cai em compilação Rust e falha.
- **`pg_ctl start` trava se a saída for canalizada no PowerShell.** O servidor herda o handle de
  stdout e o pipeline nunca fecha. Redirecione para arquivo; não use `|`.
- **`npm start` em `desktop/` falha DENTRO do VS Code**: ele define `ELECTRON_RUN_AS_NODE=1` e o
  `require('electron')` devolve um caminho. Use terminal normal.
- **`npm run dist` exige o Modo de desenvolvedor do Windows** (electron-builder cria symlinks).

### Empacotamento

- **`get_current_user` PRECISA ser `async def`.** Dependência síncrona roda numa thread com uma
  *cópia* do contexto: o `set_actor()` escreveria numa cópia descartável e todo log de auditoria
  sairia como `"sistema"`.
- **O `.exe` roda com `console=False`** → `sys.stdout` é `None` e o uvicorn chama `.isatty()` nele.
  Por isso o `run_server.py` redireciona as saídas para arquivo ANTES de subir o uvicorn. Log em
  arquivo é a única pista quando o app não abre na máquina de quem instalou.
- **O `.spec` usa `collect_submodules("app")`, não `"app.main"`.** O Alembic lê `migrations/env.py`
  do disco em tempo de execução, e o `from app.db.base import Base` de lá é invisível ao PyInstaller.
- **Program Files não é gravável.** Tudo que o app escreve vai para `%LOCALAPPDATA%\GM Locacoes\`
  (ver `app/core/paths.py`).

## Estado atual

Topo do `BACKLOG.md`.

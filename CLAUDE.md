# CLAUDE.md — GM Locações (ERP de Frota)

Guia do projeto para o Claude Code. **Leia no início de cada sessão.**

## O que é

ERP de gestão de frota para uma **locadora de veículos para motoristas de aplicativo** (Uber), de
Guilherme Melo. Não é um CRUD de carros: é o sistema operacional da empresa.

O nome do produto é **GM Locações**. A pasta do repositório ainda é `erp-frota-v1` (não renomeie: o
nome do projeto Docker vem daí, e mudá-lo criaria um volume novo — o banco apareceria vazio).

**A funcionalidade central — tudo o mais existe para alimentá-la:**

```
Lucro do veículo = receitas − despesas − valor_compra + valor_venda
```

Se uma mudança corrompe esse número, ela está errada, por mais bonita que seja.

## Arquitetura

```
erp-frota-v1/
├── docker-compose.yml     Postgres 16 (porta 5434)
├── storage/               arquivos enviados (fora do git)
├── backend/               FastAPI + SQLAlchemy 2 + Alembic (Python 3.13)
│   ├── run_server.py      entrada do .exe empacotado
│   ├── erp-frota-api.spec receita do PyInstaller
│   └── app/
│       ├── core/          config · errors · security · context · storage · paths
│       ├── db/            session · base (base.py importa TODOS os models)
│       └── domains/       um pacote por domínio: models · schemas · service · router
├── frontend/              React 19 + TS + Vite + Tailwind + TanStack Query
└── desktop/               Electron: janela + orquestração (Docker -> backend -> UI)
```

**Portas:** 5434 (banco), 8010 (API), 5273 (Vite em dev). Não são as padrão de propósito — 5432/5433,
8000 e 5173 já estão ocupadas nesta máquina por outros projetos.

**A API serve a interface compilada** (`frontend/dist` → `static/` dentro do .exe). Funciona porque as
rotas da interface são em português (`/veiculos`) e as da API em inglês (`/vehicles`): **não colidem**.
O catch-all da SPA fica por último no `main.py` — não registre rota nova depois dele.

## Como rodar (dev)

```bash
docker compose up -d                       # Postgres em localhost:5434
cd backend && alembic upgrade head
uvicorn app.main:app --reload              # http://127.0.0.1:8000  (docs em /docs)
cd frontend && npm run dev                 # http://localhost:5173
```

Existe a skill `rodar-erp` com o passo a passo.

## Convenções

- **Identificadores em inglês; comentários e textos de UI em português.**
- Commits em português, formato `tipo: descrição` (feat/fix/docs/refactor/test).
- Backend: um pacote por domínio; schemas Pydantic para entrada e saída; nunca retornar `hashed_password`.
- Frontend: TanStack Query para servidor, React Hook Form + Zod nos formulários. Sem estado global de dados.
- Não versionar `node_modules/`, `.venv/`, `.env`, `storage/`.

## Regras permanentes (IMPORTANTE)

1. **Dinheiro é sempre `Decimal` / `Numeric(12,2)`. NUNCA `float`.** Em ERP financeiro, `float` é bug de dinheiro.
2. **Migração Alembic para toda mudança de schema.** Nunca `Base.metadata.create_all`.
3. **Services nunca usam bulk DML** (`session.execute(update(...))`, `query.delete()`) **em tabela auditada.**
   O listener de auditoria é cego a isso e o log fica com buraco. Sempre carregue o objeto e altere o atributo.
4. **Não duplicar fato financeiro.** Valor de compra, valor de venda e caução moram em UM lugar só
   (`vehicles.purchase_price`, `vehicles.sale_price`, `contracts.deposit_amount`). Criar categoria de
   receita para venda ou caução conta o lucro em dobro. Já foi decidido — não reintroduzir.
5. **`storage/` nunca é servido como pasta estática.** CNH, CPF e contratos são dado pessoal (LGPD).
   Downloads só pelo endpoint autenticado `GET /files/{key}`.
6. Ao adicionar um endpoint, adicione o consumo no frontend e teste ponta a ponta na mesma sessão.
7. **Ao final de CADA sessão, atualize o `BACKLOG.md`** (data, o que foi feito, decisões, pendências).
8. Peça confirmação antes de ações destrutivas (deletar, force-push, `alembic downgrade`).

## Armadilhas já mapeadas (não recaia nelas)

### Domínio

- `custo_por_km` divide por `(current_odometer − purchase_odometer)` → carro novo dá **divisão por zero**. Retornar `NULL`, não 500.
- `roi` divide por `investimento` → carro com `purchase_price = 0` idem.
- Inadimplência é **derivada** (`status IN ('pending','partial') AND due_date < hoje`), não armazenada. Não criar job noturno.
- Geração de cobrança é **idempotente** via `UNIQUE(contract_id, period_start)`. Pode rodar toda vez que o app abre.
- **Vender carro com contrato ativo é recusado (409).** Se não fosse, a geração semanal continuaria
  criando aluguel para um carro que não é mais do dono, e a caução ficaria presa.
- `payback` é calculado só sobre a OPERAÇÃO (a venda não entra). Para carro vendido que não se pagou
  rodando, devolve vazio — projetar prazo para um carro que não é mais seu seria mentira.

### Empacotamento (app de desktop)

- **`get_current_user` PRECISA ser `async def`.** Dependência síncrona roda numa thread com uma
  *cópia* do contexto: o `set_actor()` escreveria numa cópia descartável e todo log de auditoria
  sairia como `"sistema"`.
- **O `.exe` roda com `console=False`** → `sys.stdout` é `None` e o uvicorn chama `.isatty()` nele.
  Por isso o `run_server.py` redireciona as saídas para um arquivo ANTES de subir o uvicorn.
  Log em arquivo não é conforto: é a única pista quando o app não abre na máquina de quem instalou.
- **O `.spec` usa `collect_submodules("app")`, não `"app.main"`.** O Alembic lê `migrations/env.py` do
  disco em tempo de execução, e o `from app.db.base import Base` de lá é invisível ao PyInstaller.
- **Program Files não é gravável.** Tudo que o app escreve (fotos, `secret.key`) vai para
  `%LOCALAPPDATA%\GM Locacoes\` (ver `app/core/paths.py`).
- **`npm start` em `desktop/` falha DENTRO do VS Code**: ele define `ELECTRON_RUN_AS_NODE=1`, e aí o
  Electron roda como Node puro e `require('electron')` devolve um caminho. Use terminal normal.
- **`npm run dist` exige o Modo de desenvolvedor do Windows ligado** (o electron-builder cria symlinks).

## Estado atual

Veja o topo do `BACKLOG.md`.

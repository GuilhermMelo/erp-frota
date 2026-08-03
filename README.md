# GM Locações — ERP de Frota

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Electron](https://img.shields.io/badge/Electron-33-47848F?logo=electron&logoColor=white)
![Testes](https://img.shields.io/badge/testes-113%20passando-brightgreen)

ERP de gestão de frota para uma locadora de veículos de motoristas de aplicativo.
Backend em FastAPI, interface em React, empacotado como app de desktop que instala com um clique —
sem Docker, sem Python, sem terminal na máquina de quem usa.

![A conta do veículo](docs/img/conta-do-veiculo.png)

> *A tela central: a equação do lucro com cada parcela clicável. Todos os dados destas imagens são
> fictícios — placas, nomes e CPFs foram inventados para a demonstração.*

---

## O problema

Uma locadora de carros para motoristas de app vive de uma conta que quase nunca é feita direito:
**este carro específico deu lucro?** A resposta se esconde numa planilha onde a caução virou
receita, o valor de compra foi lançado duas vezes e a multa reembolsada pelo motorista aparece
como prejuízo.

O sistema existe para responder **uma** pergunta com precisão:

```
Lucro do veículo = receitas − despesas − valor de compra + valor de venda
```

Contratos, vistorias, manutenções e multas não são módulos por serem bonitos de ter.
Cada um existe porque alimenta um termo dessa equação.

## As três armadilhas de contagem dupla

Três fatos inflariam o lucro se fossem modelados como receita ou despesa comum. Cada um mora em
**um lugar só** — e isso é regra do sistema, não preferência de estilo:

| Fato | Onde mora | Se virasse lançamento comum |
|---|---|---|
| Valor de compra | `vehicles.purchase_price` | Custo contado em dobro |
| Valor de venda | `vehicles.sale_price` | Lucro contado em dobro |
| **Caução** | `contracts.deposit_amount` | Lucro inflado até você devolver — **a caução não é sua** |

A caução só vira receita (`caucao_retida`) na parte efetivamente retida ao encerrar o contrato.

**Multas seguem a lógica inversa, de propósito:** a despesa é registrada **sempre** que você paga.
Se o motorista reembolsa, entra uma receita ligada à mesma multa e o líquido zera sozinho.
Registrar só as não-reembolsadas perderia o rastro de quanto você já desembolsou e de quanto cada
motorista te deve.

---

## O que o sistema faz

| Módulo | O que resolve |
|---|---|
| **Veículos** | Cadastro a partir do valor de compra. A ação **"Vender"** fecha o ciclo e trava o resultado. |
| **A conta do veículo** | A tela central. Mostra a equação do lucro e **cada número é clicável**, abrindo os lançamentos que o compõem. Mais ROI, payback e custo/km. |
| **Motoristas** | Cadastro com CNH e destaque de vencimento. Motorista **não tem login** — é dado, não usuário. |
| **Contratos** | Carro + motorista + valor semanal + caução, com anexos. **Gera as cobranças semanais sozinho.** |
| **Cobranças** | Inadimplência: quem deve o quê, há quantos dias. |
| **Receitas / Despesas** | Lançamentos amarrados a um veículo. Categorias editáveis, com marcação de investimento (capex). |
| **Manutenções** | Histórico (descrição, valor, KM, data). **Gera a despesa automaticamente.** |
| **Multas** | Vinculadas ao carro e ao motorista. Pagar gera despesa; reembolso gera receita. |
| **Vistorias** | Checklist estruturado + até 200 fotos (comprimidas no navegador) + foto da assinatura. |
| **Auditoria** | Log append-only de quem mudou o quê, com o "de → para". |

![Painel](docs/img/dashboard.png)

*O painel: situação da frota, resultado do mês, o que está vencido e a série de receita × despesa
desde o primeiro carro.*

![Lista de veículos](docs/img/veiculos.png)

*A frota inteira com o lucro de cada carro na última coluna. A frota de demonstração cobre os
quatro estados que importam: um quase no ponto de equilíbrio, um ainda em formação, um vendido com
o ciclo fechado e um comprado na semana passada — o caso em que ROI e custo/km dividiriam por zero.*

O CAR000001 é o exemplo que amarra as duas telas seguintes: está a **R$ 640 de se pagar** e tem
**R$ 1.550 em aberto**. Ele já estaria no azul se o motorista estivesse em dia — e é por isso que
cobrança em aberto **nunca** entra no lucro. Contar dinheiro que não entrou é como a planilha mente.

![Cobranças e inadimplência](docs/img/cobrancas.png)

*Inadimplência não é um campo no banco: é `status IN ('pending','partial') AND due_date < hoje`,
calculado na hora. Sem job noturno e sem estado que fica velho se o job falhar.*

---

## Decisões técnicas

**Dinheiro é `Decimal` / `Numeric(12,2)` ponta a ponta.** Nenhum `float` em lugar nenhum. A API
entrega valores monetários como *string* para o JavaScript não estragar na desserialização, e o
frontend **nunca** faz conta de dinheiro — só exibe. Em ERP financeiro, `float` é bug de dinheiro
esperando data para acontecer.

**Auditoria por event listener do SQLAlchemy, não por chamada no service.** Chamar
`registrar_auditoria()` em cada service é justamente o que o humano cansado esquece — e log com
buraco é pior que log nenhum. O listener não tem como esquecer. O preço: services não podem usar
bulk DML (`session.execute(update(...))`) em tabela auditada, porque o listener é cego a isso.

**Cobrança semanal idempotente** por `UNIQUE(contract_id, period_start)`. Roda toda vez que o app
abre, sem cron, sem fila e sem duplicar. A garantia é do banco, não do código de aplicação.

**Inadimplência é derivada**, não armazenada: `status IN ('pending','partial') AND due_date < hoje`.
Sem job noturno e sem um campo que fica velho se o job falhar.

**Vender carro com contrato ativo é recusado (409).** Se não fosse, a geração semanal continuaria
criando aluguel para um carro que não é mais do dono, e a caução ficaria presa.

**Divisão por zero devolve `NULL`, não 500.** `custo_por_km` divide pela quilometragem rodada e
`roi` divide pelo investimento — carro recém-comprado zera os dois denominadores. É o caso normal
no primeiro dia de uso, não uma exceção.

**Alembic desde o primeiro commit**, nunca `create_all` — inclusive nos testes, que rodam contra o
mesmo schema que vai para produção, com os `CHECK`s e índices parciais que *são* a regra de negócio.

**Códigos legíveis** (`CAR000001`, `CTR000001`) vêm de sequences do Postgres. A chave primária é
UUID; o código nunca é PK.

**Postgres embutido, não instalado.** O app carrega um Postgres 16 portátil e o sobe sozinho.
Quem instala não vê banco, não vê Docker e não vê terminal.

**Fotos comprimidas no navegador** (1600 px, JPEG 0.8) antes do upload: 200 fotos de celular caem
de ~1 GB para ~20 MB.

---

## Segurança e LGPD

O repositório é público. Isso é uma decisão, e ela impõe regras:

- **Nenhuma senha no código-fonte.** Senha padrão em repositório aberto é senha de todo mundo.
  O admin é criado no primeiro boot com uma senha **sorteada** (`secrets.token_urlsafe`), entregue
  em `%LOCALAPPDATA%\GM Locacoes\senha-inicial-admin.txt` — arquivo que pede para ser apagado após
  o primeiro acesso.
- **Segredo do JWT sorteado por instalação.** Sem isso, todas as instalações compartilhariam o
  segredo do código-fonte e qualquer um forjaria um token de admin. Fora de `ENV=dev`, subir com o
  segredo padrão é erro fatal por decisão.
- **`storage/` nunca é servido como pasta estática.** CNH, CPF e contratos são dado pessoal:
  download só pelo endpoint autenticado `GET /files/{key}`.
- **Nada de dado real em teste.** Nenhum motorista, placa ou CPF verdadeiro em fixture ou seed.
- O banco escuta apenas em `localhost` — é um banco de uma máquina só.

---

## Arquitetura

```
backend/             FastAPI · SQLAlchemy 2 · Alembic · Python 3.13
  app/core/            config · errors · security · context · storage · paths
  app/db/              session · base (importa todos os models)
  app/domains/<dom>/   models · schemas · service · router   (um pacote por domínio)
  run_server.py        entrada do .exe   ·   erp-frota-api.spec   receita do PyInstaller
frontend/            React 19 · TypeScript · Vite · Tailwind · TanStack Query · RHF + Zod
desktop/             Electron: sobe o Postgres embutido, o backend e a janela
```

**A API serve a interface compilada** (`frontend/dist` → `static/` dentro do `.exe`). Funciona
porque as rotas da interface são em português (`/veiculos`) e as da API em inglês (`/vehicles`):
não colidem. Uma porta só, sem CORS e sem servidor web separado.

**Portas:** 5434 (banco), 8010 (API), 5273 (Vite). Não são as padrão de propósito — 5432/5433,
8000 e 5173 já estavam ocupadas na máquina de desenvolvimento. O Vite roda com `strictPort`: se a
porta estiver ocupada ele falha, em vez de subir em outra e servir o app errado em silêncio.

---

## Como rodar (desenvolvimento)

**Pré-requisitos:** **Python 3.13** (não 3.14 — veja a nota abaixo), Node 20+, e o Postgres
portátil em `desktop/vendor/pgsql`.

```bash
# 1. Postgres portátil — baixe uma vez (~300 MB, fora do git)
#    https://get.enterprisedb.com/postgresql/postgresql-16.10-1-windows-x64-binaries.zip
#    extraia de modo que exista desktop/vendor/pgsql/bin/pg_ctl.exe
PG="desktop/vendor/pgsql/bin"
DATA="$LOCALAPPDATA/GM Locacoes/pgdata"
"$PG/initdb"  -D "$DATA" -U frota -A trust -E UTF8 --locale=C     # só na primeira vez
"$PG/pg_ctl"  -D "$DATA" -o "-p 5434" -w start
"$PG/createdb" -h 127.0.0.1 -p 5434 -U frota frota                # só na primeira vez

# 2. Backend  →  http://127.0.0.1:8010   (docs interativas em /docs)
cd backend
py -3.13 -m venv .venv && .venv/Scripts/activate
pip install -r requirements-dev.txt
cp ../.env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8010

# 3. Frontend  →  http://localhost:5273
cd frontend && npm install && npm run dev
```

**Login:** o admin é criado no primeiro boot com senha sorteada, gravada em
`%LOCALAPPDATA%\GM Locacoes\senha-inicial-admin.txt`.

> **Python 3.13, não 3.14.** No 3.14 o `pip install` falha: `pydantic-core==2.33.2` não tem wheel
> `cp314`, cai em compilação Rust e o PyO3 0.24.1 recusa Python acima do 3.13.

> **`pg_ctl start` trava se a saída for canalizada no PowerShell.** O servidor herda o handle de
> stdout e o pipeline nunca fecha — o banco sobe, mas o comando fica pendurado. Não use `|`.

### Testes

```bash
cd backend && pytest        # 113 testes; cria e derruba um banco `frota_test` isolado
```

A suíte tem guards que abortam a execução se a `DATABASE_URL` apontar para o banco de
desenvolvimento ou se o `STORAGE_DIR` apontar para a pasta real de arquivos.

---

## Como gerar o app de desktop

```bash
# ANTES: ligue o Modo de desenvolvedor do Windows
# (Configurações → Privacidade e segurança → Para desenvolvedores)
# Sem ele o electron-builder não cria os symlinks de que precisa.
cd frontend && npm run build                                  # compila a interface
cd ../backend && pyinstaller erp-frota-api.spec --noconfirm    # empacota a API (62 MB, sem Python)
cd ../desktop && npm install && npm run dist                   # gera o instalador
# → desktop/dist/GM Locações Setup 1.0.0.exe
```

Instale e pronto: ícone na área de trabalho. **Não é preciso Python, Docker nem terminal.**
O Postgres portátil viaja dentro do instalador, e o app o inicializa na primeira execução.

Na primeira abertura o Windows mostra "O Windows protegeu o seu PC" — o `.exe` não é assinado
digitalmente (custaria ~US$ 200/ano). **Mais informações → Executar assim mesmo**, uma vez por máquina.

**Onde ficam os dados** — tudo em `%LOCALAPPDATA%\GM Locacoes\`:

| Caminho | O que é |
|---|---|
| `pgdata\` | O banco (cluster do Postgres embutido) |
| `storage\` | Fotos, contratos e notas fiscais |
| `secret.key` | Segredo do JWT, sorteado nesta instalação |
| `senha-inicial-admin.txt` | Senha do primeiro acesso — apague depois de usar |
| `logs\backend.log` | A única pista quando o app não abre |

Fica na pasta do usuário porque `C:\Program Files` não é gravável: gravar ao lado do `.exe` daria
"Acesso negado" no primeiro upload de foto.

---

## Stack

**Backend:** Python 3.13 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · JWT · bcrypt
**Frontend:** React 19 · TypeScript · Vite · Tailwind · TanStack Query · React Hook Form · Zod
**Desktop:** Electron · electron-builder (NSIS) · PyInstaller
**Arquivos:** disco local atrás de um `StorageService` — trocar por S3/R2 é implementar 4 métodos.

## Ainda não existe

Relatórios PDF/Excel · alertas automáticos · busca global · plano de manutenção preventiva ·
app Android · rastreador · integração com WhatsApp · assinatura eletrônica.

Cada um tem gancho no schema. Nenhum exige reescrita.

## Licença

Proprietário — todos os direitos reservados. O repositório é público **para leitura e avaliação**:
é peça de portfólio, não software de uso livre. Detalhes em [LICENSE](LICENSE).

---

Notas de arquitetura e regras permanentes em [CLAUDE.md](CLAUDE.md) · diário de decisões em
[BACKLOG.md](BACKLOG.md) · a visão original em [MANIFESTO.md](MANIFESTO.md).

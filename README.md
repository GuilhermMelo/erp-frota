# ERP Frota

ERP de gestão de frota para locadora de veículos de motoristas de aplicativo.

Não é um CRUD de carros. O sistema existe para responder **uma** pergunta com precisão:

```
Lucro do veículo = receitas − despesas − valor de compra + valor de venda
```

Tudo o mais — contratos, vistorias, manutenções, multas — existe para alimentar essa conta.

---

## Como rodar

**Pré-requisitos:** Docker, Python 3.13, Node 20+.

```bash
# 1. Banco (Postgres 16 na porta 5434)
docker compose up -d

# 2. Backend  →  http://127.0.0.1:8010   (docs interativas em /docs)
cd backend
python -m venv .venv
.venv\Scripts\activate                    # Windows
pip install -r requirements-dev.txt
copy ..\.env.example .env                 # ajuste se precisar
alembic upgrade head
uvicorn app.main:app --reload --port 8010

# 3. Frontend  →  http://localhost:5273
cd frontend
npm install
npm run dev
```

**Login:** `admin@erpfrota.com.br` / `admin123` (criado no primeiro boot; troque em produção).

> **Portas:** 5434 (banco), 8010 (API), 5273 (web). Não são as portas padrão de propósito —
> 5432/5433, 8000 e 5173 já estavam ocupadas nesta máquina por outros projetos. O Vite roda
> com `strictPort`: se a porta estiver ocupada ele falha, em vez de subir em outra e servir
> o app errado em silêncio.

### Testes

```bash
cd backend && pytest        # 113 testes; cria e derruba um banco `frota_test` isolado
```

---

## O que o sistema faz

| Módulo | O que resolve |
|---|---|
| **Veículos** | Cadastro a partir do valor de compra. Ação **"Vender"** fecha o ciclo e trava o resultado. |
| **A conta do veículo** | A tela central. Mostra a equação do lucro e **cada número é clicável**, abrindo os lançamentos que o compõem. Mais ROI, payback, custo/km. |
| **Motoristas** | Cadastro, CNH com destaque de vencimento. Motorista **não tem login** — é dado, não usuário. |
| **Contratos** | Carro + motorista + valor semanal + caução, com anexos (PDF, assinatura). **Gera as cobranças semanais sozinho.** |
| **Cobranças** | Inadimplência: quem deve o quê, há quantos dias. |
| **Receitas / Despesas** | Lançamentos amarrados a um veículo. Categorias de despesa editáveis, com marcação de investimento (capex). |
| **Manutenções** | Histórico simples (descrição, valor, KM, data). **Gera a despesa automaticamente.** Sem plano preventivo. |
| **Multas** | Vinculadas ao carro e ao motorista. Pagar gera despesa; reembolso gera receita — o líquido dá zero sozinho. |
| **Vistorias** | Checklist estruturado + até 200 fotos (comprimidas no navegador) + foto da assinatura. |
| **Auditoria** | Log append-only de quem mudou o quê, com o "de → para". |

---

## As três armadilhas de contagem dupla

Três fatos inflariam o lucro do carro se fossem modelados como receita/despesa comum.
Cada um mora em **um lugar só** — e isso é regra, não preferência:

| Fato | Onde mora | Se virasse lançamento comum |
|---|---|---|
| Valor de compra | `vehicles.purchase_price` | Custo contado em dobro. |
| Valor de venda | `vehicles.sale_price` | Lucro contado em dobro. |
| **Caução** | `contracts.deposit_amount` | Lucro inflado até você devolver — **a caução não é sua.** |

A caução só vira receita (`caucao_retida`) na parte efetivamente retida ao encerrar o contrato.

**Multas:** a despesa é registrada **sempre** que você paga. Se o motorista reembolsa, entra
uma receita ligada à mesma multa e o líquido zera sozinho. Registrar só as não-reembolsadas
perderia o rastro de quanto você já pagou e de quanto cada motorista te deve.

---

## Decisões técnicas que valem saber

- **Dinheiro é `Decimal`/`Numeric(12,2)` ponta a ponta.** Nenhum `float` em lugar nenhum —
  a API entrega dinheiro como *string* para o JavaScript não estragar. O frontend **nunca**
  faz conta de dinheiro; só exibe.
- **Alembic desde o primeiro commit.** Nunca `create_all`.
- **Códigos legíveis** (`CAR000001`, `CTR000001`) vêm de sequences do Postgres. A chave
  primária é UUID — o código nunca é PK.
- **Cobrança semanal é idempotente** por `UNIQUE(contract_id, period_start)`. Roda toda vez
  que o app abre, sem cron e sem duplicar.
- **Inadimplência é derivada** (`status IN ('pending','partial') AND due_date < hoje`), não
  armazenada. Sem job noturno, sem estado que fica velho.
- **Auditoria por event listener do SQLAlchemy**, não por chamada no service — chamada no
  service é o que o humano cansado esquece.
- **`storage/` nunca é servido como pasta estática.** CNH, CPF e contratos são dado pessoal.
  Download só pelo endpoint autenticado.
- **Fotos são comprimidas no navegador** (1600px, JPEG 0.8) antes de subir: 200 fotos de
  celular passam de ~1 GB para ~20 MB.

Detalhes e regras permanentes em [CLAUDE.md](CLAUDE.md) e [MANIFESTO.md](MANIFESTO.md).

---

## Stack

**Backend:** Python 3.13 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · JWT
**Frontend:** React 19 · TypeScript · Vite · Tailwind · TanStack Query · React Hook Form · Zod
**Arquivos:** disco local, atrás de um `StorageService` — trocar por S3/R2 é implementar 4 métodos.

---

## Ainda não existe

Relatórios PDF/Excel · alertas automáticos · busca global · plano de manutenção preventiva ·
app Android · rastreador · WhatsApp · assinatura eletrônica.

Cada um tem gancho no schema. Nenhum exige reescrita.

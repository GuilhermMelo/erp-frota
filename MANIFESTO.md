# Manifesto — ERP de Gestão de Frota (v1.1)

> v1.0 foi escrita antes do projeto começar (`ERP_Frota_Manifesto_v1.md`). Esta v1.1 corrige as
> decisões de stack que foram revistas conscientemente e o modelo financeiro que estava errado.
> Este documento é a especificação viva — refine-o durante o desenvolvimento.

## Por que este projeto existe

Guilherme aluga carros para motoristas de aplicativo. Hoje são poucos veículos, controlados em
planilha, e a meta é crescer para dezenas. A planilha não responde à única pergunta que decide o
negócio: **este carro está dando lucro?**

O ERP existe para responder isso com precisão, e para sustentar a operação (contratos, vistorias,
manutenções, multas) que gera os números dessa resposta.

## A conta que o sistema fecha

```
Lucro do veículo = (todas as receitas)      aluguéis, reembolsos, caução retida
                 − (todas as despesas)      manutenção, IPVA, seguro, pneus, multas...
                 − valor de compra
                 + valor de venda           quando vendido
```

Tudo o mais no sistema existe para alimentar essa conta.

## Princípios

1. **Funciona de verdade.** Nada de tela de mentira. Se está na tela, funciona.
2. **O número tem que ser auditável.** Todo valor exibido é clicável e abre os lançamentos que o
   compõem. Dono que não consegue conferir o número não confia nele.
3. **Histórico imutável.** Quilometragem e auditoria só recebem inserções. Nada é sobrescrito.
4. **Simples de entender, sólido de manter.** Organizado por domínio, sem over-engineering.
   Um dev júnior deve conseguir ler.
5. **Preparado para crescer sem reescrita.** De 1 a 300 veículos com o mesmo sistema.
6. **Evolui em sessões documentadas.** Cada sessão é registrada no `BACKLOG.md`.

## Stack (revista em relação à v1.0)

| Camada | v1.0 dizia | **Decidido** | Por quê |
|---|---|---|---|
| Backend | NestJS + Prisma | **FastAPI + SQLAlchemy + Alembic** | Python é a força do dono (Engenheiro de Dados). Sistema real, mantido sozinho por anos — velocidade e confiança valem mais que pureza. Relatórios e OCR futuro são muito mais fáceis em Python. |
| Desktop | Electron | **Web + PWA** | Instalável, com ícone e janela própria, sem assinatura de código nem auto-update. Electron volta a fazer sentido se um segundo funcionário precisar abrir com dois cliques — é o mesmo React dentro de uma casca. |
| Banco | PostgreSQL | **PostgreSQL** | — |
| Arquivos | pasta local | **pasta local, atrás de um `StorageService`** | Trocar por nuvem depois não toca no resto do código. |

Frontend: React 19 · TypeScript · Vite · Tailwind · TanStack Query · React Hook Form · Zod.

## Escopo

**É:** veículos, motoristas, contratos (com cobrança semanal e inadimplência), vistorias (checklist +
fotos + assinatura), manutenções (histórico), multas, receitas, despesas, a conta do veículo,
auditoria.

**Ainda não é:** relatórios PDF/Excel, alertas automáticos, busca global, plano de manutenção
preventiva, app Android, rastreador, WhatsApp, assinatura eletrônica, BI.

**Nunca será:** um portal para o motorista. Todos os usuários são funcionários da locadora.

## Modelo financeiro — as três armadilhas

Três fatos infla­riam o lucro do carro se fossem modelados como receita/despesa comum. Cada um mora
em **um lugar só**:

| Fato | Onde mora | Se virasse lançamento comum |
|---|---|---|
| Valor de compra | `vehicles.purchase_price` | Custo contado em dobro. |
| Valor de venda | `vehicles.sale_price` | Lucro contado em dobro. |
| **Caução** | `contracts.deposit_amount` + `deposit_status` | Lucro inflado até você devolver — **a caução não é sua.** |

A caução só vira receita (`caucao_retida`) na parte efetivamente retida ao encerrar o contrato.

**Multas:** a despesa é registrada **sempre** que você paga, vinculada ao carro e ao motorista. Se o
motorista reembolsa, entra uma receita `reembolso` ligada à mesma multa — o líquido dá zero sozinho.
Registrar só as não-reembolsadas perderia o rastro de quanto você já pagou e de quanto o motorista deve.

## Identificadores

Toda tabela tem `id` (UUID, chave primária) e `code` (legível, gerado por sequence do Postgres):

`CAR000001` · `DRV000001` · `CTR000001` · `VST000001` · `MAN000001` · `MUL000001` · `REC000001` · `DES000001`

O código **nunca** é chave primária.

## Definição de "pronto"

- Backend: endpoint + validação + teste.
- Frontend: tela integrada e testada no navegador.
- Commit com mensagem clara.
- `BACKLOG.md` atualizado.

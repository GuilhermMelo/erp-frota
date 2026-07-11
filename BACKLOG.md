# Backlog — ERP Frota v1

> Diário do projeto. Uma entrada por sessão. Mais recente no topo.

## Próximo

1. **Cadastrar os veículos reais e migrar a planilha.** É aqui que o sistema passa a valer algo.
2. Trocar a senha do admin (`admin123`) e gerar um `SECRET_KEY` de verdade antes de qualquer uso fora da máquina local.
3. Decidir a hospedagem. Enquanto for local, o sistema exige subir Docker + API + front na mão —
   quando um segundo funcionário entrar, ou hospeda a API, ou o Electron volta a fazer sentido
   (empacota tudo num `.exe`).
4. Depois: relatórios PDF/Excel, alertas automáticos, busca global, plano de manutenção preventiva.

### Dívidas conhecidas (nenhuma bloqueia o uso)

- **Não existe `DELETE /inspections`.** Vistoria criada por engano não some. (Fotos e itens dão para apagar.)
- **Não dá para corrigir um preço de venda digitado errado.** Vender de novo dá 409. Falta um
  `POST /vehicles/{id}/sell/undo`.
- `RevenueOut` não traz veículo/motorista aninhados (a tela faz o join no cliente).

---

## Sessão 1 — 2026-07-11

Projeto criado do zero e entregue funcionando ponta a ponta.

### Contexto

Partiu de um manifesto (`ERP_Frota_Manifesto_v1.md`) escrito com ajuda do ChatGPT, que propunha
NestJS + Prisma + Electron. Revisto antes de escrever a primeira linha.

### Decisões

- **Backend em FastAPI**, não NestJS: Python é a força do dono. Sistema real, mantido sozinho por
  anos — velocidade e confiança valem mais que pureza arquitetural.
- **Web + PWA**, não Electron: exige internet de qualquer forma, e o Electron cobra assinatura de
  código e auto-update sem dar nada em troca agora. É o mesmo React dentro de uma casca, depois.
- **Portas não-padrão** (5434 / 8010 / 5273): as padrão já estavam ocupadas nesta máquina
  (Postgres local, `ai-doc-postgres`, e o Atlas Sports na 8000 e na 5173). O Vite roda com
  `strictPort` — falha em vez de subir na porta errada em silêncio.
- **As três armadilhas de contagem dupla** fechadas por construção: valor de compra, valor de venda
  e **caução** moram em um lugar só. A caução não é receita — é dinheiro que se segura e devolve.
- **Multa registra sempre a despesa**; o reembolso do motorista entra como receita ligada à multa.
  Líquido dá zero sozinho e o rastro fica preservado.
- **Cobrança semanal idempotente** por constraint `UNIQUE(contract_id, period_start)` — roda a cada
  abertura do app, sem cron. **Inadimplência é derivada**, não armazenada.
- **Fotos comprimidas no navegador** (1600px / JPEG 0.8). Medido: 200 fotos de 5 MB → ~20 MB.
- Manutenção: **histórico simples**. Sem plano preventivo, sem lembrete — foi pedido assim.

### Bugs reais encontrados e corrigidos durante a construção

1. **Vender um carro com contrato ativo corrompia o lucro dele.** O contrato seguia ativo e a
   geração semanal continuava criando aluguel para um carro que não é mais do dono: a conta fechada
   em R$ 0,00 voltava a +R$ 800 na semana seguinte. E a caução do motorista ficava presa. Agora a
   venda é recusada com 409 e uma mensagem que diz o que fazer.
2. **Apagar multa/manutenção sumia com a despesa sem deixar rastro na auditoria.** O `ON DELETE
   CASCADE` do Postgres apagava a despesa por baixo do ORM, e o listener de auditoria é cego a
   cascata de banco. O custo do carro caía e ninguém sabia quem apagou. Agora a despesa é apagada
   pelo ORM antes do pai.
3. **A auditoria gravava `actor_email='sistema'` mesmo com usuário logado.** `get_current_user` era
   uma dependência síncrona: o FastAPI a roda numa thread do pool, que recebe uma *cópia* do
   contexto — o `set_actor()` escrevia numa cópia descartável. Virou `async def`.
4. **Todo log de criação gravava `entity_id`/`entity_code` nulos.** O listener rodava em
   `before_flush`, antes de o banco gerar o UUID e o `code`. Agora coleta o diff em `before_flush`
   (único momento em que o "de → para" existe) e grava em `after_flush` (único em que o id existe).
5. **RENAVAM/chassi vazios davam HTTP 500 no segundo veículo.** String vazia gravava `""`, que viola
   o índice UNIQUE (no Postgres, NULLs são distintos entre si; strings vazias não). Normalizado
   `"" → NULL`.
6. **Anexos ficavam órfãos** ao apagar manutenção/multa (`documents` usa ponteiro polimórfico, sem
   FK — nada cascateia). Arquivo ficava no disco e a linha no banco, sem dono.
7. **Payback mentia para carro vendido.** Calculado só sobre a operação, dizia "faltam ~8 meses" de
   um carro que não é mais seu. Agora devolve vazio e a tela diz "não se pagou rodando — o resultado
   veio da venda".

### Feito

- 16 tabelas, migração Alembic única, seed idempotente (14 categorias de despesa, 32 itens de checklist).
- Backend: 12 domínios, 43 endpoints. Auditoria automática. Storage local atrás de interface.
- Frontend: 13 telas. Upload com compressão, fila de 4 paralelos, barra de progresso e retry.
- **113 testes passando**, incluindo o teste do ciclo de vida (compra R$ 50.000 → 10 aluguéis de
  R$ 800 → R$ 3.000 de despesas → venda por R$ 45.000 → **lucro R$ 0,00 exato**), a caução que não
  infla o lucro, a multa reembolsada que zera, `Decimal` sem perda de centavo, e divisão por zero
  devolvendo vazio em vez de 500.
- Verificado no Chrome: login, painel, veículos, a conta do veículo e cobranças — **zero erros de console**.

### Pendente

Ver "Próximo".

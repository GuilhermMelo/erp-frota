# Backlog — ERP Frota v1

> Diário do projeto. Uma entrada por sessão. Mais recente no topo.

## Próximo

1. **GERAR O INSTALADOR — 1 passo, bloqueado por uma permissão do Windows.**
   Ligue o **Modo de desenvolvedor** (Configurações → Privacidade e segurança → Para desenvolvedores),
   depois: `cd desktop && npm run dist`. Sai o `desktop/dist/GM Locações Setup 1.0.0.exe`.
   *Por que trava sem isso:* o `electron-builder` extrai um pacote de assinatura de código que contém
   symlinks do macOS, e criar symlink no Windows exige privilégio. Não é problema do código — o app
   em si já roda (verificado).
2. **Cadastrar os veículos reais e migrar a planilha.** É aqui que o sistema passa a valer algo.
3. Trocar a senha do admin (`admin123`). Em produção o `SECRET_KEY` já é sorteado por instalação.
4. Depois: relatórios PDF/Excel, alertas automáticos, busca global, plano de manutenção preventiva.

### Dívidas conhecidas (nenhuma bloqueia o uso)

- **O app instalado ainda depende do Docker Desktop** para o Postgres. Na sua máquina ele já inicia
  com o Windows, então é invisível. Numa máquina limpa (PC de funcionário), ou o Postgres entra no
  instalador, ou o banco vira hospedado. **Não decidido.**
- **O `.exe` não será assinado** (~US$ 200/ano). O Windows mostra "protegeu o seu PC" na primeira
  execução → "Mais informações" → "Executar assim mesmo". Uma vez só, por máquina.
- **Não existe `DELETE /inspections`.** Vistoria criada por engano não some. (Fotos e itens dão para apagar.)
- **Não dá para corrigir um preço de venda digitado errado.** Vender de novo dá 409. Falta um
  `POST /vehicles/{id}/sell/undo`.
- `RevenueOut` não traz veículo/motorista aninhados (a tela faz o join no cliente).

---

## Sessão 3 — 2026-07-11

App de desktop (Electron). O sistema deixou de exigir três comandos no terminal.

### Decisão: Electron agora se paga

Na sessão 1 eu argumentei CONTRA o Electron — ele cobra assinatura de código e auto-update sem dar
nada em troca. Aquilo valia para um sistema com API hospedada. **Como tudo aqui roda local, o
Electron passou a se pagar**: ele empacota Postgres + API + interface num clique só. Decisão revista.

### Como ficou

- **A API serve a interface compilada.** Deu certo por sorte de projeto: as rotas da interface são em
  português (`/veiculos`, `/cobrancas`) e as da API em inglês (`/vehicles`, `/revenues`) — **não
  colidem**. Uma porta só, sem CORS, sem servidor web separado. O catch-all fica por último e devolve
  o `index.html` (senão dar F5 em `/veiculos/123` daria 404).
- **Backend empacotado com PyInstaller** (62 MB): quem instalar **não precisa ter Python**.
- **As migrações rodam sozinhas no boot.** Ninguém vai abrir um terminal para rodar `alembic` num
  programa de desktop.
- **O Electron garante o Postgres**: tenta `docker start erp-frota-db`; se o container não existir,
  sobe pelo compose com o nome de projeto FIXO (`-p erp-frota-v1`) — se o Docker derivasse o nome da
  pasta, uma pasta diferente criaria um volume novo e **o banco apareceria vazio**, com os dados
  "sumidos" no volume antigo.
- Ao fechar a janela, o backend morre junto (`taskkill /T`, para não deixar órfão segurando a 8010).

### Bugs consertados

- **`AttributeError: 'NoneType' has no attribute 'isatty'`** no boot do `.exe`. Com `console=False`, o
  Windows não dá handles de saída: `sys.stdout` fica `None` e o uvicorn chama `.isatty()` nele.
  O `run_server.py` agora aponta as saídas para `%LOCALAPPDATA%\GM Locacoes\logs\backend.log` antes de
  subir o uvicorn. **Num `.exe` sem console, log em arquivo não é conforto — é a única pista** quando
  o app não abre na máquina de quem instalou.
- **`ModuleNotFoundError: No module named 'app.db.base'`** — só apareceu depois que o log existiu.
  O Alembic lê `migrations/env.py` do disco em tempo de execução, então o `from app.db.base import
  Base` de lá é invisível para o PyInstaller: o `.exe` ia com zero models. Corrigido com
  `collect_submodules("app")` no `.spec`.
- **Program Files não é gravável.** As fotos e a chave secreta iriam para o lado do `.exe` e o primeiro
  upload daria "Acesso negado". Agora vão para `%LOCALAPPDATA%\GM Locacoes\`.
- **Segredo do JWT sorteado por instalação** (`secret.key`). Sem isso, todas as instalações
  compartilhariam o segredo que está no código-fonte e qualquer um forjaria um token de admin.
- **Path traversal no catch-all da SPA**: `/../../.env` leria fora da pasta. Fechado.

### Armadilha de ambiente (não é bug do app)

Rodar `npm start` **de dentro do VS Code** falha com `Cannot read properties of undefined (reading
'requestSingleInstanceLock')`. O VS Code define `ELECTRON_RUN_AS_NODE=1` no terminal; com ela, o
Electron roda como Node puro e `require('electron')` devolve um caminho em vez da API. Rode de um
terminal normal, ou `Remove-Item Env:\ELECTRON_RUN_AS_NODE` antes.

### Verificado

`.exe` do backend rodando sozinho: `/health` → `{"status":"ok","db":"up"}`, `/` serve a interface
(título "GM Locações"), `/veiculos` devolve 200 (rota do React), migrações aplicadas no boot.
Electron aberto: 4 processos, backend subido em segundo plano, banco respondendo.

### Pendente

O instalador (ver "Próximo", item 1).

---

## Sessão 2 — 2026-07-11

Empacotamento do backend em `.exe` (PyInstaller). O `.exe` já subia — só morria num diálogo do
Windows antes de servir a primeira requisição. Dois bugs, um escondido atrás do outro.

### Consertado

- **`AttributeError: 'NoneType' object has no attribute 'isatty'`** no boot do `.exe`.
  Com `console=False`, o Windows não dá handles de saída ao processo: `sys.stdout` e `sys.stderr`
  ficam `None`, e o uvicorn chama `sys.stdout.isatty()` ao montar o formatador de log.
  `run_server.py` agora aponta as duas saídas para `%LOCALAPPDATA%\ERP Frota\logs\backend.log`
  antes de chamar o uvicorn, e loga o traceback de qualquer exceção antes de morrer.
- **`ModuleNotFoundError: No module named 'app.db.base'`** — só apareceu depois que o log passou a
  existir. O Alembic lê `migrations/env.py` do disco em tempo de execução, então o
  `from app.db.base import Base` de lá é invisível para o PyInstaller: o `.exe` ia com zero models.
  O `.spec` agora usa `collect_submodules("app")` no lugar de `"app.main"`.

### Decisão

- **O `.exe` sem console PRECISA de log em arquivo, não é conforto.** Sem terminal, todo erro de boot
  vira uma caixa de diálogo sem contexto na máquina de quem instalou. O log é a única pista.

### Verificado

`.exe` reempacotado e executado: `/health` → `{"status":"ok","db":"up"}`, `/` serve a interface (200),
migrações rodam sozinhas no boot.

### Pendências

- O instalador (NSIS/Inno) e o atalho no menu Iniciar ainda não existem — hoje é a pasta
  `dist/erp-frota-api/` inteira.
- O `.exe` continua exigindo o Postgres no Docker de pé. Para entregar numa máquina limpa, ou o
  Postgres entra no instalador, ou o banco vira SQLite/hospedado. **Não decidido.**

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

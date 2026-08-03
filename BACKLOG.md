# Backlog — GM Locações

> Diário do projeto. Uma entrada por sessão, mais recente no topo. **Histórico antigo condensa:**
> o detalhe de como um bug foi corrigido vive no `git log`, não aqui. Este arquivo guarda decisão
> e pendência — o que o próximo leitor precisa para não repetir trabalho.

## Próximo

1. **Trocar a senha do admin nas instalações que já existem.** O mecanismo novo (senha sorteada)
   só age onde ainda não há usuário. Onde o admin já foi criado com `admin123`, a troca é manual —
   ou apague o usuário e deixe o seed recriá-lo no próximo boot.
2. **Gerar o instalador** — bloqueado por uma permissão do Windows. Ligue o **Modo de
   desenvolvedor** (Configurações → Privacidade e segurança → Para desenvolvedores), depois
   `cd desktop && npm run dist`. O `electron-builder` extrai um pacote com symlinks do macOS, e
   criar symlink no Windows exige privilégio. Não é problema do código: o app já roda.
4. **Cadastrar os veículos reais e migrar a planilha.** É aqui que o sistema passa a valer algo.
5. Depois: relatórios PDF/Excel, alertas automáticos, busca global, manutenção preventiva.

## Dívidas conhecidas

Nenhuma bloqueia o uso.

**Resíduo do modelo antigo, anterior ao Postgres embutido (Sessão 4):**
- `scripts/iniciar-erp.ps1` ainda sobe o banco pelo Docker e roda o `.exe` do backend direto — é o
  lançador pré-Electron. `GM Locações.cmd` na raiz aponta para ele. Ou reescrever para o Postgres
  portátil, ou remover os dois: hoje o repositório mostra dois caminhos de execução e um está morto.
- `docker-compose.yml` sobrou do modelo antigo. Decidir: manter como alternativa de dev, ou remover.
- `README.md` já foi corrigido (Sessão 4).

**Produto:**
- Não existe `DELETE /inspections`. Vistoria criada por engano não some (fotos e itens, sim).
- Não dá para corrigir preço de venda digitado errado. Vender de novo dá 409. Falta
  `POST /vehicles/{id}/sell/undo`.
- `RevenueOut` não traz veículo/motorista aninhados (a tela faz o join no cliente).

**Empacotamento:**
- O `.exe` não será assinado (~US$ 200/ano). O Windows mostra "protegeu o seu PC" na primeira
  execução → "Mais informações" → "Executar assim mesmo". Uma vez por máquina.

---

## Sessão 4 — 2026-08-03

Projeto clonado numa máquina nova. Ambiente montado do zero e auditoria de segurança do
repositório público.

### Decisão: nenhuma senha no código-fonte

O repositório é **público**. `admin123` estava em `.env.example`, `config.py`, `seed.py`, nos
testes e no README — ou seja, a senha inicial de toda instalação que existisse era pública.

`ADMIN_PASSWORD` agora nasce **vazio**, e vazio significa **sortear**: o seed gera
`secrets.token_urlsafe(18)` no primeiro boot e grava em
`%LOCALAPPDATA%\GM Locacoes\senha-inicial-admin.txt`, arquivo que pede para ser apagado após o
primeiro login. Preencher `ADMIN_PASSWORD` continua valendo — é assim que a suíte de testes sabe
a senha de antemão.

Por que arquivo, e não log: o app é de desktop e roda sem console. Senha em `logger.info` morre
num arquivo que ninguém abre. **Escrever a senha em texto puro não é bom** — é melhor que a
alternativa que existia, que era uma senha fixa num repositório aberto.

A entrega da senha acontece **depois do commit**: entregar credencial de um usuário que não foi
gravado mandaria o dono tentar um login que nunca funcionaria.

### Auditoria do repositório público

Varridos os 3 commits inteiros (`git log --all -p`), não só a árvore atual:

- Nunca commitado: `.env` real, `secret.key`, chave privada, `.pem`, `.pfx`.
- Zero ocorrências de token real (`ghp_`, `sk-`, `AKIA`, `AIza`, `xox*`).
- `storage/` sempre ignorado — nenhuma foto de CNH/CPF ou contrato no histórico.
- Exposto: só credenciais padrão de desenvolvimento (`admin123`, `dev-secret-troque-em-producao`,
  `frota:frota`). As duas últimas já eram inofensivas — o `.exe` sorteia seu `SECRET_KEY` e o
  banco só escuta em `localhost`.
- Repositório com 0 forks, 0 stars, 0 watchers.

**Conclusão: nada sensível vazou.** O risco era a senha inicial padrão, agora eliminada.

### Ambiente de desenvolvimento em máquina nova

- **Python 3.13 é obrigatório.** No 3.14 o `pip install` falha: `pydantic-core==2.33.2` não tem
  wheel `cp314`, cai em compilação Rust e o PyO3 0.24.1 recusa Python acima do 3.13.
- **Postgres 16.10 portátil** baixado para `desktop/vendor/pgsql` (~300 MB, fora do git). Cluster
  em `%LOCALAPPDATA%\GM Locacoes\pgdata` — o mesmo caminho do app, então dev e app instalado
  compartilham o banco.
- **`pg_ctl start` trava se a saída for canalizada no PowerShell.** O servidor herda o handle de
  stdout e o pipeline nunca fecha; o banco sobe, mas o comando fica pendurado. Redirecione para
  arquivo, não use `|`.
- A pasta do clone é `erp`, não `erp-frota-v1`. **Deixou de importar:** o nome só afetava o volume
  do Docker, e o caminho dos dados hoje é fixo em `%LOCALAPPDATA%`.

### CLAUDE.md reescrito

Encurtado (entra no contexto toda sessão) e ganhou duas seções: **Segurança** (7 regras para
repositório aberto) e **Economia de contexto** (não ler arquivo inteiro, não rodar a suíte toda
para validar um domínio, não ler `vendor/`/`node_modules`/`package-lock.json`).

### Verificado

113 testes passando depois da mudança do seed. API `/health` → `{"status":"ok","db":"up"}`,
login retornando JWT, Vite em `localhost:5273` respondendo 200, migrações em `0002 (head)`,
17 tabelas.

### Decisão: o repositório continua público, e serve de portfólio

Levantada a opção de fechar o repositório e **recusada pelo dono**: o projeto é peça de portfólio.
Duas consequências, que não são opcionais a partir daqui:

1. A regra "nenhum segredo no código-fonte" deixa de ser higiene e passa a ser a única defesa que
   existe. Por isso é a regra 1 da seção de Segurança do `CLAUDE.md`, escrita como regra.
2. **Documentação errada custa mais do que documentação ausente.** Quem lê um repositório de
   portfólio julga pelo README. O README pedia Docker Desktop como pré-requisito — falso desde o
   commit `2f73735`, que trocou o Docker pelo Postgres embutido.

### README reescrito para leitura externa

Antes ele era manual de operação de quem já conhecia o sistema. Agora abre pelo problema (a conta
que a locadora quase nunca faz direito), depois a equação, as três armadilhas de contagem dupla, e
só então instalação. As decisões técnicas passaram a explicar **por que**, não só o quê — é o que
distingue um repositório de portfólio de um dump de código.

Corrigido: Docker deixou de ser pré-requisito, entrou o passo do Postgres portátil, entraram os
dois tropeços de ambiente desta sessão (Python 3.13 e não 3.14; `pg_ctl` com pipe no PowerShell) e
a tabela de onde ficam os dados. Adicionados badges de stack e a seção Segurança e LGPD.

### Aplicado na instalação local

Admin `USR000001` apagado; o seed recriou como `USR000002` com senha sorteada de 24 caracteres.
Verificado: a senha do arquivo entra, `admin123` recebe 401. Os 3 registros de auditoria
sobreviveram à exclusão do usuário — que é exatamente o que o `actor_email` desnormalizado, sem
FK para `users`, foi feito para garantir.

### graphify instalado

`graphifyy` (PyPI, projeto `Graphify-Labs/graphify`) via `uv tool install`. Atenção ao escolher:
existe um `@sentropic/graphify` no npm, de outra organização (`rhanka/graphify`), com nome quase
idêntico — o README oficial avisa que os outros pacotes `graphify*` não são afiliados.

A skill mora em `~/.claude/skills/graphify/` (perfil do usuário, não do projeto). Custo em
contexto por sessão: 3 linhas no `~/.claude/CLAUDE.md`; os 39 KB do `SKILL.md` só carregam quando
`/graphify` é chamado. `graphify-out/` está no `.gitignore` — é derivado do código, regerável com
`graphify update .`.

---

## Sessões 1 a 3 — 2026-07-11 (condensado)

Projeto criado do zero e entregue funcionando ponta a ponta, depois empacotado como app de desktop.

### Decisões que ainda valem

- **FastAPI, não NestJS** (o manifesto original propunha NestJS + Prisma): Python é a força do dono,
  e o sistema é mantido por uma pessoa só.
- **Electron se paga aqui.** Na Sessão 1 o argumento foi contra — ele cobra assinatura de código e
  auto-update sem dar nada em troca. Isso valia para um sistema com API hospedada. Como tudo roda
  local, o Electron empacota banco + API + interface num clique. Decisão revista na Sessão 3.
- **A API serve a interface compilada.** As rotas da UI são em português e as da API em inglês:
  não colidem. Uma porta só, sem CORS, sem servidor web separado.
- **As migrações rodam sozinhas no boot.** Ninguém abre terminal para rodar `alembic` num programa
  de desktop.
- **`.exe` sem console PRECISA de log em arquivo.** Não é conforto: é a única pista quando o app
  não abre na máquina de quem instalou.
- **Segredo do JWT sorteado por instalação.** Sem isso, toda instalação compartilharia o segredo do
  código-fonte e qualquer um forjaria um token de admin.

### Bugs que custaram caro (detalhe no `git log`)

`sys.stdout is None` com `console=False` · `ModuleNotFoundError: app.db.base` no PyInstaller ·
Program Files não é gravável · path traversal no catch-all da SPA. Todos viraram armadilha
documentada no `CLAUDE.md`.

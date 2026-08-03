# Abre o GM Locações nesta máquina: sobe o banco, o servidor e o navegador.
#
# Não rode direto — use o "GM Locações.cmd" na raiz (ou o atalho na área de trabalho).
#
# ---------------------------------------------------------------------------
# O DOCKER SAIU DAQUI. Este script subia o Postgres com `docker compose up` e exigia o
# Docker Desktop instalado e rodando. Hoje o banco é um Postgres PORTÁTIL que vive em
# `desktop/vendor/pgsql` e sobe como processo comum: nada para instalar, nada para manter
# ligado, nenhuma camada de virtualização entre o app e o disco.
#
# O `docker-compose.yml` foi removido do projeto. Se um dia alguém quiser voltar, ele está
# no histórico do git — mas a premissa mudou: este é um sistema de UMA máquina, e o Docker
# custava um pré-requisito pesado para quem só quer abrir o programa.
# ---------------------------------------------------------------------------

# NÃO usar ErrorActionPreference = "Stop". No PowerShell 5.1, qualquer coisa que um programa
# externo escreva em stderr — inclusive aviso inofensivo — vira erro fatal, e o script
# morreria com tudo funcionando. Aqui se olha o código de saída, que é o que de fato importa.
$ErrorActionPreference = "Continue"

$RAIZ = Split-Path -Parent $PSScriptRoot
$PG = Join-Path $RAIZ "desktop\vendor\pgsql\bin"
$DADOS = Join-Path $env:LOCALAPPDATA "GM Locacoes"
$PGDATA = Join-Path $DADOS "pgdata"
$EXE = Join-Path $RAIZ "backend\dist\erp-frota-api\erp-frota-api.exe"
$PORTA = 8010
$URL = "http://127.0.0.1:$PORTA"
$LOG = Join-Path $DADOS "logs\backend.log"

function Escreva($texto) { Write-Host $texto }

function Backend-Responde {
    try {
        $r = Invoke-WebRequest -Uri "$URL/health" -TimeoutSec 2 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch { return $false }
}

# Já está aberto? Só traz o navegador de volta — abrir duas vezes daria "porta em uso".
if (Backend-Responde) {
    Escreva "O GM Locacoes ja esta rodando."
    Start-Process $URL
    exit 0
}

if (-not (Test-Path (Join-Path $PG "pg_ctl.exe"))) {
    Escreva "ERRO: o Postgres portatil nao esta em desktop\vendor\pgsql." -ForegroundColor Red
    Escreva "Baixe uma vez (~300 MB, fora do git):"
    Escreva "  https://get.enterprisedb.com/postgresql/postgresql-16.10-1-windows-x64-binaries.zip"
    Read-Host "ENTER para fechar"
    exit 1
}

if (-not (Test-Path $EXE)) {
    Escreva "ERRO: o backend nao foi empacotado ainda."
    Escreva "Rode em backend/:  .\.venv\Scripts\python.exe -m PyInstaller erp-frota-api.spec --noconfirm"
    Read-Host "ENTER para fechar"
    exit 1
}

# 1. O banco. Só em localhost: é banco de uma máquina só, e sem senha (-A trust) justamente
#    porque nada de fora alcança a porta.
$bancoDePe = Test-NetConnection -ComputerName 127.0.0.1 -Port 5434 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $bancoDePe) {
    Escreva "Iniciando o banco de dados..."

    if (-not (Test-Path (Join-Path $PGDATA "PG_VERSION"))) {
        Escreva "Primeira execucao: preparando o banco (demora alguns segundos)..."
        New-Item -ItemType Directory -Force $DADOS | Out-Null
        & "$PG\initdb.exe" -D $PGDATA -U frota -A trust -E UTF8 --locale=C > $null 2>&1
        if ($LASTEXITCODE -ne 0) {
            Escreva "ERRO: nao consegui preparar o banco."
            Read-Host "ENTER para fechar"
            exit 1
        }
    }

    # A saída vai para ARQUIVO, nunca para um pipe: o servidor herda o handle de stdout e,
    # canalizado no PowerShell, o pipeline nunca fecha — o banco sobe e o script trava.
    & "$PG\pg_ctl.exe" -D $PGDATA -l (Join-Path $PGDATA "postgres.log") `
        -o "-p 5434 -c listen_addresses=localhost" -w -t 60 start > $null 2>&1

    # O banco lógico não vem do initdb. Criar sempre e ignorar "já existe" é a forma
    # idempotente de garantir que ele exista sem uma checagem a mais.
    & "$PG\createdb.exe" -h 127.0.0.1 -p 5434 -U frota frota > $null 2>&1

    $bancoDePe = Test-NetConnection -ComputerName 127.0.0.1 -Port 5434 -InformationLevel Quiet -WarningAction SilentlyContinue
    if (-not $bancoDePe) {
        Escreva "ERRO: o banco nao subiu. Veja $PGDATA\postgres.log"
        Read-Host "ENTER para fechar"
        exit 1
    }
}

# 2. O backend. Ele roda as migrações sozinho no boot e serve a interface na mesma porta.
Escreva "Abrindo o sistema..."
Start-Process $EXE -WindowStyle Hidden

foreach ($i in 1..45) {
    if (Backend-Responde) {
        Escreva "Pronto. Abrindo $URL"
        Start-Process $URL
        exit 0
    }
    Start-Sleep -Seconds 1
}

# Sem console, o .exe não tem onde reclamar. O log é a única pista.
Escreva ""
Escreva "ERRO: o sistema nao respondeu em 45s."
Escreva "O que aconteceu esta no log: $LOG"
if (Test-Path $LOG) {
    Escreva ""
    Escreva "--- ultimas linhas ---"
    Get-Content $LOG -Tail 20
}
Read-Host "ENTER para fechar"
exit 1

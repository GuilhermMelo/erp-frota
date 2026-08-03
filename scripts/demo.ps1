# Sobe uma instancia de DEMONSTRACAO isolada, com frota ficticia.
#
# POR QUE ISTO EXISTE: demonstrar o sistema entrando no banco de trabalho exporia CPF,
# CNH e contratos de motoristas de verdade. Os papeis (admin/operador) limitam ACOES --
# 19 endpoints exigem admin -- mas NAO limitam visibilidade: e um ERP de uma empresa so.
# Nao existe usuario que veja menos. A unica separacao real e outro banco.
#
# Este script torna o caminho seguro o caminho FACIL. Um comando:
#
#   .\scripts\demo.ps1
#
# Sobe em http://127.0.0.1:8011 -- porta e banco proprios. O banco de trabalho (frota,
# porta 8010) nao e tocado em momento nenhum.
#
# As senhas daqui sao fracas de proposito e isso nao e descuido: os dados sao inventados.
# O que protege dado real e o isolamento, nao a forca da senha de um banco de mentira.

param(
    [switch]$Recompilar,   # forca `npm run build` mesmo se a interface ja estiver compilada
    [switch]$Manter        # nao apaga o banco de demonstracao ao sair
)

# NAO usar "Stop" aqui. O alembic escreve INFO no stderr, o psql escreve NOTICE, e o
# PowerShell 5.1 transforma stderr de programa EXTERNO em erro fatal -- o script morreria
# com tudo funcionando. Aqui se olha o codigo de saida, que e o que de fato diz se deu certo.
# (Mesma armadilha documentada no topo do iniciar-erp.ps1.)
$ErrorActionPreference = "Continue"

$RAIZ = Split-Path -Parent $PSScriptRoot
$PG = Join-Path $RAIZ "desktop\vendor\pgsql\bin"
$PYTHON = Join-Path $RAIZ "backend\.venv\Scripts\python.exe"
$PORTA_DEMO = 8011
$PORTA_TRABALHO = 8010
$BANCO = "frota_demo"
$SENHA_ADMIN = "demo1234"

function Livre($porta) {
    -not (Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Path $PYTHON)) {
    Write-Host "ERRO: ambiente Python nao encontrado em backend\.venv." -ForegroundColor Red
    exit 1
}
if (-not (Livre $PORTA_DEMO)) {
    Write-Host "ERRO: a porta $PORTA_DEMO ja esta em uso. Feche a demonstracao anterior." -ForegroundColor Red
    exit 1
}
$conectou = Test-NetConnection -ComputerName 127.0.0.1 -Port 5434 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $conectou) {
    Write-Host "ERRO: o banco nao esta rodando na porta 5434. Suba com:" -ForegroundColor Red
    Write-Host "  $PG\pg_ctl.exe -D `"$env:LOCALAPPDATA\GM Locacoes\pgdata`" -o `"-p 5434`" -w start"
    exit 1
}

# A interface compilada e servida pela propria API, na mesma porta. E o que permite a
# demonstracao ser autocontida: uma URL so, sem um Vite apontando para a API errada.
$static = Join-Path $RAIZ "backend\static"
if ($Recompilar -or -not (Test-Path (Join-Path $static "index.html"))) {
    Write-Host "Compilando a interface (uma vez)..."
    Push-Location (Join-Path $RAIZ "frontend")
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "ERRO: a compilacao falhou." -ForegroundColor Red; exit 1 }
    Pop-Location
    if (Test-Path $static) { Remove-Item $static -Recurse -Force }
    Copy-Item (Join-Path $RAIZ "frontend\dist") $static -Recurse
}

Write-Host "Preparando o banco de demonstracao ($BANCO)..."
& "$PG\psql.exe" -h 127.0.0.1 -p 5434 -U frota -d postgres -q -c "DROP DATABASE IF EXISTS $BANCO WITH (FORCE);" 2>$null | Out-Null
& "$PG\createdb.exe" -h 127.0.0.1 -p 5434 -U frota $BANCO

$env:DATABASE_URL = "postgresql+psycopg://frota:frota@localhost:5434/$BANCO"
$env:ADMIN_PASSWORD = $SENHA_ADMIN
$env:CORS_ORIGINS = "http://127.0.0.1:$PORTA_DEMO"

Push-Location (Join-Path $RAIZ "backend")
& $PYTHON -m alembic upgrade head 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Host "ERRO: as migracoes falharam." -ForegroundColor Red
    exit 1
}

Write-Host "Subindo a instancia de demonstracao..."
$api = Start-Process -FilePath $PYTHON `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "$PORTA_DEMO", "--host", "127.0.0.1" `
    -PassThru -WindowStyle Hidden
Pop-Location

$subiu = $false
foreach ($i in 1..45) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$PORTA_DEMO/health" -TimeoutSec 2
        if ($h.status -eq "ok") { $subiu = $true; break }
    } catch { }
}
if (-not $subiu) {
    Write-Host "ERRO: a instancia nao respondeu em 45s." -ForegroundColor Red
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
    exit 1
}

Write-Host "Criando a frota ficticia..."
& $PYTHON (Join-Path $RAIZ "scripts\seed_demo.py") --api "http://127.0.0.1:$PORTA_DEMO" --senha $SENHA_ADMIN
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: o seed falhou." -ForegroundColor Red
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
    exit 1
}

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Green
Write-Host " DEMONSTRACAO NO AR:  http://127.0.0.1:$PORTA_DEMO" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
Write-Host ""
Write-Host "   demo@erpfrota.com.br  /  demo1234      (operador)"
Write-Host "   admin@erpfrota.com.br /  $SENHA_ADMIN      (admin)"
Write-Host ""
Write-Host " Dados 100% inventados. O banco de trabalho (porta $PORTA_TRABALHO) nao foi tocado."
Write-Host ""
Write-Host " Pressione ENTER para encerrar e apagar a demonstracao."
Read-Host | Out-Null

if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
if (-not $Manter) {
    Start-Sleep -Seconds 1
    & "$PG\psql.exe" -h 127.0.0.1 -p 5434 -U frota -d postgres -q -c "DROP DATABASE IF EXISTS $BANCO WITH (FORCE);" 2>$null | Out-Null
    Write-Host "Demonstracao encerrada e banco apagado."
} else {
    Write-Host "Demonstracao encerrada. O banco $BANCO foi mantido."
}
